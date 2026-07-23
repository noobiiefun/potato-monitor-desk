"""
Potato Monitor Desk - Server
Menangkap layar + audio PC (Windows), encode H.264/AAC via ffmpeg,
lalu di-stream lewat TCP ke HP Android via kabel USB (adb reverse).

Prasyarat di PC:
  1. ffmpeg terpasang dan ada di PATH  -> https://ffmpeg.org/download.html
  2. Android Platform Tools (adb) ada di PATH -> https://developer.android.com/tools/releases/platform-tools
  3. USB debugging aktif di HP, kabel USB terpasang & sudah authorize adb
  4. Audio device loopback aktif di Windows:
       - Cara termudah: aktifkan "Stereo Mix" di Sound Settings > Recording
         (klik kanan area kosong > Show Disabled Devices > enable Stereo Mix)
       - Kalau kartu suara tidak punya Stereo Mix, install VB-Audio Virtual Cable
         (gratis) dan set sebagai default playback/recording sesuai kebutuhan.
"""

import subprocess
import sys
import time
import shutil
import json
import os

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "config.json")

DEFAULT_CONFIG = {
    "audio_device": "Stereo Mix (Realtek Audio)",
    "video_bitrate": "3M",
    "audio_bitrate": "128k",
    "port": 9999,
    "resolution": "1280x720",
    "framerate": 30
}


def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        merged = {**DEFAULT_CONFIG, **cfg}
        return merged
    else:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
        print("[i] config.json dibuat dengan nilai default.")
        print("[i] Edit 'audio_device' di config.json sesuai nama device audio di PC-mu.")
        print("[i] Jalankan 'potato_server.exe --list-devices' untuk melihat daftar device.")
        return DEFAULT_CONFIG


def check_ffmpeg():
    if shutil.which("ffmpeg") is None:
        print("[!] ffmpeg tidak ditemukan di PATH.")
        print("    Download dari https://ffmpeg.org/download.html lalu tambahkan folder bin-nya ke PATH.")
        sys.exit(1)


def check_adb_and_reverse(port):
    if shutil.which("adb") is None:
        print("[!] adb tidak ditemukan di PATH.")
        print("    Download Android Platform Tools dan tambahkan ke PATH.")
        sys.exit(1)

    result = subprocess.run(["adb", "devices"], capture_output=True, text=True)
    lines = [l for l in result.stdout.splitlines()[1:] if l.strip()]
    if not lines:
        print("[!] Tidak ada device Android terdeteksi.")
        print("    Pastikan USB debugging aktif, kabel terpasang, dan sudah tap 'Allow' di HP.")
        sys.exit(1)

    print("[i] Device terdeteksi:")
    print(result.stdout.strip())

    subprocess.run(["adb", "reverse", f"tcp:{port}", f"tcp:{port}"], check=True)
    print(f"[i] adb reverse tcp:{port} <-> tcp:{port} berhasil dipasang lewat USB.")


def list_dshow_devices():
    print("[i] Daftar device audio/video DirectShow yang terdeteksi ffmpeg:\n")
    subprocess.run(["ffmpeg", "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"])


def build_ffmpeg_cmd(cfg):
    w, h = cfg["resolution"].split("x")
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "warning",
        "-f", "gdigrab", "-framerate", str(cfg["framerate"]), "-i", "desktop",
        "-f", "dshow", "-i", f"audio={cfg['audio_device']}",
        "-vf", f"scale={w}:{h}",
        "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
        "-b:v", cfg["video_bitrate"], "-pix_fmt", "yuv420p", "-g", str(cfg["framerate"]),
        "-c:a", "aac", "-b:a", cfg["audio_bitrate"], "-ar", "44100",
        "-f", "mpegts", f"tcp://0.0.0.0:{cfg['port']}?listen=1"
    ]
    return cmd


def main():
    print("=== Potato Monitor Desk - Server ===\n")

    if len(sys.argv) > 1 and sys.argv[1] == "--list-devices":
        check_ffmpeg()
        list_dshow_devices()
        return

    check_ffmpeg()
    cfg = load_config()
    check_adb_and_reverse(cfg["port"])

    cmd = build_ffmpeg_cmd(cfg)
    print("\n[i] Menjalankan ffmpeg dengan perintah:")
    print(" ".join(cmd))
    print(f"\n[i] Buka aplikasi 'Potato Monitor Desk' di HP untuk mulai preview.")
    print("[i] Tekan Ctrl+C untuk berhenti server.\n")

    while True:
        try:
            subprocess.run(cmd)
            print("[i] Koneksi client terputus / ffmpeg berhenti. Mencoba ulang dalam 2 detik...")
            time.sleep(2)
        except KeyboardInterrupt:
            print("\n[i] Server dihentikan oleh user.")
            break
        except Exception as e:
            print(f"[!] Error: {e}. Mencoba ulang dalam 3 detik...")
            time.sleep(3)


if __name__ == "__main__":
    main()
