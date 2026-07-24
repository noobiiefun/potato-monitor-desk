"""
Potato Monitor Desk - Server (GUI + Tray version)

Jalan di background (system tray), dengan window sederhana berisi:
  - Saklar ON/OFF untuk mulai/berhenti streaming (tanpa perlu close app)
  - Status USB: Terhubung / Tidak terhubung
  - Nama device Android yang terkoneksi

Menutup window (tombol X) TIDAK menutup aplikasi -> minimize ke tray.
Untuk benar-benar keluar: klik kanan icon tray > Keluar.

Prasyarat di PC (kalau pakai installer resmi, semua sudah otomatis terbundel,
tidak perlu install apa pun secara manual):
  - ffmpeg & adb dibundel otomatis dari folder server/bin/ saat build
  - Audio loopback aktif (Stereo Mix / VB-Audio Virtual Cable) -- ini satu-
    satunya hal yang tetap perlu diaktifkan manual di Windows Sound Settings
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


DEFAULT_CONFIG = {
    "audio_device": "Stereo Mix (Realtek Audio)",
    "video_bitrate": "3M",
    "audio_bitrate": "128k",
    "port": 9999,
    "control_port": 9998,
    "resolution": "1280x720",
    "framerate": 30
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
    w, h = cfg["resolution"].split("x")
    return [
        FFMPEG_PATH, "-hide_banner", "-loglevel", "error",
        "-f", "gdigrab", "-framerate", str(cfg["framerate"]), "-i", "desktop",
        "-f", "dshow", "-i", f"audio={cfg['audio_device']}",
        "-vf", f"scale={w}:{h}",
        "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
        "-b:v", cfg["video_bitrate"], "-pix_fmt", "yuv420p", "-g", str(cfg["framerate"]),
        "-c:a", "aac", "-b:a", cfg["audio_bitrate"], "-ar", "44100",
        "-f", "mpegts", f"tcp://0.0.0.0:{cfg['port']}?listen=1"
    ]


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
        self._poll_thread.start()
        self._control_thread = threading.Thread(target=self._control_server_loop, daemon=True)
        self._control_thread.start()

    # ---------- control channel (client bisa ganti resolusi/bitrate) ----------
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
                data = conn.recv(4096).decode("utf-8", errors="ignore").strip()
                conn.close()
                if data:
                    cmd = json.loads(data)
                    self.update_settings(cmd)
            except Exception:
                pass

    def update_settings(self, cmd: dict):
        changed = False
        for key in ("resolution", "video_bitrate", "framerate"):
            if key in cmd and cmd[key] != self.cfg.get(key):
                self.cfg[key] = cmd[key]
                changed = True
        if not changed:
            return
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(self.cfg, f, indent=2)
        if self._proc is not None:
            self._proc.terminate()  # _run_loop akan restart otomatis dengan cfg baru

    # ---------- adb polling ----------
    def _get_connected_device(self):
        try:
            result = subprocess.run([ADB_PATH, "devices"], capture_output=True, text=True, timeout=3)
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
                capture_output=True, text=True, timeout=3
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
                                     f"tcp:{self.cfg['port']}", f"tcp:{self.cfg['port']}"])
                    subprocess.run([ADB_PATH, "-s", serial, "reverse",
                                     f"tcp:{self.cfg['control_port']}", f"tcp:{self.cfg['control_port']}"])
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
        self.on_status_change(self._proc is not None, self._usb_connected, self._device_name)

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
        self._notify()

    def _run_loop(self):
        while self._want_running:
            cmd = build_ffmpeg_cmd(self.cfg)  # dibangun ulang tiap iterasi agar setting baru terpakai
            try:
                self._proc = subprocess.Popen(cmd)
                self._notify()
                self._proc.wait()
            except Exception:
                pass
            self._proc = None
            self._notify()
            if self._want_running:
                time.sleep(2)


class App:
    def __init__(self, root):
        self.root = root
        self.cfg = load_config()
        self.tray_icon = None

        root.title("Potato Monitor Desk")
        root.geometry("360x260")
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

    def on_status_change(self, is_streaming, usb_connected, device_name):
        def update():
            self.switch.set_state(is_streaming)
            if usb_connected:
                self.usb_label.config(text="USB: Terhubung", fg="#2e7d32")
                self.device_label.config(text=f"Device: {device_name}")
            else:
                self.usb_label.config(text="USB: Tidak terhubung", fg="#c62828")
                self.device_label.config(text="Device: -")
            self.status_label.config(
                text=f"Status: {'Streaming aktif' if is_streaming else 'Nonaktif'}"
            )
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
