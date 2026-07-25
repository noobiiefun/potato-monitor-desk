# Implementation Plan - Prevent Play Protect Blocking

Aplikasi Anda masih diblokir oleh Play Protect kemungkinan besar karena kombinasi dari izin sensitif (`MediaProjection`, `Record Audio`, `Notification Listener`) dan penandatanganan APK yang belum resmi (masih menggunakan *debug key*).

## User Review Required

> [!IMPORTANT]
> **Penandatanganan APK (Signing)**: Untuk melewati blokir Play Protect, Anda **WAJIB** membuat file keystore asli (`.jks`) dan mengisi `keystore.properties`. Menggunakan *debug key* pada build "Release" adalah pemicu utama Play Protect menganggap aplikasi tersebut mencurigakan.

> [!WARNING]
> **Versi AGP**: Anda mengubah versi plugin Android Gradle ke `8.13.2`. Versi ini tidak umum (kemungkinan typo dari `8.3.2` atau `8.5.2`). Saya menyarankan untuk menggunakan versi stabil yang terverifikasi.

## Proposed Changes

### Build Configuration

#### [MODIFY] [build.gradle](file:///F:/coding/potato-monitor-desk/client/build.gradle)
- Koreksi versi Android Gradle Plugin ke versi stabil (misal `8.5.0`).

#### [MODIFY] [app/build.gradle](file:///F:/coding/potato-monitor-desk/client/app/build.gradle)
- Aktifkan `minifyEnabled true` dan `shrinkResources true` pada build `release`. Ini membuat aplikasi lebih ramping dan terlihat seperti aplikasi produksi profesional di mata algoritma Play Protect.

### Manifest and Resources

#### [MODIFY] [AndroidManifest.xml](file:///F:/coding/potato-monitor-desk/client/app/src/main/AndroidManifest.xml)
- Tambahkan metadata pendukung dan pastikan semua deklarasi layanan sudah optimal.
- Pastikan `android:allowBackup="false"` jika tidak diperlukan, untuk meningkatkan profil keamanan aplikasi.

#### [MODIFY] [strings.xml](file:///F:/coding/potato-monitor-desk/client/app/src/main/res/values/strings.xml)
- Tambahkan deskripsi aplikasi yang lebih mendalam untuk ditampilkan di pengaturan sistem.

## Verification Plan

### Automated Tests
- Menjalankan `gradle_sync` untuk memastikan versi plugin valid.
- Menjalankan `./gradlew assembleRelease` untuk memastikan build berhasil dengan optimasi R8.

### Manual Verification
- Pengguna harus memastikan file `release-keystore.jks` dan `keystore.properties` sudah ada di folder root sebelum melakukan build final.
