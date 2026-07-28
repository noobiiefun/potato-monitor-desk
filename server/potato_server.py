"""
Potato Monitor Desk - Server (GUI + Tray version)

Arsitektur "spacedesk-style": PC HANYA capture layar (MJPEG, murah di CPU --
tanpa motion estimation kayak H.264) + audio mentah, kirim ke HP lewat USB.
HP yang decode lalu ENCODE ulang jadi H.264 pakai hardware encoder bawaan
Android, baru kirim ke YouTube. PC tidak pernah encode H.264 sama sekali.

Kenapa begini: PC ini (AMD A8-7600 generasi lama, GPU tanpa hardware H.264
encoder yang kedeteksi OBS) terlalu berat kalau harus encode H.264 sendiri.
MJPEG jauh lebih murah untuk CPU tua karena tiap frame dikompres sendiri-
sendiri (seperti sekumpulan foto JPEG berurutan), tidak ada perhitungan
gerak antar-frame yang mahal seperti H.264.

Jalan di background (system tray), window sederhana berisi:
  - Saklar ON/OFF untuk mulai/berhenti streaming
  - Status USB: Terhubung / Tidak terhubung
  - Nama device Android yang terkoneksi
  - Pilihan device audio (klik "Cek / pilih device audio...")

Menutup window (tombol X) TIDAK menutup aplikasi -> minimize ke tray.
Untuk benar-benar keluar: klik kanan icon tray > Keluar.
"""

import json
import os
import shutil
import struct
import subprocess
import sys
import threading
import time
import tkinter as tk
from typing import Optional

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "config.json")


def resource_path(filename: str) -> str:
    """Cari file aset (icon.ico/icon.png) baik saat dijalankan sebagai skrip
    Python biasa maupun saat sudah dibundel jadi .exe oleh PyInstaller."""
    if hasattr(sys, "_MEIPASS"):
        base = sys._MEIPASS  # folder sementara tempat PyInstaller extract data
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, filename)


def resolve_tool(path_no_ext: str, exe_name: str) -> Optional[str]:
    """Cari ffmpeg/adb: prioritas pertama folder 'bin' yang dibundel bareng
    exe (hasil --add-data saat build), baru fallback ke PATH sistem kalau
    user menjalankan potato_server.py langsung sebagai skrip Python tanpa
    bundle. Return None kalau dua-duanya tidak ketemu."""
    bundled = resource_path(os.path.join("bin", exe_name))
    if os.path.isfile(bundled):
        return bundled
    return shutil.which(path_no_ext)


FFMPEG_PATH = resolve_tool("ffmpeg", "ffmpeg.exe")
ADB_PATH = resolve_tool("adb", "adb.exe")

# Windows membuka jendela console baru tiap kali subprocess dijalankan,
# kecuali kita eksplisit minta tidak. Ini yang menyebabkan cmd ffmpeg/adb
# kelap-kelip mengganggu -- terutama parah kalau ffmpeg crash-loop
# (gagal lalu di-retry tiap 2 detik, tiap retry buka jendela baru lagi).
if os.name == "nt":
    _NO_WINDOW_FLAGS = subprocess.CREATE_NO_WINDOW
    _NO_WINDOW_STARTUPINFO = subprocess.STARTUPINFO()
    _NO_WINDOW_STARTUPINFO.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    _NO_WINDOW_STARTUPINFO.wShowWindow = subprocess.SW_HIDE
else:
    _NO_WINDOW_FLAGS = 0
    _NO_WINDOW_STARTUPINFO = None


def _hidden_subprocess_kwargs() -> dict:
    """kwargs tambahan supaya subprocess.run/Popen tidak membuka jendela
    console. Pakai ini di SETIAP pemanggilan adb/ffmpeg."""
    if os.name == "nt":
        return {"creationflags": _NO_WINDOW_FLAGS, "startupinfo": _NO_WINDOW_STARTUPINFO}
    return {}


DEFAULT_CONFIG = {
    "audio_device": "CABLE Output (VB-Audio Virtual Cable)",
    "resolution": "1280x720",
    "framerate": 30,
    "jpeg_quality": 6,  # 2 (terbaik/berat) - 31 (terjelek/ringan), ffmpeg -q:v
    "audio_bitrate": "128k",
    "port": 9999,
    "control_port": 9998
}


