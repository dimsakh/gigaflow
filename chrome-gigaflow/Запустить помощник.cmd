@echo off
chcp 65001 >nul
if not exist "%~dp0.venv\Scripts\pythonw.exe" (
    echo Сначала запустите "Установить Chrome GigaFlow.cmd"
    pause
    exit /b 1
)
start "" /b "%~dp0.venv\Scripts\pythonw.exe" -m gigaflow_chrome
