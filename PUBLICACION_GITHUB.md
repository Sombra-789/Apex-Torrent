# Publicación de Apex Torrent 1.3.8

Paquete de código fuente (no es un .exe compilado). Para publicar un instalador final, subir este proyecto a un **repositorio separado** `apex-torrent` en GitHub; no mezclar con `apex-descarga`.

## Compilación automatizada
1. Crear repositorio `apex-torrent` y subir el contenido de esta carpeta a la raíz, incluyendo `.github/workflows/`.
2. Abrir Actions → **Windows Installer - Apex Torrent 1.3.8** → Run workflow.
3. Esperar al resultado exitoso. Descargar el artefacto `ApexTorrent_1.3.8_Windows_Setup`, que contendrá `ApexTorrent_1.3.8_Setup_x64.exe` y SHA256SUMS.txt.
4. Probar en Windows 10/11 limpio y verificar instalación, icono, inicio, torrent legal oficial, cierre en bandeja y desinstalación.
5. Una vez validado, adjuntar el EXE como asset a la Release v1.3.8 en GitHub.

**Importante:** este paquete no incluye un `.exe` ya compilado. GitHub Actions no firma digitalmente la aplicación. Revisar políticas de licencias de librerías distribuidas y la reproducibilidad antes de publicar. Las pruebas/compilación no están garantizadas hasta que el workflow se ejecute.
