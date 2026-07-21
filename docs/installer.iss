; =============================================================================
; PGTP Editor - Inno Setup Script
; Author    : Botond Zalai-Ruzsics
; License   : Open source
; Version   : read from pyproject.toml at compile time (see below)
; Install   : User-space (AppData\Local), no admin required
; =============================================================================
;
; Build first, then compile this script:
;   1. python optimized_build.py          (produces dist\PGTPEditor\)
;   2. ISCC.exe docs\installer.iss         (produces Output\PGTPEditor_Setup_*.exe)
;
; This script lives in docs\, but SourceDir below points one level up so every
; relative path (dist\..., docs\..., Output\) resolves from the repository root.
; =============================================================================

#define AppName        "PGTP Editor"
#define AppID          "PGTPEditor"

; ---------------------------------------------------------------------------
; Single source of truth for the version: pyproject.toml's `version = "x.y.z"`.
; Read here at compile time so the version is never duplicated in this script.
; ISPP's SourcePath is this .iss file's directory (docs\), so the project file
; is one level up. Bump the version in pyproject.toml only.
; ---------------------------------------------------------------------------
#define PyProject AddBackslash(SourcePath) + "..\pyproject.toml"
#ifexist PyProject
  #define AppVersion ""
  #define _VerLine ""
  #define _Rest ""
  #define _Q """"
  #define _VerFH FileOpen(PyProject)
  #sub ScanForVersion
    #expr _VerLine = FileRead(_VerFH)
    #if (AppVersion == "") && (Copy(Trim(_VerLine), 1, 7) == "version")
      ; line is:  version = "x.y.z"  -- take the text between the quotes
      #expr _Rest = Copy(_VerLine, Pos(_Q, _VerLine) + 1, Len(_VerLine))
      #expr AppVersion = Copy(_Rest, 1, Pos(_Q, _Rest) - 1)
    #endif
  #endsub
  #for {0; (AppVersion == "") && !FileEof(_VerFH); 0} ScanForVersion
  #expr FileClose(_VerFH)
#endif
#if !defined(AppVersion) || (AppVersion == "")
  #pragma error "Could not read `version` from pyproject.toml"
#endif

#define AppPublisher   "Botond Zalai-Ruzsics"
#define AppExeName     "PGTPEditor.exe"
#define AppRegKey      "Software\Botond Zalai-Ruzsics\PGTPEditor"
#define AppUrl         "https://github.com/tyutyuszomoru/pgtp_editor"

; -----------------------------------------------------------------------------
[Setup]
; Resolve all relative paths from the repo root (this .iss sits in docs\).
SourceDir                 = ..

