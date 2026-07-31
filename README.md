# Potato Monitor Desk

![Potato Monitor Desk](logo.png)

Preview layar + suara PC ke HP Android lewat kabel USB — versi ringan ala
spacedesk — sekaligus bisa live-streaming tampilan PC itu ke YouTube
langsung dari HP, tanpa aplikasi live-streaming terpisah.

Server berjalan di **system tray** (bukan console), dengan window sederhana:
- Saklar ON/OFF untuk mulai/berhenti streaming.
- Status USB: Terhubung / Tidak terhubung (auto update tiap 2 detik).
- Nama device Android yang sedang konek.
- Pesan error langsung ditampilkan di window (bukan cuma numpang lewat di
  jendela cmd) kalau capture gagal — juga dicatat ke `potato_server.log`.
- Tombol "Cek / pilih device audio..." — cari device audio yang dikenali
  ffmpeg, tinggal klik pilih, tanpa perlu buka Command Prompt manual.
- Centang "Capture window OBS Preview saja" — capture 1 window spesifik
  (mis. Windowed Projector OBS) bukan seluruh layar.
- Field "RTMP URL + Stream Key" — diisi sekali di sini, otomatis terkirim
  ke HP; di HP tinggal toggle switch LIVE tanpa perlu ketik manual.
- Menutup window (tombol X) hanya minimize ke tray — app tetap jalan di
  background. Klik kanan icon tray untuk buka lagi atau benar-benar Keluar.

## Kenapa arsitekturnya begini (PC ringan, HP yang encode)

PC lama/kentang biasanya cuma punya opsi **encoder software H.264 (x264)**
di OBS — ini berat di CPU tua dan bikin live streaming patah-patah. Jadi
desainnya dibalik:

```
Layar & audio PC (gdigrab -- desktop ATAU 1 window spesifik seperti OBS
Windowed Projector, + dshow audio dari Stereo Mix/VB-Cable)
   -> ffmpeg #1: capture video -> MJPEG (JPEG per-frame, MURAH di CPU --
      tanpa motion estimation seperti H.264)
   -> ffmpeg #2: capture audio -> AAC ADTS (encode audio memang selalu
      murah, bukan sumber beban)
   -> FramedBroadcastServer (Python, port 9999): bungkus tiap frame video/
      audio jadi 1 paket kecil [type][length][payload], broadcast ke SEMUA
      klien yang connect bersamaan. Tiap klien punya antrian + thread
      pengirim sendiri -- klien yang lambat cuma kehilangan frame lama
      (di-drop), TIDAK bikin klien lain atau capture di PC ikut ketahan.
   -> adb reverse (tunnel lewat kabel USB, otomatis saat device terdeteksi)
   -> Android app, 2 konsumen paralel dari koneksi TCP yang sama:
        a) MjpegPreviewEngine: decode JPEG, tampil di ImageView (preview
           layar HP) -- video saja, TANPA audio (sengaja, biar tidak ada
           risiko gema mic dari speaker HP)
        b) RelayStreamService: decode tiap JPEG -> gambar ulang ("draw")
           ke Surface input encoder H.264 HARDWARE Android (H264SurfaceEncoder,
           chip khusus, bukan software) -> encoded H.264 + audio AAC
           (passthrough, tinggal strip header ADTS) dikirim ke RTMP lewat
           com.pedro.rtmp.rtmp.RtmpClient (RootEncoder), TANPA MediaProjection
           dan TANPA merekam layar HP sama sekali.
```

Poin penting:
- **PC tidak pernah encode H.264.** Cuma JPEG (ringan) + AAC.
- **HP yang encode H.264**, tapi pakai chip hardware khusus (MediaCodec),
  jauh lebih murah dari software x264 di PC tua.
- Live ke YouTube **bukan** hasil rekam layar HP — preview di layar HP dan
  proses live itu 2 jalur terpisah, sama-sama independen dari koneksi TCP
  yang sama ke PC.

Project ini punya 2 bagian:

- `server/` — Python, di-build jadi `.exe` + installer Windows.
- `client/` — Android Studio project (Kotlin), pakai `com.pedro:rootencoder`
  untuk RTMP dan `android.media.MediaCodec` untuk hardware H.264 encode.

