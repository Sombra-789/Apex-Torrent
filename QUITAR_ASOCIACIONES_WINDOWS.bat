@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\quitar_asociaciones.ps1"
set "RESULT=%ERRORLEVEL%"
pause
exit /b %RESULT%