; Stable AppId so upgrades detect and replace an existing install
; (see REG_UNINST in [Code]).
AppId                     = {{6AB13736-0BBF-4CB3-8C5B-388774BC72E1}
AppName                   = {#AppName}
AppVersion                = {#AppVersion}
AppPublisher              = {#AppPublisher}
AppPublisherURL           = {#AppUrl}
AppSupportURL             = {#AppUrl}/issues

; User-space install: no elevation required
PrivilegesRequired        = lowest
PrivilegesRequiredOverridesAllowed = commandline

; Default install dir under current user's AppData\Local
DefaultDirName            = {localappdata}\{#AppID}
DefaultGroupName          = {#AppName}
DisableProgramGroupPage   = yes

; Output (relative to SourceDir, i.e. repo-root\Output)
OutputDir                 = Output
OutputBaseFilename        = PGTPEditor_Setup_{#AppVersion}
SetupIconFile             = docs\pgtpeditor.ico
Compression               = lzma2/ultra64
SolidCompression          = yes

; Uninstaller stored in the app folder (user-space, no admin)
UninstallDisplayName      = {#AppName}
UninstallDisplayIcon      = {app}\{#AppExeName}
CreateUninstallRegKey     = yes

; Minimum Windows version: Windows 10
MinVersion                = 10.0

; Installer appearance
WizardStyle               = modern
WizardSizePercent         = 120

; -----------------------------------------------------------------------------
[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

; -----------------------------------------------------------------------------
[Files]
; Main application - PyInstaller onedir output in dist\PGTPEditor
; The .exe sits in {app}; every supporting file (the _internal\ folder with
; python313.dll, PySide6, etc.) is copied alongside it recursively.
Source: "dist\PGTPEditor\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\PGTPEditor\*";             DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; -----------------------------------------------------------------------------
[Icons]
; Desktop shortcut - always created
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\{#AppExeName}"

; Start Menu shortcuts
Name: "{userprograms}\{#AppName}\{#AppName}";           Filename: "{app}\{#AppExeName}"
Name: "{userprograms}\{#AppName}\Uninstall {#AppName}"; Filename: "{uninstallexe}"

; -----------------------------------------------------------------------------
[CustomMessages]
WelcomeLabel1=Welcome to PGTP Editor Setup
WelcomeLabel2=This will install [name/ver] on your computer.%n%nPlease close all other applications before continuing.

; -----------------------------------------------------------------------------
[Registry]
; ---------- .pgtp right-click "Edit with PGTP Editor" verb ----------
; This deliberately does NOT claim the default file association: no ProgID,
; no .pgtp -> handler mapping, no FileExts Progid. It only adds a shell verb
; via SystemFileAssociations, so double-clicking a .pgtp keeps whatever the
; user already has (or "Open with..."), and PGTP Editor just appears in the
; right-click menu for .pgtp files.
;
; NOTE: PGTP Editor does not yet open a file passed on the command line
; (main.py only reads --debug), so this verb launches the app but does not
; auto-open the clicked file. The "%1" is ready for when main.py starts
; reading sys.argv[1]; until then it is harmless.
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.pgtp\shell\EditWithPGTPEditor"; \
  ValueType: string; ValueName: ""; ValueData: "Edit with PGTP Editor"; \
  Flags: uninsdeletekey

Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.pgtp\shell\EditWithPGTPEditor"; \
  ValueType: string; ValueName: "Icon"; ValueData: "{app}\{#AppExeName},0"

Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.pgtp\shell\EditWithPGTPEditor\command"; \
  ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExeName}"" ""%1"""

; ---------- App metadata ----------
Root: HKCU; Subkey: "{#AppRegKey}"; ValueType: string; ValueName: "InstallDir"; ValueData: "{app}";           Flags: uninsdeletevalue
Root: HKCU; Subkey: "{#AppRegKey}"; ValueType: string; ValueName: "Version";    ValueData: "{#AppVersion}";   Flags: uninsdeletevalue
Root: HKCU; Subkey: "{#AppRegKey}"; ValueType: string; ValueName: "Publisher";  ValueData: "{#AppPublisher}"; Flags: uninsdeletevalue

; -----------------------------------------------------------------------------
[Code]

{ -- External: shell notification for file association -- }
procedure SHChangeNotify(wEventId, uFlags, dwItem1, dwItem2: Integer);
  external 'SHChangeNotify@shell32.dll stdcall';

{ -- Registry paths --
  InnoSetup appends _is1 to the AppId in the standard uninstall key.
  We also read our own key (AppRegKey) which stores InstallDir directly. }
const
  REG_UNINST = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{6AB13736-0BBF-4CB3-8C5B-388774BC72E1}_is1';
  REG_APP    = 'Software\Botond Zalai-Ruzsics\PGTPEditor';

{ -- Read previous install dir from our own registry key -- }
function GetPreviousInstallDir: String;
begin
  Result := '';
  RegQueryStringValue(HKCU, REG_APP, 'InstallDir', Result);
end;

{ -- Read uninstaller path from the standard Uninstall key -- }
function GetUninstallerPath: String;
begin
  Result := '';
  RegQueryStringValue(HKCU, REG_UNINST, 'UninstallString', Result);
end;

{ -- Check if the app is currently running via WMI --
  Returns False (safe to proceed) if WMI is unavailable for any reason. }
function IsAppRunning: Boolean;
var
  WbemLocator, WbemService, WbemObjectSet: Variant;
begin
  Result := False;
  try
    WbemLocator   := CreateOleObject('WbemScripting.SWbemLocator');
    WbemService   := WbemLocator.ConnectServer('', 'root\CIMV2', '', '');
    WbemObjectSet := WbemService.ExecQuery(
      'SELECT * FROM Win32_Process WHERE Name="PGTPEditor.exe"');
    Result := (WbemObjectSet.Count > 0);
  except
    { WMI unavailable - assume not running, let the install attempt proceed }
    Result := False;
  end;
end;

{ -- (A) Pre-populate the dir page with the previous install location -- }
procedure InitializeWizard;
var
  PrevDir: String;
begin
  PrevDir := GetPreviousInstallDir;
  if PrevDir <> '' then
    WizardForm.DirEdit.Text := PrevDir;
end;

{ -- (B) Block if app is running, then silent-uninstall previous version --
  PrepareToInstall fires after wizard pages, before any files are written. }
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  UninstPath: String;
  ResultCode: Integer;
begin
  Result := '';

  { -- 1. Refuse to continue while the app is open -- }
  while IsAppRunning do
  begin
    if MsgBox('PGTP Editor is currently running.' + #13#10 +
              'Please close it and click Retry, or Cancel to abort setup.',
              mbError, MB_RETRYCANCEL) = IDCANCEL then
    begin
      Result := 'Installation cancelled: application was still running.';
      Exit;
    end;
  end;

  { -- 2. Uninstall previous version silently -- }
  UninstPath := RemoveQuotes(GetUninstallerPath);
  if UninstPath = '' then Exit;   { no previous install - nothing to do }

  { /SILENT    = show uninstall progress bar (friendlier than VERYSILENT) }
  { /NORESTART = suppress any reboot request from the old uninstaller     }
  if not Exec(UninstPath, '/SILENT /NORESTART', '', SW_SHOW,
              ewWaitUntilTerminated, ResultCode) then
  begin
    Result := 'Failed to launch previous uninstaller:' + #13#10 + UninstPath;
    Exit;
  end;

  { Non-zero exit: warn but don't hard-abort.
    The new install uses ignoreversion, so leftover files will be overwritten. }
  if ResultCode <> 0 then
    MsgBox('Previous version uninstaller returned code ' + IntToStr(ResultCode) +
           '.' + #13#10 + 'Proceeding anyway.', mbInformation, MB_OK);
end;

{ -- Notify shell of the context-menu change after install -- }
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    SHChangeNotify($08000000, $0000, 0, 0);
end;

{ -- Remove the shell verb on uninstall and refresh the shell --
  uninsdeletekey already removes the EditWithPGTPEditor key; this also prunes
  the parent SystemFileAssociations\.pgtp key if we left it empty, then tells
  Explorer to drop the verb from its cache. }
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    RegDeleteKeyIfEmpty(HKCU, 'Software\Classes\SystemFileAssociations\.pgtp\shell');
    RegDeleteKeyIfEmpty(HKCU, 'Software\Classes\SystemFileAssociations\.pgtp');
    SHChangeNotify($08000000, $0000, 0, 0);
  end;
end;