def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        return {**DEFAULT_CONFIG, **cfg}
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(DEFAULT_CONFIG, f, indent=2)
    return DEFAULT_CONFIG


def build_video_cmd(cfg):
    """Capture layar jadi urutan JPEG (MJPEG) -- MURAH di CPU, tanpa motion
    estimation seperti H.264. Ini yang bikin PC ringan."""
    w, h = cfg["resolution"].split("x")
    return [
        FFMPEG_PATH, "-hide_banner", "-loglevel", "error",
        "-f", "gdigrab", "-framerate", str(cfg["framerate"]), "-i", "desktop",
        "-vf", f"scale={w}:{h}",
        "-q:v", str(cfg["jpeg_quality"]),
        "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1"
    ]


def build_audio_cmd(cfg):
    """Capture audio (device virtual seperti VB-Cable / Stereo Mix) jadi AAC
    ADTS -- encode audio jauh lebih murah dari video, bukan bottleneck."""
    return [
        FFMPEG_PATH, "-hide_banner", "-loglevel", "error",
        "-f", "dshow", "-i", f"audio={cfg['audio_device']}",
        "-c:a", "aac", "-b:a", cfg["audio_bitrate"], "-ar", "44100",
        "-f", "adts", "pipe:1"
    ]


# ---------- framing protokol custom: [1 byte type][4 byte length BE][payload] ----------
FRAME_TYPE_VIDEO = b"V"  # payload = 1 JPEG utuh
FRAME_TYPE_AUDIO = b"A"  # payload = 1 frame ADTS AAC utuh (termasuk 7-byte header ADTS)


def pack_frame(frame_type: bytes, payload: bytes) -> bytes:
    return frame_type + struct.pack(">I", len(payload)) + payload


def split_mjpeg_frames(read_fn, on_frame):
    """Baca stream MJPEG mentah (JPEG demi JPEG, nempel tanpa jeda) dari
    read_fn(nbytes)->bytes, panggil on_frame(jpeg_bytes) tiap 1 frame utuh
    ketemu. Deteksi batas frame dengan cari SOI marker (0xFFD8) berikutnya
    -- aman dipakai karena JPEG selalu byte-stuff 0xFF di data entropy-nya,
    jadi 0xFFD8 mentah cuma muncul di awal frame beneran."""
    buf = bytearray()
    while True:
        chunk = read_fn(64 * 1024)
        if not chunk:
            if len(buf) > 4:
                on_frame(bytes(buf))
            return
        buf.extend(chunk)
        while True:
            # cari SOI kedua (SOI pertama ada di awal buffer, itu awal frame ini)
            idx = buf.find(b"\xff\xd8", 2)
            if idx == -1:
                break
            on_frame(bytes(buf[:idx]))
            del buf[:idx]


def split_adts_frames(read_fn, on_frame):
    """Baca stream ADTS AAC mentah, panggil on_frame(adts_frame_bytes) tiap
    1 frame utuh (header 7 byte + payload) ketemu, pakai panjang frame yang
    tertulis di header ADTS-nya sendiri (bukan cari-cari marker)."""
    buf = bytearray()
    while True:
        chunk = read_fn(16 * 1024)
        if not chunk:
            return
        buf.extend(chunk)
        while len(buf) >= 7:
            if buf[0] != 0xFF or (buf[1] & 0xF0) != 0xF0:
                # sync hilang, buang 1 byte, coba lagi (jarang terjadi)
                del buf[0]
                continue
            frame_len = ((buf[3] & 0x03) << 11) | (buf[4] << 3) | (buf[5] >> 5)
            if frame_len < 7 or len(buf) < frame_len:
                break
            on_frame(bytes(buf[:frame_len]))
            del buf[:frame_len]


