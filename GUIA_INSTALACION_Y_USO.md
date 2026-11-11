# Manual de instalación y uso — Apex Torrent

Gestiona descargas BitTorrent mediante archivos .torrent o enlaces magnet, con biblioteca, pares, trackers y diagnóstico de red.

[Inicio](README.md) · [Soporte y plantilla](CONTACTO_Y_SOPORTE.md)

## Antes de empezar

Las opciones empaquetadas descritas están orientadas a Windows x64. Necesitas espacio para la aplicación y tus archivos; las descargas y la primera preparación desde código requieren Internet. Un archivo **ZIP** es una carpeta comprimida: usa clic derecho → **Extraer todo** antes de abrir el programa. El código descargado de **main** puede corresponder a una edición diferente de las Releases.

## Instalación paso a paso

### Desde el código de este repositorio (candidato 1.3.8)

1. Instala Python 3.12 o 3.13 **de 64 bits** desde [python.org](https://www.python.org/downloads/), incluyendo Python Launcher (py).
2. En GitHub abre **Code → Download ZIP**. Extrae todo en una carpeta donde puedas guardar archivos; no ejecutes nada dentro del ZIP.
3. Abre `INSTALAR_WINDOWS.bat`. Espera a que prepare el entorno y confirme la instalación; necesita Internet para descargar dependencias.
4. Abre `INICIAR_WINDOWS.bat`. En siguientes ocasiones utiliza el mismo archivo o el acceso directo.
5. Si falla, ejecuta `VERIFICAR_WINDOWS.bat` y guarda el mensaje para soporte.

### Paquetes de pruebas

No hay una Release publicada al momento de esta revisión (11 de noviembre de 2026). Consulta [Actions](https://github.com/Sombra-789/Apex-Torrent/actions) si necesitas un paquete generado: elige una ejecución correcta, comprueba su versión y descarga Artifacts. Puede exigir una cuenta GitHub y los archivos pueden caducar. Una compilación alpha de Actions puede diferir del código de main; no la trates como estable.

## Primer uso

1. Abre la aplicación y añade un archivo .torrent o enlace magnet cuyo intercambio esté autorizado.
2. Elige la carpeta de destino con espacio suficiente y confirma el inicio.
3. Selecciona la descarga para consultar progreso, archivos, semillas y pares. Puedes pausar y reanudar desde la biblioteca.
4. Si no avanza, revisa **Red / Diagnóstico**. **Intentar recuperar fuentes** solicita otro intento de descubrimiento; **Verificar archivos** comprueba piezas locales.
5. Para cerrar antes de actualizar, usa **Salir completamente** desde la bandeja del sistema.

## Dependencias y para qué sirven

La tabla corresponde a los archivos de dependencias de **main** revisados el 11 de noviembre de 2026. Los paquetes compilados incluyen sus propios componentes; no instales estas bibliotecas manualmente para usar un paquete que ya las incorpora.

| Componente | Para qué sirve |
| --- | --- |
| Python 3.12/3.13 x64 | Ejecuta el código y crea el entorno aislado .venv. |
| PySide6 >=6.9,<7 | Muestra la interfaz gráfica. |
| libtorrent ==2.0.15 | Realiza las transferencias y gestiona el protocolo BitTorrent. |
| psutil >=6,<8 | Consulta recursos del equipo para monitorización. |

Consulta [requirements.txt](requirements.txt) para los rangos declarados. No es necesario instalar otros proyectos Apex para las funciones básicas.

## Comprobar una descarga en Windows

Abre PowerShell en la carpeta donde descargaste el paquete y ejecuta, sustituyendo el nombre por el archivo real:

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath ".\NOMBRE_DEL_ARCHIVO"
```

Compara el valor **Hash** completo con el de su archivo `.sha256` o `SHA256SUMS.txt`. Deben coincidir; si difieren, no uses ese paquete. La coincidencia ayuda a detectar cambios respecto a la huella publicada, pero no sustituye una firma digital ni acredita por sí sola la identidad del autor.

## Si algo falla

1. Confirma qué edición y versión abriste y que extrajiste el paquete completo.
2. Si usas código, verifica la versión de Python indicada y conserva el mensaje del instalador de dependencias.
3. Si falta un componente o el antivirus muestra una alerta, guarda el mensaje y consulta soporte antes de modificar protecciones.
4. Envía la [plantilla de soporte](CONTACTO_Y_SOPORTE.md) a [apexsoftware.inc07@gmail.com](mailto:apexsoftware.inc07@gmail.com).

## Limitaciones

- Sin semillas o pares disponibles puede no haber descarga. No crea fuentes ni garantiza velocidad.
- Trackers, DHT y conectividad dependen de la red, sus políticas y los participantes.
- La detección de ruta de Windows no ofrece un kill switch verificable para VPN.
- El código de main se presenta como candidato de prueba; las pruebas simuladas no acreditan transferencias reales ni toda la interfaz en Windows.

## Actualizar y conservar tus datos

Cierra desde la bandeja y respalda `%LOCALAPPDATA%\ApexTorrent`. Sigue las instrucciones específicas de la versión en el README antes de reemplazar archivos.

El proyecto está abierto a futuras actualizaciones de mantenimiento, seguridad, compatibilidad y mejoras. Las propuestas son bienvenidas por el canal de soporte; no se prometen funciones ni fechas de entrega.

## Documentación y versiones

El [README](README.md) conserva notas técnicas, estado y enlaces propios del proyecto. La documentación histórica describe la versión que indica su título; no debe aplicarse automáticamente a otra edición.
