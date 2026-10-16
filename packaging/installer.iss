; Inno Setup script - compile after build_windows.ps1
[Setup]
AppName=WooDesk
AppVersion=1.0.2
DefaultDirName={autopf}\WooDesk
DefaultGroupName=WooDesk
OutputBaseFilename=WooDesk-Setup
Compression=lzma2
SolidCompression=yes
OutputDir=..\dist
[Files]
Source: "..\dist\WooDesk\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
[Icons]
Name: "{group}\WooDesk"; Filename: "{app}\WooDesk.exe"
Name: "{autodesktop}\WooDesk"; Filename: "{app}\WooDesk.exe"
[Run]
Filename: "{app}\WooDesk.exe"; Description: "Launch WooDesk"; Flags: nowait postinstall skipifsilent
