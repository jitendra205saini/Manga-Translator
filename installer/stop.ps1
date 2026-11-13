# Manga Translator band karo: server (port 7860) aur tray, jo bhi is install ke Python se chal raha ho
$app = Split-Path -Parent $PSScriptRoot
Get-NetTCPConnection -LocalPort 7860 -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
Get-Process python, pythonw -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -and $_.Path.StartsWith($app, [StringComparison]::OrdinalIgnoreCase) } |
    Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1
