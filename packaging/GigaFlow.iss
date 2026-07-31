#define MyAppName "GigaFlow"
#define MyAppVersion "0.1.7"
#define MyAppPublisher "GigaFlow"
#define MyAppExeName "GigaFlow.exe"

[Setup]
AppId={{E30BD756-132B-4F5E-91D7-F99D6CCF649D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\installer-output
OutputBaseFilename=GigaFlow-Setup
SetupIconFile=..\src\gigaflow\assets\gigaflow.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
russian.FinishedHeadingLabel=GigaFlow успешно установлен
russian.FinishedLabel=Все компоненты установлены. Приложение готово к запуску.%n%nПри первом запуске GigaFlow проверит модель распознавания речи и при необходимости автоматически загрузит её.
russian.ClickFinish=Нажмите «Завершить», чтобы закрыть установщик.
english.FinishedHeadingLabel=GigaFlow was installed successfully
english.FinishedLabel=All components are installed. The application is ready to run.%n%nOn first launch GigaFlow will check the speech model and download it automatically if necessary.
english.ClickFinish=Click Finish to close Setup.

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Ярлыки:"; Flags: checkedonce

[Files]
Source: "..\dist\GigaFlow\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\GigaFlow"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\GigaFlow"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Запустить GigaFlow"; Flags: nowait postinstall skipifsilent