class FramedBroadcastServer:
    """Terima frame video (JPEG) & audio (ADTS) dari 2 proses ffmpeg
    terpisah, bungkus jadi 1 paket kecil ber-header ([type][length][data]),
    lalu broadcast ke SEMUA klien TCP yang connect ke port ini bersamaan."""

    def __init__(self, port: int):
        import socket as sk
        self.port = port
        self._sk = sk
        self._clients = []
        self._clients_lock = threading.Lock()
        self._server_sock = None

    def start(self):
        srv = self._sk.socket(self._sk.AF_INET, self._sk.SOCK_STREAM)
        srv.setsockopt(self._sk.SOL_SOCKET, self._sk.SO_REUSEADDR, 1)
        srv.bind(("0.0.0.0", self.port))
        srv.listen(8)
        self._server_sock = srv
        threading.Thread(target=self._accept_loop, daemon=True).start()

    def _accept_loop(self):
        while self._server_sock is not None:
            try:
                conn, _ = self._server_sock.accept()
                conn.setsockopt(self._sk.IPPROTO_TCP, self._sk.TCP_NODELAY, 1)
                with self._clients_lock:
                    self._clients.append(conn)
            except OSError:
                break

    def broadcast(self, packet: bytes):
        with self._clients_lock:
            dead = []
            for c in self._clients:
                try:
                    c.sendall(packet)
                except Exception:
                    dead.append(c)
            for c in dead:
                self._clients.remove(c)
                try:
                    c.close()
                except Exception:
                    pass

    def stop(self):
        with self._clients_lock:
            for c in self._clients:
                try:
                    c.close()
                except Exception:
                    pass
            self._clients.clear()
        if self._server_sock is not None:
            try:
                self._server_sock.close()
            except Exception:
                pass
            self._server_sock = None


class ToggleSwitch(tk.Canvas):
    """Widget saklar ON/OFF sederhana (gambar sendiri, tanpa library tambahan)."""

    def __init__(self, parent, width=96, height=44, command=None, **kwargs):
        super().__init__(parent, width=width, height=height, highlightthickness=0, **kwargs)
        self.command = command
        self.is_on = False
        self.width = width
        self.height = height
        self.bind("<Button-1>", self._on_click)
        self._draw()

    def _rounded_rect(self, x1, y1, x2, y2, radius, **kw):
        pts = [
            x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
            x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
            x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1
        ]
        return self.create_polygon(pts, smooth=True, **kw)

    def _draw(self):
        self.delete("all")
        pad = 4
        track_color = "#43a047" if self.is_on else "#9e9e9e"
        self._rounded_rect(pad, pad, self.width - pad, self.height - pad,
                            radius=(self.height - 2 * pad) / 2, fill=track_color, outline="")
        knob_d = self.height - 4 * pad
        x0 = (self.width - pad * 2 - knob_d) if self.is_on else pad * 2
        self.create_oval(x0, pad * 2, x0 + knob_d, pad * 2 + knob_d, fill="white", outline="")

    def _on_click(self, _event=None):
        self.set_state(not self.is_on, fire_command=True)

    def set_state(self, is_on: bool, fire_command: bool = False):
        self.is_on = is_on
        self._draw()
        if fire_command and self.command:
            self.command(self.is_on)


