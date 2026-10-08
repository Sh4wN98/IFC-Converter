; Inno Setup 6 script for IFC Converter. Built by packaging/build.py, which passes:
;   /DAppVersion=<version from pyproject.toml>  /DSourceDir=<dist\IFC Converter>  /DOutputDir=<dist>  /DIconFile=<.ico>
;
; Installs per user (no admin rights, nothing outside the user profile): the program goes to
; %LOCALAPPDATA%\Programs\IFC Converter, plus a Start menu shortcut. No services, no autostart, no
; file associations unless the user ticks them. Installing a newer version over an older one updates it.

#define AppName "IFC Converter"
#define AppExe "IFC Converter.exe"
#ifndef AppVersion
  #error AppVersion must be passed: ISCC /DAppVersion=1.2.3 ...
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\IFC Converter"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist"
#endif
#ifndef IconFile
  #define IconFile "placeholder-icon.ico"
#endif

[Setup]
; Never change the AppId: Windows recognises updates and the uninstaller by it.
AppId={{6F0B8E52-3C1D-4B7A-9E2F-5A8C1D4E7B90}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Jonas Kleinert
AppPublisherURL=https://github.com/Sh4wN98/IFC-Converter
VersionInfoVersion={#AppVersion}
VersionInfoProductName={#AppName}
VersionInfoDescription={#AppName} Setup
; Per-user installation: no UAC prompt, no admin rights.
PrivilegesRequired=lowest
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
DisableReadyPage=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutputDir}
OutputBaseFilename=IFC-Converter-{#AppVersion}-Setup
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; While IFC Converter runs (the window or ifc-convert, and with them any conversion), Setup and the
; uninstaller ask to close it first and refuse to go on otherwise: the app holds this mutex
; (app.APP_MUTEX). Killing it would lose a conversion that may have run for an hour.
AppMutex=IFCConverter-6F0B8E52-3C1D-4B7A-9E2F-5A8C1D4E7B90
; Other programs using its files are closed (after asking) before files are replaced, and not restarted.
CloseApplications=yes
RestartApplications=no
ShowLanguageDialog=auto

[Languages]
Name: "de"; MessagesFile: "compiler:Languages\German.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
de.OpenWith=„Öffnen mit“-Eintrag für IFC-Dateien hinzufügen (ändert nicht das Standardprogramm)
en.OpenWith=Add an "Open with" entry for IFC files (does not change the default program)
de.Integration=Integration:
en.Integration=Integration:

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "openwith"; Description: "{cm:OpenWith}"; GroupDescription: "{cm:Integration}"; Flags: unchecked

[InstallDelete]
; An update replaces the bundled libraries completely, so no stale file of an older version is loaded.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Tasks: desktopicon

[Registry]
; Optional "Open with" entry, current user only. The default program for .ifc stays untouched.
Root: HKCU; Subkey: "Software\Classes\IFCConverter.ifc"; ValueType: string; ValueName: ""; ValueData: "IFC-Datei"; Flags: uninsdeletekey; Tasks: openwith
Root: HKCU; Subkey: "Software\Classes\IFCConverter.ifc\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"",0"; Tasks: openwith
Root: HKCU; Subkey: "Software\Classes\IFCConverter.ifc\shell\open"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "{#AppName}"; Tasks: openwith
Root: HKCU; Subkey: "Software\Classes\IFCConverter.ifc\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: openwith
Root: HKCU; Subkey: "Software\Classes\.ifc\OpenWithProgids"; ValueType: none; ValueName: "IFCConverter.ifc"; Flags: uninsdeletevalue; Tasks: openwith

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Only what the program itself created inside its own folder. Settings and logs in the user profile
; (%APPDATA%\IFC Converter, %LOCALAPPDATA%\IFC Converter) are kept, like most programs do.
Type: filesandordirs; Name: "{app}\_internal"

[Code]
const
  // Where versions before the renaming kept their settings (QSettings of gui.LEGACY_NAME). Later
  // versions copy them to settings.ini once (and Qt may create the key empty when looking for them).
  LegacyParentKey = 'Software\IFC File Converter';
  LegacyKey = 'Software\IFC File Converter\IFC File Converter';

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    // Only that key; its parent only if nothing else is left in it.
    if RegKeyExists(HKCU, LegacyKey) then
      if not RegDeleteKeyIncludingSubkeys(HKCU, LegacyKey) then
        Log('Could not remove HKCU\' + LegacyKey);
    if RegKeyExists(HKCU, LegacyParentKey) then
      RegDeleteKeyIfEmpty(HKCU, LegacyParentKey);
  end;
end;
