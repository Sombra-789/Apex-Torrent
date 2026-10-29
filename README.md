# Apex Torrent 1.3.8 — Final Polish & Source Recovery (candidato de prueba)

> **Apex Software Inc. — Proyecto del ecosistema Apex Software.** [Guía completa de instalación, funcionamiento, requisitos, dependencias y limitaciones](GUIA_INSTALACION_Y_USO.md). La denominación “Inc.” se usa como identidad de proyecto y no constituye prueba de registro legal.

Conserva el motor libtorrent, la selección de adaptador de **Network Repair 1.3.6**, Smart Engine, estadísticas, bandeja y Apex Bridge. No borra ni reescribe torrents ni descargas al actualizar.

## Correcciones visuales

- **Detalles** utiliza un área de desplazamiento propia: los 6 campos respetan la altura mínima, sin superposiciones si reduces el panel inferior.
- Texto extenso (hashes, rutas y errores) se muestra abreviado en el centro, y completo al pasar el cursor. El texto se interpreta como texto plano.
- **Pares** conserva anchos útiles para velocidad y disponibilidad, y ofrece desplazamiento horizontal si se estrecha demasiado la ventana.
- **Trackers** tiene anchos mínimos y desplazamiento horizontal para evitar columnas ilegibles.
- La proporción inicial del separador Biblioteca/Detalles prioriza la lectura de ambas vistas. Si ya elegiste otra proporción en la 1.3.7, se conservará.

## Intentar recuperar fuentes

En **Herramientas → Intentar recuperar fuentes** o en la pestaña **Diagnóstico** puedes solicitar un nuevo intento de descubrimiento. No descarga por sí sola si faltan semillas.

- Solicita reanuncio a los trackers y a DHT cuando el motor lo admite y DHT está habilitado. No contacta DHT para torrents privados con metadatos conocidos.
- Conserva pausas manuales, horario, configuración de red, archivos e historial de descargas.
- Comparte una espera de 60 segundos con «Reanunciar» para evitar solicitudes repetidas.
- No añade automáticamente listas masivas de rastreadores ni garantiza que un torrent con 0 fuentes se recupere.
- Si un archivo local presenta fallos de piezas, usa **Herramientas → Verificar archivos**, una operación distinta que puede tardar bastante para archivos grandes.
- Para distinguir problema de fuentes frente a problemas del motor, compara con Ubuntu oficial u otra descarga autorizada con semillas activas.

## Actualizar desde 1.3.7

1. Cierra Apex Torrent mediante **Salir completamente** desde la bandeja del sistema.
2. Respalda `%LOCALAPPDATA%\ApexTorrent` antes de actualizar.
3. Extrae el parche directamente en la carpeta que contiene `INICIAR_WINDOWS.bat`, reemplazando solo los archivos incluidos.
4. Ejecuta `INICIAR_WINDOWS.bat` y verifica que la ventana muestre `1.3.8`.
5. Ajusta el separador Biblioteca / Detalles y prueba «Intentar recuperar fuentes» sobre un torrent autorizado detenido.

El **ZIP completo** incluye instalador para Windows con Python 3.12/3.13 x64. No contiene un `.exe` precompilado. Si usas una instalación previa funcional, no hace falta reinstalar libtorrent.

## Pruebas y límites

Las pruebas automatizadas utilizan un sustituto de libtorrent; no envían tráfico BitTorrent ni modifican descargas. En Windows ejecuta `EJECUTAR_PRUEBAS.bat`. Deben realizarse pruebas de la interfaz en PySide6 y de descarga real antes de declarar esta versión final estable.

---

## Historial de la versión anterior

# Apex Torrent 1.3.7 — Visual & Peer Intelligence (Beta)

Actualización conservadora desde 1.3.6. **No modifica** la selección de adaptador, el puerto automático, las descargas existentes ni Apex Bridge. La interfaz necesita validación visual en Windows 11.

## Mejoras de interfaz

- Tarjetas superiores compactas y más altura para la biblioteca de torrents.
- Divisor vertical redimensionable: arrastra la separación entre Biblioteca y Detalles. Las proporciones se guardan localmente en `%LOCALAPPDATA%\ApexTorrent\ui_layout.json`.
- Botón **Ocultar detalles / Mostrar detalles** para aprovechar toda la pantalla.
- Columnas adaptables: la tabla oculta progresivamente Ratio, ETA, Subida y Semillas cuando la ventana es demasiado estrecha. Los detalles técnicos siguen visibles seleccionando el torrent.
- Aviso contextual en una línea con informe completo en el tooltip y la pestaña Diagnóstico.
- Altura de filas reducida, mejor separación y un separador más visible para arrastrar.

## Peer Intelligence

- Direcciones de pares mostradas como `IP:puerto` o `[IPv6]:puerto`, sin tuplas crudas.
- Nombres de clientes recibidos en `bytes` decodificados correctamente; si están vacíos se indica *No identificado*.
- Resumen del porcentaje de piezas que reportan los pares conectados: **no equivale a la cantidad total de semillas disponibles en la red**.
- Se distingue tráfico de protocolo de tráfico útil usando `torrent_status.download_payload_rate` cuando está disponible; `download_rate` se conserva por compatibilidad.
- El estado **Conectando** puede aparecer cuando hay intercambio de protocolo sin carga útil. Las cifras y el ETA se basan en carga útil cuando libtorrent la expone.
- No se prometen velocidades superiores ni semillas artificiales.

