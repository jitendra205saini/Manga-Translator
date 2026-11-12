@echo off
rem Developer copy ke liye one-click start. Installer wale users Start menu ka "Manga Translator" use karein.
cd /d "%~dp0"
set "PYW=%~dp0python\pythonw.exe"
if not exist "%PYW%" set "PYW=%~dp0manga_env\Scripts\pythonw.exe"
if not exist "%PYW%" (
  echo Pehli baar setup ho raha hai...
  call "%~dp0SETUP.bat"
  if not exist "%PYW%" exit /b 1
)
start "" "%PYW%" "%~dp0server\launch.py"
