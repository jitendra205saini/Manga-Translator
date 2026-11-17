# Manga Translator band karo: server aur tray, sirf jo is install ke Python se chal rahe hon (doosre apps ko mat chhuo)
$app = Split-Path -Parent $PSScriptRoot
Get-Process python, pythonw -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -and $_.Path.StartsWith($app, [StringComparison]::OrdinalIgnoreCase) } |
    Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1
