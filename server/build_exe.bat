@echo off
REM Jalankan file ini di Command Prompt Windows, di folder yang sama dengan potato_server.py
REM Prasyarat: py -m pip install -r requirements.txt
REM (pakai "py -m pip", bukan "pip" langsung -- lebih reliable terutama kalau
REM  Python di-install lewat "Python Install Manager" versi baru dari python.org)
REM
REM WAJIB sebelum menjalankan file ini: taruh ffmpeg.exe, adb.exe,
REM AdbWinApi.dll, AdbWinUsbApi.dll di folder bin\ (lihat bin\PUT_FFMPEG_ADB_HERE.txt)

if not exist "bin\ffmpeg.exe" (
    echo [!] bin\ffmpeg.exe tidak ditemukan.
    echo     Baca bin\PUT_FFMPEG_ADB_HERE.txt dulu sebelum build.
    pause
    exit /b 1
)
if not exist "bin\adb.exe" (
    echo [!] bin\adb.exe tidak ditemukan.
    echo     Baca bin\PUT_FFMPEG_ADB_HERE.txt dulu sebelum build.
    pause
    exit /b 1
)

REM --onedir     = hasilkan folder (bukan 1 file exe) -- INI PENTING: mode
REM                --onefile lama extract ffmpeg/adb ke folder temp _MEI...
REM                tiap kali dijalankan, dan kalau proses belum benar-benar
REM                lepas saat app ditutup, Windows gagal hapus folder itu
REM                (muncul "Failed to remove temporary directory"). --onedir
REM                taruh semua file permanen di 1 folder, tidak ada extract/
REM                cleanup temp sama sekali, jadi masalah ini hilang total.
REM --windowed   = tidak muncul jendela console hitam (GUI + tray)
REM --icon       = icon.ico dipakai sebagai icon file .exe (taskbar, File Explorer)
REM --add-data   = bundel icon + seluruh folder bin\ (ffmpeg, adb, dll) ke dalam
REM                folder hasil build supaya end-user tidak perlu install apa pun manual
py -m PyInstaller --onedir --windowed --name PotatoMonitorDeskServer ^
    --icon=icon.ico ^
    --add-data "icon.ico;." ^
    --add-data "icon.png;." ^
    --add-data "bin;bin" ^
    potato_server.py

echo.
echo Selesai. Cek folder dist\PotatoMonitorDeskServer\PotatoMonitorDeskServer.exe
pause
