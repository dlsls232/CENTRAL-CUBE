; CENTRAL CUBE installer template.
; Build the EXE files first using scripts\build_windows.bat.
#define MyAppName "CENTRAL CUBE"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "CENTRAL CUBE"

[Setup]
AppId={{A3B5B02C-9D7D-4E90-A54B-CC0A4B0D9A01}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\CENTRAL CUBE
DefaultGroupName=CENTRAL CUBE
OutputDir=..\dist-installer
OutputBaseFilename=CentralCube-Setup-{#MyAppVersion}
ArchitecturesInstallIn64BitMode=x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\assets\central_cube.ico
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\CentralCube.exe
AppComments=Secure direct computer management over mutually authenticated TLS

[Files]
Source: "..\dist\CentralCube\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
Source: "..\dist\CentralCubeAgent\*"; DestDir: "{app}\Agent"; Flags: recursesubdirs ignoreversion
Source: "..\scripts\*.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\docs\*"; DestDir: "{app}\docs"; Flags: ignoreversion

[Icons]
Name: "{group}\CENTRAL CUBE"; Filename: "{app}\CentralCube.exe"
Name: "{autodesktop}\CENTRAL CUBE"; Filename: "{app}\CentralCube.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительные значки:"
