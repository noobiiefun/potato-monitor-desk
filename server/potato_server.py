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
import re
import shutil
import struct
import subprocess
import sys
import threading
import time
import collections
import urllib.request
import urllib.error
import tkinter as tk
from tkinter import ttk
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
    "control_port": 9998,
    # "desktop" = capture seluruh layar. "window" = capture 1 window spesifik
    # by judul (mis. window "Windowed Projector (Preview)" dari OBS -- klik
    # kanan di jendela Preview OBS > Windowed Projector (Preview) untuk
    # membukanya, TIDAK perlu Start Streaming/Recording di OBS sama sekali).
    "capture_mode": "desktop",
    "capture_window_title": "Windowed Projector (Preview)",
    "rtmp_url": "",
    "youtube_api_key": "",
    "youtube_video_id": ""
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
    estimation seperti H.264. Ini yang bikin PC ringan.

    3 mode capture_mode:
    - "desktop": seluruh layar, lewat gdigrab (paling simpel, paling kompatibel)
    - "window": 1 window spesifik by judul, lewat gdigrab -- PERHATIAN: gdigrab
      berbasis GDI, konten yang di-render GPU (mis. overlay webcam di preview
      OBS lewat Direct3D) bisa freeze/tidak ter-capture dengan benar. Kalau
      ketemu masalah itu, pakai mode "obs_virtual_cam" di bawah.
    - "obs_virtual_cam": capture dari device "OBS Virtual Camera" (aktifkan
      dulu tombol "Start Virtual Camera" di OBS) -- OBS sendiri yang render
      komposit semua source (termasuk webcam), diekspos sebagai video device
      biasa. Jauh lebih reliable daripada gdigrab window-title untuk kasus
      preview yang ada elemen GPU-rendered di dalamnya.
    """
    w, h = cfg["resolution"].split("x")
    mode = cfg.get("capture_mode", "desktop")

    if mode == "obs_virtual_cam":
        return [
            FFMPEG_PATH, "-hide_banner", "-loglevel", "error",
            "-f", "dshow", "-framerate", str(cfg["framerate"]),
            "-video_size", f"{w}x{h}", "-i", "video=OBS Virtual Camera",
            "-vf", f"scale={w}:{h}",
            "-q:v", str(cfg["jpeg_quality"]),
            "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1"
        ]

    if mode == "window" and cfg.get("capture_window_title"):
        input_args = ["-i", f"title={cfg['capture_window_title']}"]
    else:
        input_args = ["-i", "desktop"]
    return [
        FFMPEG_PATH, "-hide_banner", "-loglevel", "error",
        "-f", "gdigrab", "-framerate", str(cfg["framerate"]), *input_args,
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
    lalu broadcast ke SEMUA klien TCP yang connect ke port ini bersamaan.

    PENTING: tiap klien punya antrian + thread pengirim SENDIRI. Kalau ada
    1 klien yang lambat nerima (mis. HP lagi berat/USB lelet), klien itu
    yang kehilangan frame lama (di-drop, bukan ditunggu) -- klien LAIN dan
    proses capture ffmpeg TIDAK ikut ketahan. Sebelumnya broadcast() kirim
    langsung (blocking) ke semua klien gantian, jadi 1 klien lambat bikin
    semuanya numpuk delay, termasuk balik ke buffer capture audio di PC."""

    MAX_QUEUE = 60  # ~2 detik buffer di 30fps sebelum mulai buang frame lama

    def __init__(self, port: int):
        import socket as sk
        self.port = port
        self._sk = sk
        self._clients_lock = threading.Lock()
        self._client_queues = {}  # conn -> collections.deque
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
                q = collections.deque(maxlen=self.MAX_QUEUE)
                event = threading.Event()
                with self._clients_lock:
                    self._client_queues[conn] = (q, event)
                threading.Thread(target=self._writer_loop, args=(conn, q, event), daemon=True).start()
            except OSError:
                break

    def _writer_loop(self, conn, q: "collections.deque", event: threading.Event):
        while True:
            event.wait(timeout=1.0)
            event.clear()
            while True:
                try:
                    packet = q.popleft()
                except IndexError:
                    break
                try:
                    conn.sendall(packet)
                except Exception:
                    with self._clients_lock:
                        self._client_queues.pop(conn, None)
                    try:
                        conn.close()
                    except Exception:
                        pass
                    return

    def broadcast(self, packet: bytes):
        # Non-blocking: cuma numpuk ke antrian tiap klien lalu bangunkan
        # writer thread-nya. deque(maxlen=...) otomatis buang frame PALING
        # LAMA sendiri kalau klien itu ketinggalan jauh -- tidak pernah
        # nunggu di sini.
        with self._clients_lock:
            items = list(self._client_queues.values())
        for q, event in items:
            q.append(packet)
            event.set()

    def stop(self):
        with self._clients_lock:
            for conn in list(self._client_queues.keys()):
                try:
                    conn.close()
                except Exception:
                    pass
            self._client_queues.clear()
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

    # ---------- control channel ----------
    # Setiap kali HP connect ke port ini, server langsung kirim balik JSON
    # berisi rtmp_url yang kamu isi di window app -- jadi kamu cukup isi
    # sekali di sini, HP otomatis dapet tanpa perlu ketik manual di HP.
    def _control_server_loop(self):
        import socket as sk
        srv = sk.socket(sk.AF_INET, sk.SOCK_STREAM)
        srv.setsockopt(sk.SOL_SOCKET, sk.SO_REUSEADDR, 1)
        try:
            srv.bind(("0.0.0.0", self.cfg["control_port"]))
            srv.listen(4)
        except Exception:
            return
        while True:
            try:
                conn, _ = srv.accept()
                payload = json.dumps({"rtmp_url": self.cfg.get("rtmp_url", "")}) + "\n"
                conn.sendall(payload.encode("utf-8"))
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
                    p.wait(timeout=3)  # pastikan proses (ffmpeg.exe) benar-benar
                    # keluar & lepas handle-nya sebelum lanjut -- kalau tidak,
                    # dan app ditutup dari mode --onefile, Windows bisa gagal
                    # bersihkan folder temp karena file masih "dipegang".
                except subprocess.TimeoutExpired:
                    try:
                        p.kill()
                        p.wait(timeout=2)
                    except Exception:
                        pass
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


