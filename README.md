# Potato Monitor Desk

Preview layar OBS (video + audio) dari PC ke HP Android lewat kabel USB —
versi ringan tanpa driver display virtual seperti spacedesk.

Arsitektur:

```
OBS Virtual Camera (video) + Stereo Mix / VB-Cable (audio)
   -> ffmpeg (encode H.264 + AAC, mux MPEG-TS)
   -> TCP server (potato_server.exe)
   -> adb reverse (tunnel lewat kabel USB)
   -> Android app (ExoPlayer decode + render)
```

Project ini punya 2 bagian:

- `server/` — Python, di-build jadi `.exe` + installer Windows.
- `client/` — Android Studio project (Kotlin + Media3 ExoPlayer).

---

## 1. Build Server (Windows)

### Prasyarat
1. Install **Python 3.10+** (centang "Add to PATH" saat install).
2. Install **ffmpeg** dan tambahkan folder `bin`-nya ke PATH sistem.
   Cek dengan buka Command Prompt lalu ketik `ffmpeg -version`.
3. Install **Android Platform Tools** (berisi `adb`) dan tambahkan ke PATH.
   Cek dengan `adb version`.
4. Aktifkan audio loopback:
   - Klik kanan icon speaker > Sound settings > More sound settings >
     tab Recording > klik kanan area kosong > "Show Disabled Devices" >
     enable **Stereo Mix** (kalau ada).
   - Kalau tidak ada Stereo Mix, install **VB-Audio Virtual Cable** (gratis)
     dan set sebagai default output, lalu pakai itu sebagai `audio_device`.
5. (Opsional, untuk build .exe) install Inno Setup:
   https://jrsoftware.org/isdl.php

### Langkah build

```bat
cd server
pip install -r requirements.txt
build_exe.bat
```

Hasil: `server\dist\PotatoMonitorDeskServer.exe`

### Build installer (opsional)
Buka `server\installer.iss` dengan **Inno Setup Compiler**, klik Compile.
Hasil: `Output\PotatoMonitorDeskServerSetup.exe`

### Sebelum jalan pertama kali
Cek nama device audio yang benar:
```bat
PotatoMonitorDeskServer.exe --list-devices
```
Salin nama device audio yang muncul (mis. `Stereo Mix (Realtek Audio)`)
ke `config.json` yang otomatis dibuat di folder yang sama, field `audio_device`.

### Menjalankan
1. Buka **OBS** > Start Virtual Camera (agar preview OBS jadi "kamera" yang bisa
   ditangkap ffmpeg — atau langsung capture layar penuh, sudah default lewat
   `gdigrab`, sesuaikan kalau ingin capture window OBS spesifik saja).
2. Sambungkan HP ke PC lewat kabel USB, pastikan USB debugging aktif.
3. Jalankan `PotatoMonitorDeskServer.exe`.
   Script otomatis: cek ffmpeg & adb, deteksi HP, pasang `adb reverse`,
   lalu mulai streaming dan menunggu koneksi dari app Android.

---

## 2. Build Client (Android)

1. Buka **Android Studio** > Open > pilih folder `client/`.
2. Biarkan Gradle sync selesai (akan download dependency Media3 ExoPlayer,
   perlu koneksi internet saat build pertama kali).
3. Sambungkan HP Android (USB debugging aktif) atau pakai emulator.
4. Klik Run ▶ untuk install & buka app "Potato Monitor Desk" di HP.

App akan otomatis connect ke `127.0.0.1:9999` (diteruskan lewat `adb reverse`
yang dipasang otomatis oleh server) begitu dibuka. Kalau server belum jalan,
tampil status "Menghubungkan..." dan tombol **Reconnect** untuk coba lagi.

---

## Catatan & tuning

- **Latensi**: default preset `ultrafast` + `zerolatency` untuk latensi rendah.
  Kalau gambar patah-patah, turunkan `resolution` atau `video_bitrate` di
  `config.json` (mis. `960x540`, bitrate `1.5M`).
- **Kualitas vs kabel**: karena lewat USB (bukan WiFi), throughput jauh lebih
  stabil — aman naikkan bitrate kalau kabel & port USB mendukung.
- **Capture window OBS spesifik** (bukan seluruh layar): ganti input `gdigrab`
  di `build_ffmpeg_cmd()` dari `-i desktop` jadi `-i title=<judul window OBS>`.
- **Multi-device**: saat ini didesain untuk 1 HP per server (satu port TCP).
  Untuk banyak HP sekaligus, jalankan beberapa instance server dengan port
  berbeda + `adb reverse` per device (`adb -s <serial> reverse ...`).
