@echo off
REM Jalankan file ini di Command Prompt Windows, di folder yang sama dengan potato_server.py
REM Prasyarat: pip install -r requirements.txt

REM --windowed   = tidak muncul jendela console hitam (GUI + tray)
REM --icon       = icon.ico dipakai sebagai icon file .exe (taskbar, File Explorer)
REM --add-data   = bundel icon.ico & icon.png ke dalam exe supaya tray icon & window icon
REM                tetap bisa dimuat saat runtime (";." artinya taruh di folder root bundle)
pyinstaller --onefile --windowed --name PotatoMonitorDeskServer ^
    --icon=icon.ico ^
    --add-data "icon.ico;." ^
    --add-data "icon.png;." ^
    potato_server.py

echo.
echo Selesai. Cek folder dist\PotatoMonitorDeskServer.exe
pause
