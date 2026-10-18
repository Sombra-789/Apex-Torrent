@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul
if not exist ".venv\Scripts\python.exe" (
  echo No esta instalado Apex Torrent.
  echo Ejecuta primero INSTALAR_WINDOWS.bat
  pause
  exit /b 1
)
".venv\Scripts\python.exe" "app\main.py"
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" (
  echo.
  echo Apex Torrent se cerro con error %RESULT%.
  echo Revisa %%LOCALAPPDATA%%\ApexTorrent\apex_torrent.log
  pause
)
exit /b %RESULT%
