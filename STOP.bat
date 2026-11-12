@echo off
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 7860 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }"
echo Manga Translator server band ho gaya.
ping -n 3 127.0.0.1 >nul
