$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"

Write-Host "Preparing the isolated GigaFlow environment..."
if (-not (Test-Path -LiteralPath $venvPython)) {
    py -3.14 -m venv (Join-Path $projectRoot ".venv")
}

& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -e $projectRoot

Write-Host ""
Write-Host "GigaFlow installation is complete."
Write-Host "Start the GigaFlow.cmd file."
