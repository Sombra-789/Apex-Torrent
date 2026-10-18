@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul
if not exist ".venv\Scripts\python.exe" (
  echo Ejecuta primero INSTALAR_WINDOWS.bat
  pause
  exit /b 1
)
echo Instalando PyInstaller...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check "pyinstaller>=6.0,<7"
if errorlevel 1 goto :error
echo Creando ejecutable portable de Windows...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --windowed --onedir --name "ApexTorrent" --icon "app\assets\apex-torrent.ico" --add-data "app\assets;assets" --paths "app" --hidden-import libtorrent "app\main.py"
if errorlevel 1 goto :error
echo.
echo EXE generado en: dist\ApexTorrent\ApexTorrent.exe
echo Copia toda la carpeta dist\ApexTorrent para compartir el programa.
echo Para actualizar el acceso directo al EXE: ejecuta CREAR_ACCESO_DIRECTO.bat.
pause
exit /b 0
:error
echo.
echo No se pudo compilar. Lee los mensajes anteriores.
pause
exit /b 1
