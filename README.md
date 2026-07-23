# Potato Monitor Desk

Preview layar + suara PC ke HP Android lewat kabel USB — versi ringan ala
spacedesk, tapi **tanpa driver display virtual** (bukan extend monitor asli,
melainkan mirror/preview layar PC ke HP dengan latensi rendah).

Server berjalan di **system tray** (bukan console), dengan window sederhana:
- Saklar ON/OFF untuk mulai/berhenti streaming.
- Status USB: Terhubung / Tidak terhubung (auto update tiap 2 detik).
- Nama device Android yang sedang konek.
- Menutup window (tombol X) hanya minimize ke tray — app tetap jalan di
  background. Klik kanan icon tray untuk buka lagi atau benar-benar Keluar.

> Catatan: membuat HP benar-benar terdeteksi Windows sebagai monitor kedua
> (extend desktop) butuh Indirect Display Driver kernel-mode yang harus
> disertifikasi Microsoft — di luar scope project ringan ini. Yang dilakukan
> di sini adalah mirror layar+audio real-time, bukan extend display.

Arsitektur:

```
Layar & audio PC (gdigrab + Stereo Mix/VB-Cable)
   -> ffmpeg (encode H.264 + AAC, mux MPEG-TS)
   -> TCP server (dikontrol dari GUI tray, potato_server.exe)
   -> adb reverse (tunnel lewat kabel USB, otomatis saat device terdeteksi)
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
1. Sambungkan HP ke PC lewat kabel USB, pastikan USB debugging aktif & sudah
   di-authorize (akan muncul dialog "Allow USB debugging" di HP saat pertama
   kali connect ke PC ini).
2. Jalankan `PotatoMonitorDeskServer.exe`. Window kecil akan muncul:
   - Label **USB** otomatis jadi "Terhubung" + nama device begitu HP terdeteksi
     (adb reverse dipasang otomatis di belakang layar, tidak perlu command manual).
   - Geser **saklar Streaming** ke ON untuk mulai capture layar+audio & kirim
     ke HP. Geser ke OFF untuk berhenti sementara tanpa menutup aplikasi.
3. Tutup window (tombol X) kalau mau app tetap jalan di background — cari
   icon di system tray untuk buka lagi kapan saja, atau klik kanan > Keluar
   untuk benar-benar mematikan aplikasi.
4. Buka app **Potato Monitor Desk** di HP — begitu saklar ON, gambar+suara
   PC langsung tampil di HP.

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