---

## 1. Build Server (Windows)

`ffmpeg` dan `adb` **dibundel langsung ke dalam installer** — end user
tinggal jalankan installer-nya, tidak perlu install atau atur PATH manual.

### Prasyarat (hanya untuk build, bukan untuk end-user)
1. Install **Python 3.10+** (centang "Add to PATH" saat install).
2. Download 4 file berikut, taruh di folder `server/bin/` (baca
   `server/bin/PUT_FFMPEG_ADB_HERE.txt` untuk link & detailnya):
   `ffmpeg.exe`, `adb.exe`, `AdbWinApi.dll`, `AdbWinUsbApi.dll`.
   Dilakukan **sekali saja**, tidak perlu diulang tiap build ulang.
3. Install Inno Setup untuk bikin installer: https://jrsoftware.org/isdl.php
4. Aktifkan audio loopback di PC (WAJIB, tanpa ini fitur audio tidak jalan):
   - Cek dulu apakah PC kamu punya **Stereo Mix**: klik kanan icon speaker
     > Sound settings > More sound settings > tab Recording > klik kanan
     area kosong > "Show Disabled Devices" > enable **Stereo Mix** kalau
     muncul.
   - Kalau **tidak ada Stereo Mix** (umum di PC/laptop yang pakai driver
     audio generik, bukan Realtek/manufaktur asli): install
     **VB-Audio Virtual Cable** (gratis, vb-audio.com/Cable), restart PC.
     Lalu di Sound settings > Output, set **"CABLE Input (VB-Audio Virtual
     Cable)"** sebagai default output. Supaya kamu TETAP dengar suara game
     sendiri (bukan cuma ke-capture doang): Sound settings > Recording >
     klik kanan **CABLE Output** > Properties > tab Listen > centang
     "Listen to this device" > pilih speaker/headset asli kamu.
   > Ini satu-satunya langkah yang tidak bisa diotomatisasi, karena
   > tergantung driver audio masing-masing PC.

### Langkah build

```bat
cd server
py -m pip install -r requirements.txt
build_exe.bat
```

`build_exe.bat` otomatis cek dulu apakah `bin\ffmpeg.exe` dan `bin\adb.exe`
sudah ada — kalau belum, akan berhenti dan mengingatkan.

> **Kalau muncul error `'pip' is not recognized...`**: pakai `py -m pip ...`
> (bukan `pip ...` langsung). Kalau `py` juga belum kedetect, buka Command
> Prompt **baru** (tutup yang lama) supaya PATH ter-refresh.

> **Kalau muncul `PermissionError: Access is denied` pas build**: pastikan
> `PotatoMonitorDeskServer.exe` hasil build sebelumnya sudah benar-benar
> ditutup (cek system tray, klik kanan > Keluar — bukan cuma tutup window-nya,
> karena itu cuma minimize ke tray) sebelum build ulang.

Hasil: `server\dist\PotatoMonitorDeskServer.exe` — self-contained, tidak
butuh dependency eksternal apa pun lagi.

### Build installer

Buka `server\installer.iss` dengan **Inno Setup Compiler**, klik Compile.
Hasil: `Output\PotatoMonitorDeskServerSetup.exe` — Next → Next → Finish,
otomatis bikin shortcut Start Menu & Desktop.

### Isi `config.json`

Dibuat otomatis saat pertama kali dijalankan, berisi:
```json
{
  "audio_device": "CABLE Output (VB-Audio Virtual Cable)",
  "resolution": "1280x720",
  "framerate": 30,
  "jpeg_quality": 6,
  "audio_bitrate": "128k",
  "port": 9999,
  "control_port": 9998,
  "capture_mode": "desktop",
  "capture_window_title": "Windowed Projector (Preview)",
  "rtmp_url": ""
}
```
- `audio_device` — pakai tombol "Cek / pilih device audio..." di app,
  jangan edit manual kecuali tahu persis nama device-nya.
