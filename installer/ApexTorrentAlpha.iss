#define MyAppName "Apex Torrent Alpha"
#define MyAppVersion "1.4.0-alpha.1"
#define MyAppPublisher "Apex Software"
#define MyAppExeName "ApexTorrentAlpha.exe"
[Setup]
AppId={{5CA855CA-7E5E-4B15-881E-68D05538E135}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\ApexTorrentAlpha
DefaultGroupName=Apex Software\Apex Torrent Alpha
OutputDir=..\release
OutputBaseFilename=ApexTorrent_1.4.0_alpha1_Setup_x64
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=..\app\assets\apex-torrent.ico
UninstallDisplayIcon={app}\ApexTorrentAlpha.exe
WizardStyle=modern
CloseApplications=yes
[Files]
Source: "..\dist\ApexTorrentAlpha\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo Alpha en el escritorio"; GroupDescription: "Accesos directos:"; Flags: unchecked
[Icons]
Name: "{group}\Apex Torrent Alpha"; Filename: "{app}\ApexTorrentAlpha.exe"
Name: "{autodesktop}\Apex Torrent Alpha"; Filename: "{app}\ApexTorrentAlpha.exe"; Tasks: desktopicon
[Run]
Filename: "{app}\ApexTorrentAlpha.exe"; Description: "Iniciar Apex Torrent Alpha"; Flags: nowait postinstall skipifsilent
