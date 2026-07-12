; =============================================================================
; Field Manager Warehouse - Inno Setup Script
; Publisher : Pansoinco s.r.l.
; Version   : 1.0.272
; Install   : User-space (AppData\Local), no admin required
; =============================================================================

#define AppName        "Field Manager Warehouse"
#define AppID          "FieldManagerWarehouse"
#define AppVersion     "1.0.272"
#define AppPublisher   "Pansoinco s.r.l."
#define AppExeName     "DGWHClient.exe"
#define AppRegKey      "Software\Pansoinco\FieldManagerWarehouse"

; -----------------------------------------------------------------------------
[Setup]
; AppId is kept stable across the rename so an existing install is still
; detected and replaced on upgrade (see REG_UNINST in [Code]).
AppId                     = {{7A9BFB38-C2B4-490D-B51C-205A893CC9DB}
AppName                   = {#AppName}
AppVersion                = {#AppVersion}
AppPublisher              = {#AppPublisher}
AppPublisherURL           = https://www.pansoinco.com
AppSupportURL             = https://www.pansoinco.com/support

; User-space install: no elevation required
PrivilegesRequired        = lowest
PrivilegesRequiredOverridesAllowed = commandline

; Default install dir under current user's AppData\Local
DefaultDirName            = {localappdata}\{#AppID}
DefaultGroupName          = {#AppName}
DisableProgramGroupPage   = yes

; Output
OutputDir                 = Output
OutputBaseFilename        = FieldManagerWarehouse_Setup_{#AppVersion}
SetupIconFile             = dist\DGWHClient\_internal\client.ico
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
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

; -----------------------------------------------------------------------------
[Dirs]
Name: "{app}\_internal\app\templates"

; -----------------------------------------------------------------------------
[Files]
; Main application — PyInstaller onedir output in dist\DGWHClient
Source: "dist\DGWHClient\{#AppExeName}";     DestDir: "{app}"; Flags: ignoreversion
Source: "dist\DGWHClient\*";                  DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "dist\DGWHClient\_internal\app\templates\*"; DestDir: "{app}\_internal\app\templates"; Flags: ignoreversion recursesubdirs createallsubdirs; Check: HasBundledTemplates

; -----------------------------------------------------------------------------
[Icons]
; Desktop shortcut — always created (per spec)
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\{#AppExeName}"

; Start Menu shortcuts
Name: "{userprograms}\{#AppName}\{#AppName}";           Filename: "{app}\{#AppExeName}"
Name: "{userprograms}\{#AppName}\Uninstall {#AppName}"; Filename: "{uninstallexe}"

; -----------------------------------------------------------------------------
[CustomMessages]
WelcomeLabel1=Welcome to Field Manager Warehouse Setup
WelcomeLabel2=This will install [name/ver] on your computer.%n%nPlease close all other applications before continuing.

; -----------------------------------------------------------------------------
[Registry]
; ---------- Template folder key (read by future template-only installers) ----------
Root: HKCU; Subkey: "{#AppRegKey}"; ValueType: string; ValueName: "TemplateFolder"; \
  ValueData: "{app}\_internal\app\templates"; Flags: uninsdeletevalue createvalueifdoesntexist

; ---------- .dgwh (warehouse) file type association ----------
; The .dgjc association is intentionally NOT registered here: the warehouse app
; coexists with the DigitalJobcard app, which owns .dgjc. This installer claims
; only .dgwh so the two apps do not fight over the .dgjc double-click handler.
;
; 1. Register the extension
Root: HKCU; Subkey: "Software\Classes\.dgwh"; \
  ValueType: string; ValueName: ""; ValueData: "FieldManagerWarehouse.Document"; \
  Flags: uninsdeletekey

; 2. Register the ProgID
Root: HKCU; Subkey: "Software\Classes\FieldManagerWarehouse.Document"; \
  ValueType: string; ValueName: ""; ValueData: "Field Manager Warehouse Document"; \
  Flags: uninsdeletekey

Root: HKCU; Subkey: "Software\Classes\FieldManagerWarehouse.Document\DefaultIcon"; \
  ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExeName},0"; \
  Flags: uninsdeletekey

Root: HKCU; Subkey: "Software\Classes\FieldManagerWarehouse.Document\shell\open\command"; \
  ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExeName}"" ""%1"""; \
  Flags: uninsdeletekey

; 3. Notify Windows Explorer of the association change
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.dgwh"; \
  ValueType: string; ValueName: "Progid"; ValueData: "FieldManagerWarehouse.Document"; \
  Flags: uninsdeletevalue

; ---------- App metadata (Add/Remove Programs info) ----------
Root: HKCU; Subkey: "{#AppRegKey}"; ValueType: string; ValueName: "InstallDir";  ValueData: "{app}";           Flags: uninsdeletevalue
Root: HKCU; Subkey: "{#AppRegKey}"; ValueType: string; ValueName: "Version";     ValueData: "{#AppVersion}";   Flags: uninsdeletevalue
Root: HKCU; Subkey: "{#AppRegKey}"; ValueType: string; ValueName: "Publisher";   ValueData: "{#AppPublisher}"; Flags: uninsdeletevalue

; -----------------------------------------------------------------------------
[Code]

{ ── External: shell notification for file association ─────────────────────── }
procedure SHChangeNotify(wEventId, uFlags, dwItem1, dwItem2: Integer);
  external 'SHChangeNotify@shell32.dll stdcall';

{ ── Registry paths ──────────────────────────────────────────────────────────
  InnoSetup appends _is1 to the AppId in the standard uninstall key.
  We also read our own key (AppRegKey) which stores InstallDir directly.       }
const
  REG_UNINST = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{7A9BFB38-C2B4-490D-B51C-205A893CC9DB}_is1';
  REG_APP    = 'Software\Pansoinco\FieldManagerWarehouse';

{ ── Read previous install dir from our own registry key ─────────────────── }
function GetPreviousInstallDir: String;
begin
  Result := '';
  RegQueryStringValue(HKCU, REG_APP, 'InstallDir', Result);
end;

{ ── Read uninstaller path from the standard Uninstall key ───────────────── }
function GetUninstallerPath: String;
begin
  Result := '';
  RegQueryStringValue(HKCU, REG_UNINST, 'UninstallString', Result);
end;

{ ── Check if the app is currently running via WMI ──────────────────────────
  Returns False (safe to proceed) if WMI is unavailable for any reason.        }
function IsAppRunning: Boolean;
var
  WbemLocator, WbemService, WbemObjectSet: Variant;
begin
  Result := False;
  try
    WbemLocator   := CreateOleObject('WbemScripting.SWbemLocator');
    WbemService   := WbemLocator.ConnectServer('', 'root\CIMV2', '', '');
    WbemObjectSet := WbemService.ExecQuery(
      'SELECT * FROM Win32_Process WHERE Name="DGWHClient.exe"');
    Result := (WbemObjectSet.Count > 0);
  except
    { WMI unavailable — assume not running, let the install attempt proceed }
    Result := False;
  end;
end;

{ ── Helper: templates folder present next to installer ──────────────────── }
function HasBundledTemplates(): Boolean;
begin
  Result := DirExists(ExpandConstant('{src}\templates'));
end;

{ ── (A) Pre-populate the dir page with the previous install location ─────── }
procedure InitializeWizard;
var
  PrevDir: String;
begin
  PrevDir := GetPreviousInstallDir;
  if PrevDir <> '' then
    WizardForm.DirEdit.Text := PrevDir;
end;

{ ── (B) Block if app is running, then silent-uninstall previous version ─────
  PrepareToInstall fires after wizard pages, before any files are written.     }
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  UninstPath: String;
  ResultCode: Integer;
begin
  Result := '';

  { ── 1. Refuse to continue while the app is open ─────────────────────────── }
  while IsAppRunning do
  begin
    if MsgBox('Field Manager Warehouse is currently running.' + #13#10 +
              'Please close it and click Retry, or Cancel to abort setup.',
              mbError, MB_RETRYCANCEL) = IDCANCEL then
    begin
      Result := 'Installation cancelled: application was still running.';
      Exit;
    end;
  end;

  { ── 2. Uninstall previous version silently ──────────────────────────────── }
  UninstPath := RemoveQuotes(GetUninstallerPath);
  if UninstPath = '' then Exit;   { no previous install — nothing to do }

  { /SILENT    = show uninstall progress bar (friendlier than VERYSILENT)      }
  { /NORESTART = suppress any reboot request from the old uninstaller          }
  if not Exec(UninstPath, '/SILENT /NORESTART', '', SW_SHOW,
              ewWaitUntilTerminated, ResultCode) then
  begin
    Result := 'Failed to launch previous uninstaller:' + #13#10 + UninstPath;
    Exit;
  end;

  { Non-zero exit: warn but don't hard-abort.
    The new install uses ignoreversion, so leftover files will be overwritten.
    Change to a hard Result := '...' if you prefer strict behaviour.           }
  if ResultCode <> 0 then
    MsgBox('Previous version uninstaller returned code ' + IntToStr(ResultCode) +
           '.' + #13#10 + 'Proceeding anyway.', mbInformation, MB_OK);
end;

{ ── Notify shell of file association change after install ────────────────── }
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    SHChangeNotify($08000000, $0000, 0, 0);
end;

{ ── Clean up FileExts key on uninstall (Windows doesn't auto-remove it) ──── }
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    RegDeleteKeyIncludingSubkeys(HKCU,
      'Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.dgwh');
end;
