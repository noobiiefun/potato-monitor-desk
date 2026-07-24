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

REM --windowed   = tidak muncul jendela console hitam (GUI + tray)
REM --icon       = icon.ico dipakai sebagai icon file .exe (taskbar, File Explorer)
REM --add-data   = bundel icon + seluruh folder bin\ (ffmpeg, adb, dll) ke dalam
REM                exe supaya end-user tidak perlu install apa pun secara manual
py -m PyInstaller --onefile --windowed --name PotatoMonitorDeskServer ^
    --icon=icon.ico ^
    --add-data "icon.ico;." ^
    --add-data "icon.png;." ^
    --add-data "bin;bin" ^
    potato_server.py

echo.
echo Selesai. Cek folder dist\PotatoMonitorDeskServer.exe
pause
