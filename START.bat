@echo off
setlocal
cd /d "%~dp0"
title Manga Translator
set "VPY=%~dp0manga_env\Scripts\python.exe"
set "PYW=%~dp0manga_env\Scripts\pythonw.exe"

rem ---- 1. Pehli baar: setup ----
if not exist "%VPY%" (
  echo Pehli baar setup ho raha hai, thoda time lagega...
  call "%~dp0SETUP.bat"
  if not exist "%VPY%" exit /b 1
)
if not exist "server\models\comic-text-and-bubble-detector\detector.onnx" (
  pushd server & "%VPY%" download_assets.py & popd
)

rem ---- 2. API key check ----
"%VPY%" -c "import json,sys;c=json.load(open(r'server\config.json',encoding='utf-8'));sys.exit(0 if (c.get('gemini',{}).get('api_key') or c.get('groq',{}).get('api_key')) else 1)" >nul 2>&1
if errorlevel 1 (
  if not exist "server\config.json" copy "server\config.example.json" "server\config.json" >nul
  echo.
  echo Gemini API key chahiye ^(free^). Browser mein page khul raha hai, key copy karo
  echo aur Notepad mein "api_key" ke saamne "" ke andar paste karke save karo.
  start "" "https://aistudio.google.com/apikey"
  notepad "server\config.json"
)

rem ---- 3. Server pehle se chal raha hai? ----
call :health
if not errorlevel 1 goto :ready

rem ---- 4. Server background mein (bina window ke) ----
echo Server start ho raha hai...
powershell -NoProfile -Command "Start-Process -FilePath '%PYW%' -ArgumentList '-m','uvicorn','server:app','--host','127.0.0.1','--port','7860' -WorkingDirectory '%~dp0server' -WindowStyle Hidden -RedirectStandardOutput '%~dp0server\server.log' -RedirectStandardError '%~dp0server\server_err.log'"
for /l %%i in (1,1,90) do (
  ping -n 2 127.0.0.1 >nul
  call :health
  if not errorlevel 1 goto :ready
)
echo [ERROR] Server start nahi hua. Log dekho: server\server_err.log
notepad "server\server_err.log"
pause
exit /b 1

:ready
rem ---- 5. Desktop shortcut (sirf pehli baar) ----
if not exist "%USERPROFILE%\Desktop\Manga Translator.lnk" (
  powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\Manga Translator.lnk');$s.TargetPath='%~dp0START.bat';$s.WorkingDirectory='%~dp0';$s.IconLocation='%~dp0extension\icons\icon.ico';$s.WindowStyle=7;$s.Save()" >nul 2>&1
)
echo.
echo Server chal raha hai: http://127.0.0.1:7860
echo Ab manga page kholo aur extension ON karo ^(Alt+T^). Band karna ho to STOP.bat.
ping -n 5 127.0.0.1 >nul
exit /b 0

:health
powershell -NoProfile -Command "try{Invoke-WebRequest http://127.0.0.1:7860/health -UseBasicParsing -TimeoutSec 2 | Out-Null; exit 0}catch{exit 1}" >nul 2>&1
exit /b %errorlevel%
