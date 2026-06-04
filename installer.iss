[Setup]
AppName=Shweta AI Desktop Assistant
AppVersion=2.0.0
AppPublisher=Prathamesh Khairnar
AppPublisherURL=https://github.com/Prathameshkhairnarr/DESKSHWETA
DefaultDirName={autopf}\Shweta AI
DefaultGroupName=Shweta AI
OutputDir=installer_output
OutputBaseFilename=Shweta_AI_Setup_v2.0
Compression=lzma2/ultra64
SolidCompression=yes
SetupIconFile=
LicenseFile=
WizardStyle=modern
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
UninstallDisplayName=Shweta AI Desktop Assistant
; Minimum Windows 10
MinVersion=10.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
WelcomeLabel1=Welcome to Shweta AI v2.0
WelcomeLabel2=This will install Shweta AI Desktop Assistant. After install you will need to add your free API keys in the .env file.

[Tasks]
Name: "desktopicon"; Description: "Create a Desktop shortcut"; GroupDescription: "Additional icons:"
Name: "startupicon"; Description: "Start Shweta when Windows starts"; GroupDescription: "Startup:"

[Files]
; Main app files
Source: "dist\Shweta\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; .env template — copy as .env only if not already there
Source: ".env.example"; DestDir: "{app}"; DestName: ".env"; Flags: onlyifdoesntexist

[Icons]
Name: "{group}\Shweta AI"; Filename: "{app}\Shweta.exe"; Comment: "Voice-controlled AI Desktop Assistant"
Name: "{group}\Edit API Keys (.env)"; Filename: "notepad.exe"; Parameters: "{app}\.env"; Comment: "Configure your API keys"
Name: "{group}\Uninstall Shweta"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Shweta AI"; Filename: "{app}\Shweta.exe"; Tasks: desktopicon
Name: "{userstartup}\Shweta AI"; Filename: "{app}\Shweta.exe"; Tasks: startupicon

[Run]
Filename: "notepad.exe"; Parameters: "{app}\.env"; Description: "Configure API keys (recommended)"; Flags: postinstall skipifsilent unchecked
Filename: "{app}\Shweta.exe"; Description: "Launch Shweta AI now"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\logs"
Type: filesandordirs; Name: "{app}\cache"
Type: filesandordirs; Name: "{app}\screenshots"


