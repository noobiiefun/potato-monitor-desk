; Potato Monitor Desk - Server Installer
; Buka file ini dengan Inno Setup Compiler (gratis): https://jrsoftware.org/isinfo.php
; Compile untuk menghasilkan PotatoMonitorDeskServerSetup.exe
;
; Prasyarat sebelum compile:
;   1. Sudah menjalankan build_exe.bat sehingga ada file:
;      dist\PotatoMonitorDeskServer.exe

#define MyAppName "Potato Monitor Desk Server"
#define MyAppVersion "1.0"
#define MyAppPublisher "Potato Monitor Desk"
#define MyAppExeName "PotatoMonitorDeskServer.exe"

[Setup]
AppId={{8F2C1B4A-6E11-4C2F-9C2B-POTATOMONITOR}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\PotatoMonitorDesk
DefaultGroupName=Potato Monitor Desk
DisableProgramGroupPage=yes
OutputBaseFilename=PotatoMonitorDeskServerSetup
SetupIconFile=icon.ico
Compression=lzma
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "dist\PotatoMonitorDeskServer.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Potato Monitor Desk Server"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall Potato Monitor Desk Server"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Potato Monitor Desk Server"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Buat shortcut di Desktop"; GroupDescription: "Additional icons:"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Jalankan Potato Monitor Desk Server sekarang"; Flags: nowait postinstall skipifsilent
