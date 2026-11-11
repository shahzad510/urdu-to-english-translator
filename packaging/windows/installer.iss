; Inno Setup script for the offline Windows 10 x64 installer.
; The Gemma GGUF model is not installed by this script.
; User history and configuration under {%LOCALAPPDATA}\UrduTranslator are kept
; on upgrade and are not removed by uninstall.

#define MyAppName "Urdu Translator"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "UrduTranslator"
#define MyAppExeName "UrduTranslator.exe"
#define MyAppIcon "assets\UrduTranslator.ico"

[Setup]
AppId={{7C3E9A21-4B6D-4E1A-9F2C-8D5A1B0E6C44}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\Urdu Translator
DefaultGroupName=Urdu Translator
DisableProgramGroupPage=yes
OutputDir=output
OutputBaseFilename=UrduTranslator-Setup-1.0.0-x64
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=admin
SetupIconFile={#MyAppIcon}
UninstallDisplayIcon={app}\{#MyAppExeName}
SetupLogging=no
; Installation does not contact the network.

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
; Application directory produced by PyInstaller. Do not add a .gguf file here.
Source: "dist\UrduTranslator\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Urdu Translator"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Urdu Translator"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Urdu Translator"; Flags: nowait postinstall skipifsilent

; Uninstall removes only the Program Files copy of the application.
; {%LOCALAPPDATA}\UrduTranslator is not an install folder, so history,
; configuration, logs, and a copied model remain after uninstall and upgrade.
