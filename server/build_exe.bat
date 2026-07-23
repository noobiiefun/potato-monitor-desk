@echo off
REM Jalankan file ini di Command Prompt Windows, di folder yang sama dengan potato_server.py
REM Prasyarat: pip install -r requirements.txt

pyinstaller --onefile --console --name PotatoMonitorDeskServer potato_server.py

echo.
echo Selesai. Cek folder dist\PotatoMonitorDeskServer.exe
pause
