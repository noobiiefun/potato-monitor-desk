@echo off
REM Jalankan file ini di Command Prompt Windows, di folder yang sama dengan potato_server.py
REM Prasyarat: py -m pip install -r requirements.txt
REM (pakai "py -m pip", bukan "pip" langsung -- lebih reliable terutama kalau
REM  Python di-install lewat "Python Install Manager" versi baru dari python.org)

REM --windowed   = tidak muncul jendela console hitam (GUI + tray)
REM --icon       = icon.ico dipakai sebagai icon file .exe (taskbar, File Explorer)
REM --add-data   = bundel icon.ico & icon.png ke dalam exe supaya tray icon & window icon
REM                tetap bisa dimuat saat runtime (";." artinya taruh di folder root bundle)
py -m PyInstaller --onefile --windowed --name PotatoMonitorDeskServer ^
    --icon=icon.ico ^
    --add-data "icon.ico;." ^
    --add-data "icon.png;." ^
    potato_server.py

echo.
echo Selesai. Cek folder dist\PotatoMonitorDeskServer.exe
pause
