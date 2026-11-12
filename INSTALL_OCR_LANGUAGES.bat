@echo off
net session >nul 2>&1
if errorlevel 1 (
  echo Admin permission maang raha hai...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
echo OCR language packs install ho rahe hain, kuch minute lag sakte hain...
powershell -NoProfile -ExecutionPolicy Bypass -Command "foreach ($l in @('ja-JP','ko-KR','zh-CN','zh-TW','en-US')) { $n = 'Language.OCR~~~' + $l + '~0.0.1.0'; Write-Host ('Installing ' + $n); try { Add-WindowsCapability -Online -Name $n -ErrorAction Stop | Out-Null; Write-Host '  OK' } catch { Write-Host ('  FAIL: ' + $_.Exception.Message) } }"
echo.
echo Ho gaya.
pause
