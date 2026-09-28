; Windows installer for the YAMS PyInstaller onedir bundle.
; Build from the repository root with:
; ISCC.exe /DMyAppVersion=<version> packaging\windows\yams_installer.iss

#define MyAppName "YAMS"
#define MyAppPublisher "SenSE Lab, OSU"
#define MyAppURL "https://github.com/SenSE-Lab-OSU/YAMS"
#define MyAppExeName "YAMS_Windows_x64.exe"
#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

[Setup]
; This GUID belongs only to YAMS and must remain stable across upgrades.
AppId={{5157D520-A264-42E0-99E7-C1CFF76778FD}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\YAMS
DefaultGroupName=YAMS
DisableProgramGroupPage=yes
OutputDir=..\..\dist
OutputBaseFilename=YAMS_Windows_x64_Setup
SetupIconFile=..\..\yams\resources\icons\yams.ico
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
Source: "..\..\dist\YAMS_Windows_x64\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\YAMS"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall YAMS"; Filename: "{uninstallexe}"
Name: "{autodesktop}\YAMS"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch YAMS now"; Flags: nowait postinstall skipifsilent
