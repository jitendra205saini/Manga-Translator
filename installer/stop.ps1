# Manga Translator server (port 7860) band karo
Get-NetTCPConnection -LocalPort 7860 -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 1
