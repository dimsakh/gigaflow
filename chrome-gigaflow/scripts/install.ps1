$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$venvRoot = Join-Path $projectRoot ".venv"
$venvPython = Join-Path $venvRoot "Scripts\python.exe"
$venvPythonw = Join-Path $venvRoot "Scripts\pythonw.exe"

Write-Host "Устанавливаю локальный помощник GigaFlow для Chrome..."
if (-not (Test-Path -LiteralPath $venvPython)) {
    $created = $false
    if (Get-Command py.exe -ErrorAction SilentlyContinue) {
        foreach ($version in @("3.14", "3.13", "3.12")) {
            & py "-$version" -m venv $venvRoot
            if ($LASTEXITCODE -eq 0) {
                $created = $true
                break
            }
        }
    }
    if (-not $created -and (Get-Command python.exe -ErrorAction SilentlyContinue)) {
        & python -m venv $venvRoot
        $created = $LASTEXITCODE -eq 0
    }
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "Не найден подходящий Python. Установите Python 3.12–3.14 с python.org и повторите."
}

& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -e $projectRoot

$startupDirectory = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"
$shortcutPath = Join-Path $startupDirectory "GigaFlow Chrome.lnk"
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $venvPythonw
$shortcut.Arguments = "-m gigaflow_chrome"
$shortcut.WorkingDirectory = $projectRoot
$iconPath = Join-Path $projectRoot "assets\gigaflow.ico"
if (Test-Path -LiteralPath $iconPath) {
    $shortcut.IconLocation = $iconPath
}
$shortcut.Save()

Start-Process -FilePath $venvPythonw -ArgumentList "-m", "gigaflow_chrome" -WorkingDirectory $projectRoot -WindowStyle Hidden

Write-Host ""
Write-Host "Локальный помощник установлен и запущен."
Write-Host "Теперь откройте chrome://extensions, включите режим разработчика,"
Write-Host "нажмите 'Загрузить распакованное расширение' и выберите папку:"
Write-Host (Join-Path $projectRoot "extension")
Write-Host ""
Write-Host "При первом запуске модель загрузится автоматически."
