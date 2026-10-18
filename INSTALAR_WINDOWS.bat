@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\instalar.ps1"
set "RESULT=%ERRORLEVEL%"
echo.
if not "%RESULT%"=="0" echo Instalacion incompleta. Error: %RESULT%
echo Pulsa cualquier tecla para cerrar esta ventana.
pause >nul
exit /b %RESULT%