- `jpeg_quality` — skala ffmpeg `-q:v`: **2 = kualitas terbaik/paling
  berat, 31 = paling jelek/paling ringan**. Naikkan angka ini (mis. ke 10-15)
  kalau CPU masih kerasa berat meski sudah MJPEG.
- `capture_mode`: `"desktop"` (seluruh layar) atau `"window"` (1 window
  spesifik, judulnya di `capture_window_title`) — bisa juga diatur lewat
  checkbox di window app, tidak perlu edit `config.json` manual.
- `rtmp_url` — RTMP URL + stream key gabung jadi satu (mis.
  `rtmp://a.rtmp.youtube.com/live2/<key>`) — bisa diisi lewat field di
  window app, otomatis terkirim ke HP lewat `control_port` (9998) setiap
  kali HP connect, jadi tidak perlu diketik manual di HP.
- `port` — port stream (video+audio), melayani banyak koneksi sekaligus
  (preview + relay live jalan bersamaan) lewat `FramedBroadcastServer`.

### Menjalankan
1. Sambungkan HP ke PC lewat kabel USB, USB debugging aktif & sudah
   di-authorize.
2. Jalankan `PotatoMonitorDeskServer.exe`.
3. Klik **"Cek / pilih device audio..."** kalau belum pernah, pilih device
   yang sesuai (VB-Cable/Stereo Mix).
4. (Opsional) Kalau mau cuma capture window OBS: buka OBS, klik kanan
   Preview > **Windowed Projector (Preview)**, lalu centang "Capture
   window OBS Preview saja" di app (judulnya sudah default sesuai nama
   window itu).
5. (Opsional) Isi field **RTMP URL + Stream Key** kalau mau live ke YouTube
   langsung dari HP tanpa ketik manual di HP.
6. Geser **saklar Streaming** ke ON.
7. Buka app **Potato Monitor Desk** di HP — gambar+suara PC langsung tampil.

---

## 2. Build Client (Android)

### Setup signing (sekali saja, sebelum build release)
APK release **wajib** ditandatangani dengan keystore rilis sendiri (bukan
debug key) — APK bertanda debug key adalah salah satu sinyal terbesar yang
bikin Google Play Protect menganggap app "tidak dikenal/berisiko" saat
sideload. Sudah disiapkan `keystore.properties.example` di root `client/`:
1. Generate keystore (sekali saja):
   ```bash
   keytool -genkeypair -v -keystore app/release-keystore.jks \
     -alias potato-monitor-desk -keyalg RSA -keysize 2048 -validity 10000
   ```
2. Copy `keystore.properties.example` jadi `keystore.properties`, isi
   password & alias sesuai yang kamu pakai di atas.
3. **Jangan pernah commit** `keystore.properties` atau `*.jks` ke git —
   sudah masuk `.gitignore`, tapi tetap dicek ulang sebelum push.

Build release APK: `Build > Generate Signed Bundle/APK` di Android Studio,
atau `./gradlew assembleRelease`.

### Langkah build
1. Buka **Android Studio** > Open > pilih folder `client/`.
2. Biarkan Gradle sync selesai (download dependency RootEncoder buat RTMP,
   perlu koneksi internet saat build pertama kali).
3. Sambungkan HP Android (USB debugging aktif) atau pakai emulator.
4. Klik Run ▶ untuk install & buka app "Potato Monitor Desk" di HP.

App otomatis connect ke `127.0.0.1:9999` (diteruskan lewat `adb reverse`
yang dipasang otomatis oleh server) begitu dibuka, dan otomatis ambil RTMP
URL yang diisi di server lewat `127.0.0.1:9998`.

---

## Live streaming langsung dari app

**Cara pakai:**
1. Isi **RTMP URL + Stream Key** di window server (paling gampang — otomatis
   terkirim ke HP), atau isi manual di HP lewat ⚙ **Pengaturan** >
   **Pengaturan Live** kalau mau override.
2. Nyalakan switch **LIVE** di pojok kanan atas. Tidak ada dialog izin
   capture layar sama sekali (tidak pakai `MediaProjection`) — app langsung
   decode stream dari PC dan encode ulang jadi H.264 pakai hardware encoder
   HP, lalu kirim ke RTMP.
