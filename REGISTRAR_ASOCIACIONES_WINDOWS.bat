@echo off
setlocal
cd /d "%~dp0"
echo Registrando Apex Torrent como opcion para .torrent y magnet sin cambiar tu aplicacion predeterminada...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\registrar_asociaciones.ps1"
set "RESULT=%ERRORLEVEL%"
pause
exit /b %RESULT%
