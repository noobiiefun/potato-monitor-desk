"""
Potato Monitor Desk - Server (GUI + Tray version)

Jalan di background (system tray), dengan window sederhana berisi:
  - Saklar ON/OFF untuk mulai/berhenti (nyalakan RTMP listener lokal)
  - Status USB: Terhubung / Tidak terhubung
  - Nama device Android yang terkoneksi

PC TIDAK capture layar/audio sendiri. OBS (yang kamu jalankan seperti
biasa untuk gaming) yang push stream-nya ke sini lewat RTMP lokal
(127.0.0.1) -- server cuma menerima lalu meneruskan (`-c copy`, remux
tanpa re-encode) ke HP lewat kabel USB. Tidak butuh driver audio
tambahan apa pun (Stereo Mix/VB-Cable/dll) karena OBS sudah handle
capture audio+videonya sendiri.

Menutup window (tombol X) TIDAK menutup aplikasi -> minimize ke tray.
Untuk benar-benar keluar: klik kanan icon tray > Keluar.
"""

import json
import os
import shutil
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
    "rtmp_port": 1935,
    "rtmp_app": "live",
    "stream_key": "stream",
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


def build_ffmpeg_cmd(cfg):
    """PC TIDAK capture layar/audio sendiri lagi. OBS (yang sudah kamu pakai
    dan sudah terbukti jalan mulus) yang push hasil encode-nya ke sini lewat
    RTMP lokal. ffmpeg di sini cuma REMUX (repackaging, `-c copy`, tanpa
    decode/encode ulang sama sekali) supaya bisa diteruskan ke HP -- jauh
    lebih ringan buat PC dan tidak butuh instalasi driver audio apa pun."""
    rtmp_url = f"rtmp://0.0.0.0:{cfg['rtmp_port']}/{cfg['rtmp_app']}/{cfg['stream_key']}"
    return [
        FFMPEG_PATH, "-hide_banner", "-loglevel", "error",
        "-listen", "1", "-i", rtmp_url,
        "-c", "copy",
        "-f", "mpegts", "pipe:1"
    ]


class TsBroadcastServer:
    """Terima 1 sumber MPEG-TS dari stdout ffmpeg, lalu salin (broadcast) byte
    yang sama ke SEMUA klien TCP yang connect ke port ini secara bersamaan.

    Ini menggantikan cara lama (ffmpeg langsung 'tcp://...?listen=1') yang
    cuma bisa melayani 1 klien. Sekarang preview di HP (ExoPlayer) dan relay
    livestream RTMP di HP bisa connect ke port yang sama di saat bersamaan.
    """

    def __init__(self, port: int):
        import socket as sk
        self.port = port
        self._sk = sk
        self._clients = []  # list of socket.socket
        self._clients_lock = threading.Lock()
        self._server_sock = None
        self._accept_thread = None

    def start(self):
        srv = self._sk.socket(self._sk.AF_INET, self._sk.SOCK_STREAM)
        srv.setsockopt(self._sk.SOL_SOCKET, self._sk.SO_REUSEADDR, 1)
        srv.bind(("0.0.0.0", self.port))
        srv.listen(8)
        self._server_sock = srv
        self._accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._accept_thread.start()

    def _accept_loop(self):
        while self._server_sock is not None:
            try:
                conn, _ = self._server_sock.accept()
                conn.setsockopt(self._sk.IPPROTO_TCP, self._sk.TCP_NODELAY, 1)
                with self._clients_lock:
                    self._clients.append(conn)
            except OSError:
                break

    def broadcast(self, chunk: bytes):
        with self._clients_lock:
            dead = []
            for c in self._clients:
                try:
                    c.sendall(chunk)
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
    """Mengatur proses ffmpeg + status koneksi adb, jalan di thread terpisah."""

    def __init__(self, cfg, on_status_change):
        self.cfg = cfg
        self.on_status_change = on_status_change  # callback(is_streaming, usb_connected, device_name)
        self._proc = None
        self._want_running = False
        self._stream_thread = None
        self._poll_thread = threading.Thread(target=self._poll_adb_loop, daemon=True)
        self._usb_connected = False
        self._device_name = ""
        self._reversed_serial = None
        self._last_error = ""
        self._status_text = "Nonaktif"
        self._broadcast = TsBroadcastServer(cfg["port"])
        self._broadcast.start()
        self._poll_thread.start()
        self._control_thread = threading.Thread(target=self._control_server_loop, daemon=True)
        self._control_thread.start()

    # ---------- control channel ----------
    # Catatan: sejak versi relay-OBS ini, kualitas video/audio ditentukan
    # oleh setting OBS kamu sendiri (bukan lagi oleh server, karena server
    # cuma remux `-c copy` tanpa re-encode). Channel ini dibiarkan tetap
    # nyala (compat dengan client lama yang masih connect ke port ini)
    # tapi tidak lagi mengubah apa pun di ffmpeg.
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
        return lines[0].split()[0]  # serial

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
        self.on_status_change(self._proc is not None, self._usb_connected, self._device_name,
                               self._last_error, self._status_text)

    # ---------- ffmpeg control ----------
    def start(self):
        if self._want_running:
            return
        self._want_running = True
        self._stream_thread = threading.Thread(target=self._run_loop, daemon=True)
        self._stream_thread.start()

    def stop(self):
        self._want_running = False
        if self._proc is not None:
            self._proc.terminate()
            self._proc = None
        self._status_text = "Nonaktif"
        self._notify()

    def _run_loop(self):
        while self._want_running:
            cmd = build_ffmpeg_cmd(self.cfg)  # dibangun ulang tiap iterasi (config bisa berubah)
            try:
                self._proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0,
                    **_hidden_subprocess_kwargs()
                )
                self._status_text = "Menunggu OBS mulai streaming..."
                self._notify()

                # baca stderr ffmpeg di thread terpisah -- isinya pesan error
                # asli (RTMP app/key salah, port dipakai proses lain, dll)
                # yang tadinya cuma numpang lewat di jendela cmd yang
                # kelap-kelip lalu hilang begitu proses di-retry.
                stderr_lines = []

                def _drain_stderr(pipe):
                    try:
                        for raw in iter(pipe.readline, b""):
                            line = raw.decode("utf-8", errors="ignore").strip()
                            if line:
                                stderr_lines.append(line)
                                self._last_error = line
                                self._log(line)
                    except Exception:
                        pass

                threading.Thread(target=_drain_stderr, args=(self._proc.stderr,), daemon=True).start()

                stdout = self._proc.stdout
                got_any_data = False
                while True:
                    chunk = stdout.read(32 * 1024)
                    if not chunk:
                        break
                    if not got_any_data:
                        got_any_data = True
                        self._last_error = ""  # ffmpeg berhasil kirim data, bersihkan error lama
                        self._status_text = "Streaming aktif (dari OBS)"
                        self._notify()
                    self._broadcast.broadcast(chunk)
                self._proc.wait()

                if got_any_data:
                    # OBS berhenti streaming (mis. tombol Stop Streaming di OBS
                    # ditekan) -- bukan error, cuma OBS-nya yang stop
                    self._status_text = "OBS berhenti streaming, menunggu lagi..."
                elif self._want_running:
                    # ffmpeg keluar tanpa pernah terima koneksi/data -> gagal start
                    reason = stderr_lines[-1] if stderr_lines else "ffmpeg keluar tanpa output"
                    self._last_error = reason
                    self._status_text = "Gagal (lihat pesan error di bawah)"
                    self._log(f"ffmpeg gagal start: {reason}")
            except Exception as e:
                self._last_error = str(e)
                self._status_text = "Gagal (lihat pesan error di bawah)"
                self._log(f"Exception saat menjalankan ffmpeg: {e}")
            self._proc = None
            self._notify()
            if self._want_running:
                time.sleep(2)

    def _log(self, message: str):
        try:
            log_path = os.path.join(os.path.dirname(CONFIG_PATH), "potato_server.log")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
        except Exception:
            pass