## Instalación desde 1.3.6

1. Sal completamente de Apex Torrent desde la bandeja.
2. Haz copia de `%LOCALAPPDATA%\ApexTorrent`.
3. Descomprime el parche dentro de la misma carpeta donde está `INICIAR_WINDOWS.bat` reemplazando archivos.
4. Abre Apex Torrent y comprueba `1.3.7` en el título.
5. Prueba Ubuntu oficial; verifica que el motor siga descargando y ajusta el divisor entre Biblioteca y Detalles.

Si utilizas la **versión completa**, ejecuta el instalador incluido. Requiere Windows con Python 3.12/3.13 x64 y dependencias especificadas en `requirements.txt`. No contiene ejecutable precompilado.

## Pruebas

Las pruebas automatizadas corren con motor libtorrent simulado. Ejecuta `EJECUTAR_PRUEBAS.bat` para verificarlas en Windows. Ni la transferencia real ni la visualización con PySide6 pueden considerarse validadas hasta probarse localmente.

---

## Detalles de Network Repair 1.3.6 conservados

# Apex Torrent 1.3.6 — Network Repair (Beta)

**Motor:** libtorrent 2.0.15 + PySide6. **Base:** Apex Torrent 1.3.5, con Apex Bridge v2 y las funciones anteriores.

## Qué corrige

En equipos Windows con adaptadores virtuales, libtorrent podía escuchar y enviar anuncios UDP/DHT desde varias interfaces simultáneamente, incluso loopback (`127.0.0.1`, `::1`) o redes privadas sin ruta. La pantalla de diagnóstico mostraba fallos `unreachable`, `Host desconocido` y `timed out`.

Ahora el modo **Ruta principal de Windows (recomendado)**:

- Consulta únicamente la tabla de rutas local usando sockets UDP sin enviar datagramas, para detectar las direcciones origen IPv4/IPv6 que Windows utilizaría hacia Internet.
- Configura **listen_interfaces** (TCP/uTP, trackers UDP, DHT) y **outgoing_interfaces** (pares TCP) de libtorrent con esas direcciones; no fija ninguna IP persistente en el código.
- Comprueba cambios cada ~30 segundos. Si cambia la ruta, actualiza las interfaces nuevas. **Si deja de existir una ruta**, bloquea nuevos sockets P2P en lugar de volver silenciosamente a todas las interfaces.
- Conserva **puerto 0** (asignación automática) y los límites de velocidad, DHT, Smart Engine, Apex Bridge, programaciones y descargas existentes.
- Permite elegir **Compatibilidad: todas las interfaces** para recuperar manualmente el comportamiento de v1.3.5.

En **Red / Diagnóstico** se muestran las rutas, las interfaces seleccionadas y los errores; el botón *Detectar ruta de Windows* permite actualizar cuando cambies de Wi-Fi.

> **Limitaciones:** detección de la ruta local no prueba conectividad, disponibilidad de trackers o semillas. No sustituye un firewall ni ofrece un kill switch verificable para VPN. No fuerza el uso de Wi-Fi ni ignora una VPN si Windows cambia su ruta preferida. En redes IPv6-only o políticas corporativas de enrutamiento, quizá necesites el modo Compatibilidad. El modo recomendado no promete acelerar torrents sin fuentes.

## Actualizar conservando tu biblioteca

1. Cierra Apex Torrent desde la bandeja del sistema usando **Salir completamente**.
2. Copia `%LOCALAPPDATA%\ApexTorrent` a otro lugar como respaldo (contiene biblioteca, configuración, resume, historial y recibos Apex Bridge).
3. Extrae **el parche** directamente donde está `INICIAR_WINDOWS.bat` y reemplaza los archivos indicados.
4. Abre `INICIAR_WINDOWS.bat`. No requiere nuevas dependencias respecto a 1.3.5.
5. En Configuración verifica **Adaptador de red → Ruta principal de Windows** y **Puerto de escucha → Automático**. Guarda si cambias algo.
6. En Red / Diagnóstico pulsa *Detectar ruta de Windows* y compara la IP con `Get-NetIPConfiguration` de PowerShell.
7. Prueba primero un torrent oficial de Linux con semillas. Si no puedes conectar, compara con **Compatibilidad** y comparte un diagnóstico (oculta rutas/IP personales).

Para quienes todavía usan **1.3.4**, usa el parche específico *1.3.4 → 1.3.6* o el ZIP completo para no perder las novedades de Apex Bridge.

**Diagnóstico adicional:** `COMPROBAR_RED_WINDOWS.bat` (solo lee información; no cambia el firewall).

## Pruebas

`EJECUTAR_PRUEBAS.bat` ejecuta pruebas automatizadas offline. La suite comprueba configuración, registros locales, UI por análisis de código, integraciones y rutas simuladas. **La descarga real y los cambios de Wi-Fi deben validarse en Windows.** Los ZIP contienen código y scripts, no `.exe` precompilado.
