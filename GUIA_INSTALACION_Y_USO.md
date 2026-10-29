# Guía de instalación, uso y requisitos — Apex Torrent

**Contacto oficial Apex Software Inc.:** [apexsoftware.inc07@gmail.com](mailto:apexsoftware.inc07@gmail.com) — sugerencias, quejas, fallos y propuestas. [Guía de contacto y soporte](CONTACTO_Y_SOPORTE.md).

**Producto del ecosistema Apex Software Inc.** (denominación de marca utilizada por este proyecto; no implica certificación ni acredita por sí sola una sociedad legalmente constituida).

## Para qué sirve
Cliente BitTorrent para gestionar torrents autorizados, pares, trackers, selección de adaptador, diagnóstico de red, reanuncio y recuperación de fuentes.

## Descargas disponibles
[Instalador Windows 1.3.8 en Actions](https://github.com/Sombra-789/Apex-Torrent/actions/runs/39108540999) · [Alpha 1.4.0 experimental](https://github.com/Sombra-789/Apex-Torrent/actions/runs/39506715187)

**Importante:** GitHub Actions Artifacts puede exigir inicio de sesión y caducar. Los paquetes beta/preview no se equiparan a versiones estables.

## Instalación paso a paso
Para el ejecutable, abre la ejecución correcta de Actions, descarga el archivo en Artifacts, extrae e inspecciona el paquete antes de ejecutar el instalador. Para código fuente, instala Python 3.12/3.13 x64 en Windows, extrae el repositorio, ejecuta `INSTALAR_WINDOWS.bat` y abre `INICIAR_WINDOWS.bat`. Antes de actualizar respalda `%LOCALAPPDATA%\ApexTorrent` y cierra la aplicación desde la bandeja.

## Cómo funciona y cómo utilizarlo
Añade un magnet o torrent autorizado, elige destino, observa disponibilidad, pares y progreso. En Red/Diagnóstico revisa interfaces y puertos; utiliza 'Intentar recuperar fuentes' solo cuando corresponda; 'Verificar archivos' comprueba las piezas locales.

## Requisitos y dependencias
Windows x64, conexión P2P permitida, espacio según descarga. Desde código: Python 3.12/3.13 x64, `PySide6>=6.9,<7`, `libtorrent==2.0.15`, `psutil>=6,<8` (requirements.txt). El instalador de Actions puede requerir sesión de GitHub y caduca.

## Limitaciones, seguridad y privacidad
No crea semillas, no garantiza velocidad ni recuperación de torrents sin pares; DHT/trackers dependen de la red. La detección de ruta no es un kill switch VPN. El README histórico describe 1.3.8 como candidato de prueba; la alpha 1.4 no debe considerarse estable. P2P solo con archivos cuyo intercambio esté autorizado.

## Más información
- [Repositorio GitHub](https://github.com/Sombra-789/Apex-Torrent)
- [Ficha de proyecto en Notion](https://app.notion.com/p/3fd252e21ba681d29a95ce03eb90f371)
- Consulta el README y las notas de cada versión para instrucciones adicionales.

---
© 2026 Apex Software Inc. — Identidad de proyecto. Las bibliotecas externas pertenecen a sus respectivos titulares y conservan sus licencias. No se afirma registro mercantil ni afiliación con terceros.
