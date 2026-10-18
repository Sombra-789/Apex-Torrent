#define MyAppName "Apex Torrent"
#define MyAppVersion "1.3.8"
#define MyAppPublisher "Apex Software Inc."
#define MyAppExeName "ApexTorrent.exe"
[Setup]
AppId={{88D33E2B-925A-4FE3-BF8D-11F5B4001388}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\ApexTorrent
DefaultGroupName=Apex Software\Apex Torrent
OutputDir=..\release
OutputBaseFilename=ApexTorrent_1.3.8_Setup_x64
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=..\app\assets\apex-torrent.ico
UninstallDisplayIcon={app}\ApexTorrent.exe
WizardStyle=modern
CloseApplications=yes
[Files]
Source: "..\dist\ApexTorrent\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el escritorio"; GroupDescription: "Accesos directos:"; Flags: unchecked
[Icons]
Name: "{group}\Apex Torrent"; Filename: "{app}\ApexTorrent.exe"
Name: "{autodesktop}\Apex Torrent"; Filename: "{app}\ApexTorrent.exe"; Tasks: desktopicon
[Run]
Filename: "{app}\ApexTorrent.exe"; Description: "Iniciar Apex Torrent"; Flags: nowait postinstall skipifsilent
