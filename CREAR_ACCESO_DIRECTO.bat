@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul
echo ============================================
echo       APEX TORRENT 1.2 - ACCESO DIRECTO
echo ============================================
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\crear_acceso_directo.ps1"
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" (
 echo.
 echo No se pudo crear el acceso directo. Error: %RESULT%
)
echo.
pause
exit /b %RESULT%
