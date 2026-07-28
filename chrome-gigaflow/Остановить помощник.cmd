@echo off
chcp 65001 >nul
powershell.exe -NoProfile -Command "try { Invoke-RestMethod -Method Post -ContentType 'application/json' -Body '{}' -Uri 'http://127.0.0.1:38473/shutdown' -Headers @{ Origin='chrome-extension://local-control' } | Out-Null; Write-Host 'Помощник остановлен.' } catch { Write-Host 'Помощник не запущен.' }"
pause