def list_open_window_titles() -> list:
    """Daftar judul semua window yang sedang terbuka & terlihat di Windows --
    dipakai buat dropdown pilih window capture, jadi tidak perlu ketik judul
    manual. Pakai ctypes langsung (user32.dll), tidak butuh library tambahan."""
    if os.name != "nt":
        return []
    import ctypes
    titles = []

    def foreach_window(hwnd, _lparam):
        if ctypes.windll.user32.IsWindowVisible(hwnd):
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
                title = buff.value.strip()
                if title and title not in titles:
                    titles.append(title)
        return True

    enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(foreach_window)
    ctypes.windll.user32.EnumWindows(enum_proc, 0)
    return titles


def extract_youtube_video_id(text: str) -> str:
    """Terima URL YouTube penuh atau video ID mentah, kembalikan video ID-nya
    saja. Contoh URL yang didukung: watch?v=, youtu.be/, /live/."""
    text = text.strip()
    patterns = [
        r"(?:v=|youtu\.be/|/live/|/embed/)([A-Za-z0-9_-]{11})",
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            return m.group(1)
    return text  # anggap sudah berupa ID mentah


class YoutubeChatPoller:
    """Polling YouTube Live Chat lewat YouTube Data API v3 -- jauh lebih
    ringan dari embed WebView (cuma HTTP+JSON, bukan render Chromium penuh)."""

    def __init__(self, api_key: str, video_id: str, on_messages, on_error):
        self.api_key = api_key
        self.video_id = extract_youtube_video_id(video_id)
        self.on_messages = on_messages  # callback(list[(author, text)])
        self.on_error = on_error  # callback(str)
        self._running = False
        self._thread = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _api_get(self, url: str) -> dict:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _run(self):
        try:
            info_url = (
                "https://www.googleapis.com/youtube/v3/videos"
                f"?part=liveStreamingDetails&id={self.video_id}&key={self.api_key}"
            )
            data = self._api_get(info_url)
            items = data.get("items", [])
            if not items:
                self.on_error("Video ID tidak ditemukan (cek lagi URL/ID-nya).")
                return
            live_chat_id = items[0].get("liveStreamingDetails", {}).get("activeLiveChatId")
            if not live_chat_id:
                self.on_error("Live chat belum aktif -- pastikan stream sudah LIVE di YouTube.")
                return
        except urllib.error.HTTPError as e:
            self.on_error(f"API error ({e.code}): cek API key & kuota harian.")
            return
        except Exception as e:
            self.on_error(f"Gagal menghubungi YouTube API: {e}")
            return

        page_token = ""
        while self._running:
            try:
                url = (
                    "https://www.googleapis.com/youtube/v3/liveChat/messages"
                    f"?liveChatId={live_chat_id}&part=snippet,authorDetails&key={self.api_key}"
                )
                if page_token:
                    url += f"&pageToken={page_token}"
                data = self._api_get(url)
                messages = []
                for item in data.get("items", []):
                    author = item.get("authorDetails", {}).get("displayName", "?")
                    text = item.get("snippet", {}).get("displayMessage", "")
                    if text:
                        messages.append((author, text))
                if messages:
                    self.on_messages(messages)
                page_token = data.get("nextPageToken", page_token)
                interval_ms = data.get("pollingIntervalMillis", 5000)
                time.sleep(max(interval_ms, 2000) / 1000)
            except urllib.error.HTTPError as e:
                self.on_error(f"API error ({e.code}): cek API key & kuota harian.")
                time.sleep(10)
            except Exception as e:
                self.on_error(f"Terputus dari YouTube API: {e}")
                time.sleep(5)


class App:
    def __init__(self, root):
        self.root = root
        self.cfg = load_config()
        self.tray_icon = None
        self.chat_poller: Optional[YoutubeChatPoller] = None

        root.title("Potato Monitor Desk")
        root.geometry("400x480")
        root.resizable(False, False)
        root.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
        self._set_window_icon()
        self._apply_theme()

        header = ttk.Frame(root, padding=(16, 16, 16, 8))
        header.pack(fill="x")
        ttk.Label(header, text="Potato Monitor Desk", font=("Segoe UI", 15, "bold")).pack()
        ttk.Label(header, text="Preview layar + suara PC ke HP lewat USB",
                  font=("Segoe UI", 9), foreground="#666666").pack(pady=(2, 0))

        notebook = ttk.Notebook(root)
        notebook.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        status_tab = ttk.Frame(notebook, padding=16)
        settings_tab = ttk.Frame(notebook, padding=16)
        chat_tab = ttk.Frame(notebook, padding=16)
        notebook.add(status_tab, text="Status")
        notebook.add(settings_tab, text="Pengaturan")
        notebook.add(chat_tab, text="Live Chat")

        self._build_status_tab(status_tab)
        self._build_settings_tab(settings_tab)
        self._build_chat_tab(chat_tab)

        ttk.Label(root, text="Tutup jendela ini akan meminimize ke tray, bukan keluar.",
                  font=("Segoe UI", 8), foreground="#999999").pack(pady=(0, 10))

        self.manager = StreamManager(self.cfg, self.on_status_change)
        self._setup_tray()

    def _apply_theme(self):
        style = ttk.Style(self.root)
        try:
            if os.name == "nt":
                style.theme_use("vista")
            else:
                style.theme_use("clam")
        except Exception:
            pass
        style.configure("TNotebook.Tab", font=("Segoe UI", 9), padding=(14, 6))
        style.configure("TLabel", font=("Segoe UI", 9))
        style.configure("TButton", font=("Segoe UI", 9))
        style.configure("Accent.TButton", font=("Segoe UI", 9, "bold"))

    # ---------- Tab: Status ----------
    def _build_status_tab(self, parent):
        switch_frame = ttk.Frame(parent)
        switch_frame.pack(pady=(4, 12))
        ttk.Label(switch_frame, text="Streaming:", font=("Segoe UI", 11)).pack(side="left", padx=(0, 12))
        self.switch = ToggleSwitch(switch_frame, command=self.on_toggle)
        self.switch.pack(side="left")

        info = ttk.Frame(parent)
        info.pack(fill="x", pady=4)
        self.usb_label = ttk.Label(info, text="USB: Tidak terhubung", font=("Segoe UI", 10), foreground="#c62828")
        self.usb_label.pack(anchor="center")
        self.device_label = ttk.Label(info, text="Device: -", font=("Segoe UI", 10), foreground="#666666")
        self.device_label.pack(anchor="center", pady=2)
        self.status_label = ttk.Label(info, text="Status: Nonaktif", font=("Segoe UI", 10), foreground="#666666")
        self.status_label.pack(anchor="center", pady=2)

        self.error_label = ttk.Label(parent, text="", font=("Segoe UI", 8), foreground="#c62828",
                                      wraplength=340, justify="center")
        self.error_label.pack(pady=(8, 0), fill="x")

    # ---------- Tab: Pengaturan ----------
    def _make_scrollable(self, parent) -> tk.Widget:
        """Bikin area yang bisa di-scroll di dalam sebuah tab -- dipakai kalau
        kontennya lebih tinggi dari window (kejadian di tab Pengaturan setelah
        makin banyak opsi ditambahkan). Return frame tempat kamu pack widget
        seperti biasa (bukan langsung ke `parent`)."""
        canvas = tk.Canvas(parent, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)

        inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(window_id, width=e.width))
        canvas.configure(yscrollcommand=scrollbar.set)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        return inner

    def _build_settings_tab(self, parent):
        scroll = self._make_scrollable(parent)

        audio_section = ttk.LabelFrame(scroll, text="Audio", padding=10)
        audio_section.pack(fill="x", pady=(0, 10))
        ttk.Button(audio_section, text="Cek / pilih device audio...",
                   command=self.open_audio_device_picker).pack(fill="x")

        capture_section = ttk.LabelFrame(scroll, text="Sumber Capture", padding=10)
        capture_section.pack(fill="x", pady=(0, 10))

        self.capture_mode_var = tk.StringVar(value=self.cfg.get("capture_mode", "desktop"))
        ttk.Radiobutton(
            capture_section, text="Seluruh layar", value="desktop",
            variable=self.capture_mode_var, command=self.on_capture_mode_changed
        ).pack(anchor="w")
        ttk.Radiobutton(
            capture_section, text="1 window tertentu by judul (bisa freeze kalau ada konten GPU seperti webcam)",
            value="window", variable=self.capture_mode_var, command=self.on_capture_mode_changed
        ).pack(anchor="w")
        ttk.Radiobutton(
            capture_section, text="OBS Virtual Camera (disarankan kalau preview OBS ada webcam)",
            value="obs_virtual_cam", variable=self.capture_mode_var, command=self.on_capture_mode_changed
        ).pack(anchor="w")

        self.window_title_var = tk.StringVar(value=self.cfg.get("capture_window_title", ""))
        self.window_combo = ttk.Combobox(capture_section, textvariable=self.window_title_var, font=("Segoe UI", 9))
        self.window_combo.pack(fill="x", pady=(6, 0))
        self.window_combo["postcommand"] = self._refresh_window_list
        self.window_combo.bind("<<ComboboxSelected>>", lambda _e: self.on_capture_mode_changed())
        self.window_combo.bind("<FocusOut>", lambda _e: self.on_capture_mode_changed())
        self.window_combo.bind("<Return>", lambda _e: self.on_capture_mode_changed())

        ttk.Label(
            capture_section,
            text='Untuk "1 window tertentu": daftar otomatis dari window yang sedang '
                 'terbuka, klik dropdown buat refresh. Untuk "OBS Virtual Camera": '
                 'klik dulu "Start Virtual Camera" di panel Controls OBS (tidak '
                 'perlu Start Streaming/Recording), device-nya baru aktif setelah itu.',
            font=("Segoe UI", 7), foreground="#999999", wraplength=340, justify="left"
        ).pack(anchor="w", pady=(4, 0))

        rtmp_section = ttk.LabelFrame(scroll, text="Live Streaming", padding=10)
        rtmp_section.pack(fill="x")
        ttk.Label(rtmp_section, text="RTMP URL + Stream Key (dikirim otomatis ke HP):").pack(anchor="w")
        self.rtmp_url_var = tk.StringVar(value=self.cfg.get("rtmp_url", ""))
        rtmp_entry = ttk.Entry(rtmp_section, textvariable=self.rtmp_url_var, show="*")
        rtmp_entry.pack(fill="x", pady=(4, 0))
        rtmp_entry.bind("<FocusOut>", lambda _e: self.on_rtmp_url_changed())
        rtmp_entry.bind("<Return>", lambda _e: self.on_rtmp_url_changed())
        ttk.Label(rtmp_section, text='Contoh: rtmp://a.rtmp.youtube.com/live2/xxxx-xxxx-xxxx-xxxx',
                  font=("Segoe UI", 7), foreground="#999999", wraplength=340, justify="left").pack(anchor="w", pady=(4, 0))

    def _refresh_window_list(self):
        titles = list_open_window_titles()
        self.window_combo["values"] = titles

    # ---------- Tab: Live Chat ----------
    def _build_chat_tab(self, parent):
        key_section = ttk.Frame(parent)
        key_section.pack(fill="x")
        ttk.Label(key_section, text="YouTube API Key:").pack(anchor="w")
        self.yt_api_key_var = tk.StringVar(value=self.cfg.get("youtube_api_key", ""))
        yt_key_entry = ttk.Entry(key_section, textvariable=self.yt_api_key_var, show="*")
        yt_key_entry.pack(fill="x", pady=(2, 8))

        ttk.Label(key_section, text="URL / Video ID Live YouTube:").pack(anchor="w")
        self.yt_video_var = tk.StringVar(value=self.cfg.get("youtube_video_id", ""))
        yt_video_entry = ttk.Entry(key_section, textvariable=self.yt_video_var)
        yt_video_entry.pack(fill="x", pady=(2, 8))

        btn_row = ttk.Frame(key_section)
        btn_row.pack(fill="x", pady=(0, 8))
        self.chat_toggle_btn = ttk.Button(btn_row, text="Mulai Live Chat", command=self.on_chat_toggle)
        self.chat_toggle_btn.pack(fill="x")

        ttk.Label(
            key_section,
            text='Belum punya API key? console.cloud.google.com > New Project > '
                 'enable "YouTube Data API v3" > Credentials > Create API Key.',
            font=("Segoe UI", 7), foreground="#999999", wraplength=340, justify="left"
        ).pack(anchor="w")

        self.chat_status_label = ttk.Label(parent, text="", font=("Segoe UI", 8), foreground="#c62828",
                                            wraplength=340, justify="left")
        self.chat_status_label.pack(fill="x", pady=(6, 4))

        chat_frame = ttk.Frame(parent)
        chat_frame.pack(fill="both", expand=True)
        scrollbar = ttk.Scrollbar(chat_frame)
        scrollbar.pack(side="right", fill="y")
        self.chat_text = tk.Text(chat_frame, font=("Segoe UI", 9), wrap="word",
                                  yscrollcommand=scrollbar.set, state="disabled", height=10)
        self.chat_text.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.chat_text.yview)
        self.chat_text.tag_configure("author", font=("Segoe UI", 9, "bold"))

    def on_chat_toggle(self):
        if self.chat_poller is not None:
            self.chat_poller.stop()
            self.chat_poller = None
            self.chat_toggle_btn.config(text="Mulai Live Chat")
            self.chat_status_label.config(text="")
            return

        api_key = self.yt_api_key_var.get().strip()
        video_id = self.yt_video_var.get().strip()
        if not api_key or not video_id:
            self.chat_status_label.config(text="Isi API Key dan URL/Video ID dulu.")
            return

        self.cfg["youtube_api_key"] = api_key
        self.cfg["youtube_video_id"] = video_id
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(self.cfg, f, indent=2)

        self.chat_text.config(state="normal")
        self.chat_text.delete("1.0", "end")
        self.chat_text.config(state="disabled")
        self.chat_status_label.config(text="Menghubungkan ke YouTube...", foreground="#666666")

        self.chat_poller = YoutubeChatPoller(
            api_key, video_id,
            on_messages=lambda msgs: self.root.after(0, lambda: self._append_chat_messages(msgs)),
            on_error=lambda msg: self.root.after(0, lambda: self.chat_status_label.config(
                text=f"⚠ {msg}", foreground="#c62828"))
        )
        self.chat_poller.start()
        self.chat_toggle_btn.config(text="Berhenti Live Chat")

    def _append_chat_messages(self, messages):
        self.chat_status_label.config(text="")
        self.chat_text.config(state="normal")
        for author, text in messages:
            self.chat_text.insert("end", f"{author}: ", "author")
            self.chat_text.insert("end", f"{text}\n")
        self.chat_text.see("end")
        self.chat_text.config(state="disabled")

    # ---------- handlers ----------
    def on_capture_mode_changed(self):
        self.cfg["capture_mode"] = self.capture_mode_var.get()
        self.cfg["capture_window_title"] = self.window_title_var.get().strip()
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(self.cfg, f, indent=2)
        self.manager.cfg["capture_mode"] = self.cfg["capture_mode"]
        self.manager.cfg["capture_window_title"] = self.cfg["capture_window_title"]

    def on_rtmp_url_changed(self):
        self.cfg["rtmp_url"] = self.rtmp_url_var.get().strip()
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(self.cfg, f, indent=2)
        self.manager.cfg["rtmp_url"] = self.cfg["rtmp_url"]

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
                self.usb_label.config(text="USB: Terhubung", foreground="#2e7d32")
                self.device_label.config(text=f"Device: {device_name}")
            else:
                self.usb_label.config(text="USB: Tidak terhubung", foreground="#c62828")
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
            if self.chat_poller:
                self.chat_poller.stop()
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
        ttk.Label(loading, text="Mencari device audio...", font=("Segoe UI", 9)).pack(expand=True)
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
        ttk.Label(picker, text="Klik nama device yang mau dipakai untuk capture audio PC:",
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

        ttk.Button(picker, text="Pakai device ini", command=apply_selection).pack(pady=10)

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
