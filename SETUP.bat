@echo off
rem Developer setup (installer ki zarurat nahi): Python 3.11+ chahiye. Offline NLLB backup ke liye: SETUP.bat nllb
setlocal
cd /d "%~dp0"
echo ===== Manga Translator developer setup =====

if not exist "manga_env\Scripts\python.exe" (
  py -3 -m venv manga_env || goto :fail
)
set "VPY=%~dp0manga_env\Scripts\python.exe"

"%VPY%" -m pip install --upgrade pip || goto :fail
"%VPY%" -m pip install -r server\requirements.txt || goto :fail
set "NLLB=--no-nllb"
if /i "%~1"=="nllb" (
  "%VPY%" -m pip install torch -r server\requirements-nllb.txt || goto :fail
  set "NLLB="
)

cd server
echo.
echo ===== Fonts, models, config =====
"%VPY%" download_assets.py %NLLB% || goto :fail
echo.
echo ===== Setup check =====
"%VPY%" check_setup.py
cd ..
echo.
echo Setup complete. START.bat chalao, phir browser mein API key daalo.
pause
exit /b 0

:fail
echo.
echo [ERROR] Setup fail hua. Upar ka error dekho.
pause
exit /b 1
