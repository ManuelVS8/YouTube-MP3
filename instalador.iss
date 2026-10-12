; Instalador de Descargador YouTube (Inno Setup 6)
; Lo compila GitHub Actions automáticamente (ver .github/workflows/compilar.yml)

#define MyAppName "Descargador YouTube"
#define MyAppExe "DescargadorYouTube.exe"
#ifndef AppVersion
  #define AppVersion "1.2"
#endif

[Setup]
AppId={{8E6F2B4A-3C1D-4F5E-9A7B-2D1C0E9F8A61}
AppName={#MyAppName}
AppVersion={#AppVersion}
AppVerName={#MyAppName} {#AppVersion}
AppPublisher=Manuel J. Ventura Sánchez
DefaultDirName={localappdata}\Programs\DescargadorYouTube
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=DescargadorYouTube-Setup
SetupIconFile=icono.ico
UninstallDisplayIcon={app}\{#MyAppExe}
UninstallDisplayName={#MyAppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; Limpia la versión anterior al actualizar
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "dist\DescargadorYouTube\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{userappdata}\DescargadorYouTube"
