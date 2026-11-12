@echo off
setlocal
cd /d "%~dp0"
echo ===== Manga Translator setup (Python 3.13 + existing PyTorch) =====

py -3.13 -c "import torch" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python 3.13 mein PyTorch nahi mila.
  pause
  exit /b 1
)

if not exist "manga_env\Scripts\python.exe" (
  py -3.13 -m venv --system-site-packages manga_env || goto :fail
)
set "VPY=%~dp0manga_env\Scripts\python.exe"

"%VPY%" -m pip install --upgrade pip || goto :fail
"%VPY%" -m pip install -r server\requirements.txt || goto :fail

cd server
echo.
echo ===== Fribidi, config, font aur NLLB model download =====
"%VPY%" download_assets.py || goto :fail
echo.
echo ===== Setup check =====
"%VPY%" check_setup.py
cd ..
echo.
echo Setup complete. Ab server\config.json mein apni Gemini/Groq key daalo, phir START_SERVER.bat chalao.
pause
exit /b 0

:fail
echo.
echo [ERROR] Setup fail hua. Upar ka error dekho.
pause
exit /b 1