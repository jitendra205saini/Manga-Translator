@echo off
cd /d "%~dp0server"
if not exist "..\manga_env\Scripts\python.exe" (
  echo Pehle SETUP.bat chalao.
  pause
  exit /b 1
)
echo Server start ho raha hai: http://127.0.0.1:7860
echo Band karne ke liye ye window band kar do.
"..\manga_env\Scripts\python.exe" -m uvicorn server:app --host 127.0.0.1 --port 7860
pause
