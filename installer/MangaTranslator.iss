; Inno Setup script. Build: installer\build.bat  ->  installer\Output\MangaTranslator-Setup.exe
#define AppName "Manga Translator"
#define AppVersion "2.5.1"
#define Root ".."

[Setup]
AppId={{6B0D5F2E-6E9A-4C1B-9A8F-4D2C1E7B5A31}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=jitendra205saini
AppPublisherURL=https://github.com/jitendra205saini/Manga-Translator
DefaultDirName={localappdata}\Programs\Manga Translator
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=MangaTranslator-Setup
SetupIconFile={#Root}\extension\icons\icon.ico
UninstallDisplayIcon={app}\extension\icons\icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"
Name: "autostart"; Description: "Start Manga Translator automatically when Windows starts (recommended)"

[Files]
Source: "{#Root}\server\*"; DestDir: "{app}\server"; Flags: recursesubdirs ignoreversion; \
  Excludes: "models,cache,debug,bin,fonts\*.ttf,__pycache__,config.json,memory.json,usage.json,*.log"
Source: "{#Root}\extension\*"; DestDir: "{app}\extension"; Flags: recursesubdirs ignoreversion
Source: "{#Root}\installer\install.ps1"; DestDir: "{app}\installer"; Flags: ignoreversion
Source: "{#Root}\installer\stop.ps1"; DestDir: "{app}\installer"; Flags: ignoreversion
Source: "{#Root}\installer\browser.html"; DestDir: "{app}\installer"; Flags: ignoreversion
Source: "{#Root}\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#Root}\LICENSE"; DestDir: "{app}"; Flags: ignoreversion

[InstallDelete]
; purane version ka startup shortcut (sirf server chalata tha)
Type: files; Name: "{userstartup}\Manga Translator server.lnk"

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\server\tray.py"""; \
  WorkingDir: "{app}\server"; IconFilename: "{app}\extension\icons\icon.ico"
Name: "{group}\API keys"; Filename: "http://127.0.0.1:7860/setup"; IconFilename: "{app}\extension\icons\icon.ico"
Name: "{group}\Add extension to browser"; Filename: "{app}\installer\browser.html"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\server\tray.py"""; \
  WorkingDir: "{app}\server"; IconFilename: "{app}\extension\icons\icon.ico"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}"; Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\server\tray.py"" --quiet"; \
  WorkingDir: "{app}\server"; IconFilename: "{app}\extension\icons\icon.ico"; Tasks: autostart

[Run]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\installer\install.ps1"" -AppDir ""{app}"""; \
  StatusMsg: "Downloading Python and AI models (about 600 MB, a few minutes)..."; Flags: waituntilterminated runhidden
Filename: "{app}\installer\browser.html"; Description: "Add the extension to my browser"; Flags: postinstall shellexec skipifsilent
Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\server\tray.py"""; WorkingDir: "{app}\server"; \
  Description: "Start Manga Translator now"; Flags: postinstall nowait skipifsilent
; auto-update (silent install) ke baad tray khud dobara chalu
Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\server\tray.py"" --quiet"; WorkingDir: "{app}\server"; \
  Flags: nowait; Check: WizardSilent

[UninstallRun]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\installer\stop.ps1"""; \
  Flags: runhidden waituntilterminated; RunOnceId: "StopServer"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var Code: Integer;
begin
  { update ke waqt purana server band karo taaki files badal sakein }
  if (CurStep = ssInstall) and FileExists(ExpandConstant('{app}\installer\stop.ps1')) then
    Exec('powershell.exe', '-NoProfile -ExecutionPolicy Bypass -File "' + ExpandConstant('{app}\installer\stop.ps1') + '"',
      '', SW_HIDE, ewWaitUntilTerminated, Code);
end;
