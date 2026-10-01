; IP-Analyzer.iss - Inno Setup script para IP Analyzer
; Compilar: ISCC.exe /DMyAppVersion=2.2.0 scripts\IP-Analyzer.iss

#ifndef MyAppVersion
  #define MyAppVersion "2.2.0"
#endif

#define MyAppName "IP Analyzer"
#define MyAppShort "IP-Analyzer"
#define MyAppPublisher "Diego A. Rabalo"
#define MyAppURL "https://github.com/mikear/IP-Analyzer"
#define MyAppExeName "IP-Analyzer.exe"
#define MyCliExeName "ip-analyzer-cli.exe"
#define PayloadDir "..\dist\IP-Analyzer"

[Setup]
AppId={{5A7C3D9E-1B4F-4E2A-9C6D-8F1E2A3B4C5D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} v{#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
AppCopyright=(c) {#MyAppPublisher} - Licencia MIT

VersionInfoVersion={#MyAppVersion}
VersionInfoProductVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=Instalador de {#MyAppName}
VersionInfoProductName={#MyAppName}
VersionInfoProductTextVersion={#MyAppVersion}

DefaultDirName={autopf}\{#MyAppShort}
DisableProgramGroupPage=yes
DefaultGroupName={#MyAppName}

PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline

OutputDir=..\dist
OutputBaseFilename=IP-Analyzer-Setup-v{#MyAppVersion}-win64
SetupIconFile=..\assets\app_icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}

Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
ChangesAssociations=no
ChangesEnvironment=no
CloseApplications=yes
RestartApplications=yes
DisableDirPage=no
DisableReadyPage=no
SetupLogging=yes

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#PayloadDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs restartreplace

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Comment: "{#MyAppName} v{#MyAppVersion} - analisis forense de IPs"
Name: "{group}\{#MyAppName} (CLI)"; Filename: "{app}\{#MyCliExeName}"; WorkingDir: "{app}"; Comment: "{#MyAppName} - linea de comandos"
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"; Comment: "Desinstalar {#MyAppName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\{#MyAppShort}"; ValueType: string; ValueName: "InstallLocation"; ValueData: "{app}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\{#MyAppShort}"; ValueType: string; ValueName: "Version"; ValueData: "{#MyAppVersion}"
Root: HKA; Subkey: "Software\{#MyAppShort}"; ValueType: string; ValueName: "InstalledBySetup"; ValueData: "1"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Lanzar {#MyAppName}"; Flags: nowait postinstall skipifsilent unchecked; WorkingDir: "{app}"

[UninstallRun]
Filename: "{cmd}"; Parameters: "/C taskkill /F /IM {#MyAppExeName}"; Flags: runhidden waituntilterminated; RunOnceId: "KillGUI"
Filename: "{cmd}"; Parameters: "/C taskkill /F /IM {#MyCliExeName}"; Flags: runhidden waituntilterminated; RunOnceId: "KillCLI"

[UninstallDelete]
Type: files; Name: "{app}\.env"
Type: filesandordirs; Name: "{app}\__pycache__"
Type: files; Name: "{app}\Thumbs.db"
Type: files; Name: "{app}\desktop.ini"
Type: filesandordirs; Name: "{app}\_internal"