class StreamManager:
    """Mengatur 2 proses ffmpeg (video MJPEG + audio AAC) + status koneksi
    adb, jalan di thread terpisah masing-masing."""

    def __init__(self, cfg, on_status_change):
        self.cfg = cfg
        self.on_status_change = on_status_change
        self._video_proc = None
        self._audio_proc = None
        self._want_running = False
        self._usb_connected = False
        self._device_name = ""
        self._reversed_serial = None
        self._last_error = ""
        self._status_text = "Nonaktif"
        self._broadcast = FramedBroadcastServer(cfg["port"])
        self._broadcast.start()
        threading.Thread(target=self._poll_adb_loop, daemon=True).start()
        threading.Thread(target=self._control_server_loop, daemon=True).start()

    # ---------- control channel (dibiarkan nyala untuk kompatibilitas, tidak
    # lagi mengubah setting apa pun -- kualitas sekarang diatur di config.json) ----------
    def _control_server_loop(self):
        import socket as sk
        srv = sk.socket(sk.AF_INET, sk.SOCK_STREAM)
        srv.setsockopt(sk.SOL_SOCKET, sk.SO_REUSEADDR, 1)
        try:
            srv.bind(("0.0.0.0", self.cfg["control_port"]))
            srv.listen(2)
        except Exception:
            return
        while True:
            try:
                conn, _ = srv.accept()
                conn.recv(4096)
                conn.close()
            except Exception:
                pass

    # ---------- adb polling ----------
    def _get_connected_device(self):
        try:
            result = subprocess.run([ADB_PATH, "devices"], capture_output=True, text=True,
                                     timeout=3, **_hidden_subprocess_kwargs())
        except Exception:
            return None
        lines = [l for l in result.stdout.splitlines()[1:] if l.strip() and "device" in l]
        if not lines:
            return None
        return lines[0].split()[0]

    def _get_device_model(self, serial):
        try:
            result = subprocess.run(
                [ADB_PATH, "-s", serial, "shell", "getprop", "ro.product.model"],
                capture_output=True, text=True, timeout=3, **_hidden_subprocess_kwargs()
            )
            return result.stdout.strip() or serial
        except Exception:
            return serial

    def _poll_adb_loop(self):
        while True:
            serial = self._get_connected_device()
            if serial:
                if not self._usb_connected or serial != self._reversed_serial:
                    subprocess.run([ADB_PATH, "-s", serial, "reverse",
                                     f"tcp:{self.cfg['port']}", f"tcp:{self.cfg['port']}"],
                                    **_hidden_subprocess_kwargs())
                    subprocess.run([ADB_PATH, "-s", serial, "reverse",
                                     f"tcp:{self.cfg['control_port']}", f"tcp:{self.cfg['control_port']}"],
                                    **_hidden_subprocess_kwargs())
                    self._reversed_serial = serial
                self._usb_connected = True
                self._device_name = self._get_device_model(serial)
            else:
                self._usb_connected = False
                self._device_name = ""
                self._reversed_serial = None
            self._notify()
            time.sleep(2)

    def _notify(self):
        is_streaming = self._video_proc is not None or self._audio_proc is not None
        self.on_status_change(is_streaming, self._usb_connected, self._device_name,
                               self._last_error, self._status_text)

    # ---------- start/stop ----------
    def start(self):
        if self._want_running:
            return
        self._want_running = True
        threading.Thread(target=self._run_video_loop, daemon=True).start()
        threading.Thread(target=self._run_audio_loop, daemon=True).start()
        self._status_text = "Streaming aktif"
        self._notify()

    def stop(self):
        self._want_running = False
        for attr in ("_video_proc", "_audio_proc"):
            p = getattr(self, attr)
            if p is not None:
                try:
                    p.terminate()
                except Exception:
                    pass
                setattr(self, attr, None)
        self._status_text = "Nonaktif"
        self._notify()

    def _run_video_loop(self):
        while self._want_running:
            cmd = build_video_cmd(self.cfg)
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                         bufsize=0, **_hidden_subprocess_kwargs())
                self._video_proc = proc
                self._notify()
                self._drain_stderr(proc.stderr, "video")

                def on_frame(jpeg_bytes):
                    self._broadcast.broadcast(pack_frame(FRAME_TYPE_VIDEO, jpeg_bytes))

                split_mjpeg_frames(proc.stdout.read, on_frame)
                proc.wait()
            except Exception as e:
                self._last_error = f"Video: {e}"
                self._log(f"Exception video loop: {e}")
            self._video_proc = None
            self._notify()
            if self._want_running:
                time.sleep(2)

    def _run_audio_loop(self):
        while self._want_running:
            cmd = build_audio_cmd(self.cfg)
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                         bufsize=0, **_hidden_subprocess_kwargs())
                self._audio_proc = proc
                self._notify()
                self._drain_stderr(proc.stderr, "audio")

                def on_frame(adts_bytes):
                    self._broadcast.broadcast(pack_frame(FRAME_TYPE_AUDIO, adts_bytes))

                split_adts_frames(proc.stdout.read, on_frame)
                proc.wait()
            except Exception as e:
                self._last_error = f"Audio: {e}"
                self._log(f"Exception audio loop: {e}")
            self._audio_proc = None
            self._notify()
            if self._want_running:
                time.sleep(2)

    def _drain_stderr(self, pipe, label):
        def worker():
            try:
                for raw in iter(pipe.readline, b""):
                    line = raw.decode("utf-8", errors="ignore").strip()
                    if line:
                        self._last_error = f"[{label}] {line}"
                        self._status_text = "Gagal (lihat pesan error di bawah)"
                        self._log(f"[{label}] {line}")
                        self._notify()
            except Exception:
                pass
        threading.Thread(target=worker, daemon=True).start()

    def _log(self, message: str):
        try:
            log_path = os.path.join(os.path.dirname(CONFIG_PATH), "potato_server.log")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
        except Exception:
            pass

    @staticmethod
    def list_audio_devices() -> list:
        try:
            result = subprocess.run(
                [FFMPEG_PATH, "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
                capture_output=True, text=True, timeout=8, **_hidden_subprocess_kwargs()
            )
            output = result.stderr or ""
        except Exception:
            return []
        devices = []
        for line in output.splitlines():
            # Format ffmpeg baru: "Nama Device" (audio)  atau  (video)
            # (bukan lagi pakai header section "DirectShow audio devices").
            # Skip baris "Alternative name" -- itu ID internal, bukan nama pilihan.
            if "Alternative name" in line:
                continue
            if '"' not in line or "(audio)" not in line:
                continue
            name = line.split('"')[1]
            if name not in devices:
                devices.append(name)
        return devices


class App:
    def __init__(self, root):
        self.root = root
        self.cfg = load_config()
        self.tray_icon = None

        root.title("Potato Monitor Desk")
        root.geometry("360x360")
        root.resizable(False, False)
        root.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
        self._set_window_icon()

        tk.Label(root, text="Potato Monitor Desk", font=("Segoe UI", 14, "bold")).pack(pady=(16, 4))
        tk.Label(root, text="Preview layar + suara PC ke HP lewat USB",
                  font=("Segoe UI", 9), fg="#666666").pack(pady=(0, 16))

        switch_frame = tk.Frame(root)
        switch_frame.pack(pady=4)
        tk.Label(switch_frame, text="Streaming:", font=("Segoe UI", 11)).pack(side="left", padx=(0, 12))
        self.switch = ToggleSwitch(switch_frame, command=self.on_toggle)
        self.switch.pack(side="left")

        self.usb_label = tk.Label(root, text="USB: Tidak terhubung", font=("Segoe UI", 10), fg="#c62828")
        self.usb_label.pack(pady=(16, 2))

        self.device_label = tk.Label(root, text="Device: -", font=("Segoe UI", 10), fg="#666666")
        self.device_label.pack(pady=2)

        self.status_label = tk.Label(root, text="Status: Nonaktif", font=("Segoe UI", 10), fg="#666666")
        self.status_label.pack(pady=2)

        self.error_label = tk.Label(root, text="", font=("Segoe UI", 8), fg="#c62828",
                                      wraplength=320, justify="center")
        self.error_label.pack(pady=(4, 0))

        tk.Button(root, text="Cek / pilih device audio...", font=("Segoe UI", 8),
                  command=self.open_audio_device_picker).pack(pady=(8, 0))

        tk.Label(root, text="Tutup jendela ini akan meminimize ke tray, bukan keluar.",
                  font=("Segoe UI", 8), fg="#999999").pack(side="bottom", pady=10)

        self.manager = StreamManager(self.cfg, self.on_status_change)
        self._setup_tray()

    def _set_window_icon(self):
        try:
            self.root.iconbitmap(resource_path("icon.ico"))
        except Exception:
            pass

    def on_toggle(self, is_on):
        if is_on:
            self.manager.start()
        else:
            self.manager.stop()

    def on_status_change(self, is_streaming, usb_connected, device_name, last_error="", status_text="Nonaktif"):
        def update():
            self.switch.set_state(is_streaming)
            if usb_connected:
                self.usb_label.config(text="USB: Terhubung", fg="#2e7d32")
                self.device_label.config(text=f"Device: {device_name}")
            else:
                self.usb_label.config(text="USB: Tidak terhubung", fg="#c62828")
                self.device_label.config(text="Device: -")
            self.status_label.config(text=f"Status: {status_text}")
            self.error_label.config(text=f"⚠ {last_error}" if last_error else "")
            if self.tray_icon:
                self.tray_icon.title = (
                    f"Potato Monitor Desk - {'ON' if is_streaming else 'OFF'} "
                    f"({'terhubung' if usb_connected else 'tidak terhubung'})"
                )
        self.root.after(0, update)

    def _setup_tray(self):
        try:
            import pystray
            from PIL import Image
        except ImportError:
            self.tray_icon = None
            return

        def make_image():
            try:
                return Image.open(resource_path("icon.png"))
            except Exception:
                from PIL import Image as _Image, ImageDraw as _ImageDraw
                img = _Image.new("RGB", (64, 64), "#8d6e63")
                d = _ImageDraw.Draw(img)
                d.ellipse((8, 8, 56, 56), fill="#efebe9")
                return img

        def on_show(_icon, _item):
            self.root.after(0, self.show_window)

        def on_toggle_stream(_icon, _item):
            new_state = not self.switch.is_on
            self.root.after(0, lambda: self.switch.set_state(new_state, fire_command=True))

        def toggle_text(_item):
            return "Matikan Streaming" if self.switch.is_on else "Nyalakan Streaming"

        def on_exit(_icon, _item):
            self.manager.stop()
            _icon.stop()
            self.root.after(0, self.root.destroy)

        menu = pystray.Menu(
            pystray.MenuItem("Buka", on_show, default=True),
            pystray.MenuItem(toggle_text, on_toggle_stream),
            pystray.MenuItem("Keluar", on_exit),
        )
        self.tray_icon = pystray.Icon("potato_monitor_desk", make_image(), "Potato Monitor Desk", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def hide_to_tray(self):
        self.root.withdraw()

    def show_window(self):
        self.root.deiconify()
        self.root.lift()

    # ---------- audio device picker ----------
    def open_audio_device_picker(self):
        loading = tk.Toplevel(self.root)
        loading.title("Potato Monitor Desk")
        loading.geometry("260x80")
        loading.resizable(False, False)
        tk.Label(loading, text="Mencari device audio...", font=("Segoe UI", 9)).pack(expand=True)
        loading.transient(self.root)
        loading.grab_set()

        def worker():
            devices = StreamManager.list_audio_devices()
            self.root.after(0, lambda: self._show_device_picker_result(loading, devices))

        threading.Thread(target=worker, daemon=True).start()

    def _show_device_picker_result(self, loading_dialog, devices):
        loading_dialog.destroy()

        if not devices:
            import tkinter.messagebox as mb
            mb.showwarning(
                "Potato Monitor Desk",
                "Tidak ada device audio (dshow) yang terdeteksi ffmpeg.\n\n"
                "Install VB-Audio Virtual Cable (gratis, vb-audio.com/Cable), "
                "restart PC, lalu cek lagi. Atau enable Stereo Mix kalau ada "
                "di Sound settings > Recording > Show Disabled Devices."
            )
            return

        picker = tk.Toplevel(self.root)
        picker.title("Pilih device audio")
        picker.geometry("380x220")
        picker.resizable(False, False)
        tk.Label(picker, text="Klik nama device yang mau dipakai untuk capture audio PC:",
                  font=("Segoe UI", 9), wraplength=340, justify="left").pack(pady=(12, 6), padx=12)

        listbox = tk.Listbox(picker, font=("Segoe UI", 9), height=6)
        for name in devices:
            listbox.insert("end", name)
        listbox.pack(fill="both", expand=True, padx=12)

        def apply_selection():
            sel = listbox.curselection()
            if not sel:
                return
            chosen = devices[sel[0]]
            self.cfg["audio_device"] = chosen
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self.cfg, f, indent=2)
            self.manager.cfg["audio_device"] = chosen
            picker.destroy()
            import tkinter.messagebox as mb
            mb.showinfo("Potato Monitor Desk",
                         f'Disimpan: "{chosen}"\n\nNyalakan lagi switch Streaming untuk mencoba.')

        tk.Button(picker, text="Pakai device ini", command=apply_selection).pack(pady=10)


def check_prereqs():
    missing = []
    if FFMPEG_PATH is None:
        missing.append("ffmpeg")
    if ADB_PATH is None:
        missing.append("adb")
    if missing:
        import tkinter.messagebox as mb
        mb.showerror(
            "Potato Monitor Desk",
            f"Tidak ditemukan: {', '.join(missing)}.\n"
            "Kalau kamu pakai versi installer/exe resmi, ini seharusnya sudah "
            "otomatis terbundel -- coba install ulang. Kalau menjalankan dari "
            "source langsung, pastikan ffmpeg & adb ada di PATH sistem."
        )
        sys.exit(1)


def main():
    root = tk.Tk()
    check_prereqs()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
