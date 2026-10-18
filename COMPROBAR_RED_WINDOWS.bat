@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title Apex Torrent - Verificar puertos Windows
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\comprobar_red.ps1"
echo.
echo Pulsa cualquier tecla para cerrar...
pause >nul