3. Live dimulai: badge **🔴 LIVE 00:00:xx** muncul dan bertambah tiap detik.
4. Matikan switch **LIVE** kapan saja untuk stop tanpa menutup app. Preview
   layar boleh tetap dibuka atau di-minimize — dua-duanya jalan independen.

Audio yang terkirim ke live adalah audio yang di-capture di PC (Stereo
Mix/VB-Cable) — bukan mikrofon HP dan bukan audio internal HP.

> Catatan teknis: `H264SurfaceEncoder` (MediaCodec, hardware) encode video
> dari Surface yang digambar tiap JPEG masuk; `RtmpRelayEngine` kirim hasil
> encode + audio AAC (passthrough, cuma strip header ADTS) ke RTMP lewat
> `com.pedro.rtmp.rtmp.RtmpClient` (RootEncoder, level rendah — bukan lewat
> `RtmpDisplay`/`MediaProjection`).

---

## Fitur client (HP)

Tekan ikon gear (⚙) di pojok kanan atas untuk membuka menu:

- **Pengaturan Live** — override RTMP URL manual kalau perlu (biasanya
  tidak perlu, karena sudah otomatis dari server), pilih posisi timer LIVE.

> Fitur "Kualitas Streaming" (ganti resolusi/bitrate dari HP) dan
> "Aplikasi yang Disunyikan" (mute notifikasi) dari versi sebelumnya
> **sudah tidak ada** di arsitektur saat ini — kualitas sekarang diatur di
> `config.json`/window server (`jpeg_quality`, `resolution`, `framerate`).
> Kalau butuh salah satu fitur ini dihidupkan lagi, kabari untuk dibangun
> ulang menyesuaikan arsitektur baru.

**Minimize / Picture-in-Picture**: tombol minimize (pojok kanan atas) atau
tombol Home akan mengecilkan app jadi floating window kecil yang tetap
menampilkan preview sambil kamu buka app lain.

---

## Catatan & tuning

- **Latensi**: kalau gambar patah-patah atau delay, coba naikkan
  `jpeg_quality` (lebih ringan) atau turunkan `resolution`/`framerate` di
  `config.json`. Broadcast server sudah didesain non-blocking (klien lambat
  otomatis kehilangan frame lama, bukan bikin capture di PC ikut ketahan),
  tapi kalau HP-nya sendiri terlalu lemah buat decode+encode secepat FPS
  yang dikirim, tetap akan ada backlog di sisi HP.
- **Kualitas vs kabel**: karena lewat USB (bukan WiFi), throughput jauh
  lebih stabil dari WiFi/internet — aman naikkan kualitas kalau kabel & port
  USB mendukung, PC & HP masih sanggup.
- **Capture window OBS spesifik**: centang di app, isi judul window persis
  (klik kanan Preview OBS > Windowed Projector (Preview) untuk buka
  window-nya duluan).
- **Multi-device**: saat ini didesain untuk 1 HP per server (1 port stream
  + 1 port kontrol). Untuk banyak HP sekaligus, jalankan beberapa instance
  server dengan `port`/`control_port` berbeda per instance, dan pastikan
  `adb -s <serial> reverse ...` dipasang untuk device masing-masing.

---

## Logo & icon

Semua aset di bawah sudah digenerate dari `logo.png` (logo utama) dan sudah
otomatis terpakai — tidak perlu diedit manual kecuali mau ganti desain:

- `server/icon.ico` — icon file `.exe`, taskbar, dan shortcut installer.
- `server/icon.png` — dipakai runtime untuk tray icon & title bar window.
- `client/app/src/main/res/mipmap-*/ic_launcher.png` (+ `_round`) — icon app
  di launcher HP, sudah digenerate untuk semua density (mdpi–xxxhdpi).
- `client/app/src/main/res/drawable/potato_logo.png` — ditampilkan di
  `SplashActivity` (splash screen ~1.2 detik) sebelum masuk ke layar utama.

Kalau nanti ganti logo, tinggal replace `logo.png` di root project lalu
generate ulang turunannya (resize ke ukuran yang sama seperti di atas) — atau
minta saya bantu generate ulang.
