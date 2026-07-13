@echo off
chcp 65001 >nul
REM Briefly — kill old processes and restart bot + worker + API
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: .venv not found. Create it first:
  echo   python -m venv .venv
  echo   .venv\Scripts\pip install -r requirements.txt
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0restart.ps1" %*
set ERR=%ERRORLEVEL%
if %ERR% neq 0 (
  echo.
  echo Restart failed with code %ERR%.
  pause
  exit /b %ERR%
)
echo.
pause