class App:
    def __init__(self, root):
        self.root = root
        self.cfg = load_config()
        self.tray_icon = None

        root.title("Potato Monitor Desk")
        root.geometry("360x335")
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
        self.usb_label.pack(pady=(20, 2))

        self.device_label = tk.Label(root, text="Device: -", font=("Segoe UI", 10), fg="#666666")
        self.device_label.pack(pady=2)

        self.status_label = tk.Label(root, text="Status: Nonaktif", font=("Segoe UI", 10), fg="#666666")
        self.status_label.pack(pady=2)

        self.error_label = tk.Label(root, text="", font=("Segoe UI", 8), fg="#c62828",
                                      wraplength=320, justify="center")
        self.error_label.pack(pady=(4, 0))

        obs_info = (
            f"Setting OBS: Settings > Stream > Service: Custom\n"
            f"Server: rtmp://127.0.0.1:{self.cfg['rtmp_port']}/{self.cfg['rtmp_app']}\n"
            f"Stream Key: {self.cfg['stream_key']}\n"
            f"Lalu tekan \"Start Streaming\" di OBS seperti biasa."
        )
        tk.Label(root, text=obs_info, font=("Segoe UI", 8), fg="#555555",
                  justify="left").pack(pady=(10, 0))

        tk.Label(root, text="Tutup jendela ini akan meminimize ke tray, bukan keluar.",
                  font=("Segoe UI", 8), fg="#999999").pack(side="bottom", pady=10)

        self.manager = StreamManager(self.cfg, self.on_status_change)
        self._setup_tray()

    # ---------- icon ----------
    def _set_window_icon(self):
        try:
            self.root.iconbitmap(resource_path("icon.ico"))
        except Exception:
            pass  # aman diabaikan kalau file icon belum ada / platform non-Windows

    # ---------- UI callbacks ----------
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

    # ---------- tray ----------
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
                # fallback kalau icon.png tidak ditemukan, tetap jalan tanpa crash
                from PIL import Image as _Image, ImageDraw as _ImageDraw
                img = _Image.new("RGB", (64, 64), "#8d6e63")
                d = _ImageDraw.Draw(img)
                d.ellipse((8, 8, 56, 56), fill="#efebe9")
                return img

        def on_show(_icon, _item):
            self.root.after(0, self.show_window)

        def on_toggle_stream(_icon, _item):
            new_state = not (self.manager._proc is not None)
            self.root.after(0, lambda: self.switch.set_state(new_state, fire_command=True))

        def toggle_text(_item):
            return "Matikan Streaming" if self.manager._proc is not None else "Nyalakan Streaming"

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
