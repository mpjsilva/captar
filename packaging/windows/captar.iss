; Instalador do Captar para Windows 10/11 x64 (Inno Setup 6).
; Uso: iscc /DMyVersion=2.1.0 packaging\windows\captar.iss

#ifndef MyVersion
  #define MyVersion "0.0.0"
#endif

[Setup]
AppId={{6F0B5E7A-2C1D-4C8B-9E55-CA97A0C0FFEE}
AppName=Captar
AppVersion={#MyVersion}
AppPublisher=mpjsilva
AppPublisherURL=https://github.com/mpjsilva/captar
AppSupportURL=https://github.com/mpjsilva/captar/issues
AppUpdatesURL=https://github.com/mpjsilva/captar/releases
DefaultDirName={autopf}\Captar
DefaultGroupName=Captar
DisableProgramGroupPage=yes
; Instala só para o usuário: sem UAC, e o atualizador automático roda calado.
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\..\dist
OutputBaseFilename=captar-{#MyVersion}-setup-x64
SetupIconFile=captar.ico
UninstallDisplayIcon={app}\Captar.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
LicenseFile=..\..\LICENSE

[Languages]
Name: "ptbr"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "startup"; Description: "Iniciar o Captar com o Windows"; GroupDescription: "Opções:"
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\..\dist\Captar\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Captar"; Filename: "{app}\Captar.exe"
Name: "{group}\Desinstalar o Captar"; Filename: "{uninstallexe}"
Name: "{userdesktop}\Captar"; Filename: "{app}\Captar.exe"; Tasks: desktopicon
Name: "{userstartup}\Captar"; Filename: "{app}\Captar.exe"; Tasks: startup

[Run]
Filename: "{app}\Captar.exe"; Description: "{cm:LaunchProgram,Captar}"; Flags: nowait postinstall

[UninstallRun]
Filename: "taskkill.exe"; Parameters: "/F /IM Captar.exe"; Flags: runhidden; RunOnceId: "KillCaptar"
