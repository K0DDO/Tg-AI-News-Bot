@echo off
REM Briefly — kill old processes and restart bot + worker + API
cd /d "%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0restart.ps1" %*
