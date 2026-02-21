
@echo off
cd /d %~dp0..\

if not exist .venv (
  echo Falta entorn virtual. Executa scripts\install.ps1
  pause
  exit /b 1
)

call .venv\Scripts\activate.bat
python -m app.main
