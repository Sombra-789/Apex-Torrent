@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul
echo =====================================
echo   APEX TORRENT - DIAGNOSTICO
echo =====================================
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: ejecuta INSTALAR_WINDOWS.bat primero.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" "scripts\verificar_dependencias.py"
if errorlevel 1 (
  echo ERROR: faltan librerias.
) else (
  echo Si tienes problemas, abre INICIAR_WINDOWS.bat desde esta consola.
)
pause
