# Apex Bridge v2 — protocolo local con acuse de recepción

**El código de Thunderbolt y Smart Files no se incluye en este repositorio.** Apex Torrent 1.3.5 implementa el emisor, almacenamiento temporal, control de respuestas y un **relay de compatibilidad** para instalaciones antiguas. El relay abre la app y facilita la ruta, pero **NO** realiza análisis con Thunderbolt ni confirma navegación interna con Smart Files.

## Operación sin modificar otros programas

1. Configura en **Ecosistema Apex** las rutas reales de `ABRIR_THUNDERBOLT.bat` y `Abrir_Apex_Smart_Files.bat` (o sus `.exe`).
2. Selecciona un torrent completo y un archivo. Pulsa **Revisar archivo completado**.
3. Apex Torrent valida que esté dentro de la carpeta descargada, crea una solicitud temporal local en `%LOCALAPPDATA%\ApexTorrent\bridge`, abre Thunderbolt usando el relay y recibe `manual_required`. La ruta también se copia al portapapeles. **El usuario debe ejecutar el análisis desde Thunderbolt**.
4. Selecciona un torrent y pulsa **Abrir carpeta seleccionada**. Se abre Smart Files y, mientras no exista soporte nativo, también la carpeta en Explorer. El acuse es `folder_opened` con mensaje claro de que la navegación interna no se ha confirmado.
5. La interfaz muestra el acuse en Ecosistema Apex; el archivo de solicitud se elimina al terminar. No hay servidor web, socket, cloud ni envío por internet.

## Integración REAL en las dos aplicaciones (requiere editar su código fuente)

El programa receptor debe tener un `apex-bridge-v2.json` junto a su launcher elegido y un script Python receptor que importe el SDK `app/bridge_sdk.py` (también puede copiarse junto al receptor). Ejemplo de manifiesto Thunderbolt:

```json
{"protocol":"apex-bridge-v2","app":"thunderbolt","actions":["scan_file"],"receiver":"thunderbolt_bridge_receiver.py"}
```

Y Smart Files:

```json
{"protocol":"apex-bridge-v2","app":"smart_files","actions":["open_folder"],"receiver":"smartfiles_bridge_receiver.py"}
```

El receptor se inicia con `--request <ruta_local_request.json>` y debe llamar a:

```python
from bridge_sdk import thunderbolt_handle, smart_files_handle
# dentro del receptor Thunderbolt (llamada al MOTOR REAL):
# thunderbolt_handle(request_path, scan_callback=actual_scan_method)
# dentro del receptor Smart Files (llamada al NAVEGADOR REAL):
# smart_files_handle(request_path, open_folder_callback=actual_navigation_method)
```

Sin el callback real, estos métodos responden `unsupported` explícitamente. Ningún ejemplo devuelve `clean` por defecto.

### Ciclo de petición

- Emisor: `request.json` creado con ID aleatorio y escritura atómica.
- Receptor: comprueba protocolo, ID, acción, caducidad y que el archivo/carpeta exista. No interpreta rutas como comandos.
- Receptor: `receipt.json` con `request_id`, `app`, `action`, `status`, `message` y opcionalmente `verdict` **solo tras `scan_finished`**.
- Estados: `received`, `manual_required`, `folder_opened`, `scanning`, `scan_finished`, `scan_failed`, `failed`, `unsupported`.
- Emisor: comprueba ID, app y acción; descarta acuses no concordantes, elimina archivos de solicitud y presenta solo el estado realmente reportado.
- **Seguridad:** los acuses son datos de una aplicación ejecutándose con el mismo usuario de Windows, no firmas criptográficas. Un programa malicioso con ese usuario podría falsificarlos. La confirmación final de un análisis se debe consultar en Thunderbolt; incluso un veredicto `clean` no garantiza inocuidad absoluta.

## Límites del sistema actual

- No ejecuta archivos torrent ni ficheros recién descargados.
- No borra, pone en cuarentena, ni repara archivos automáticamente.
- No modifica los otros programas al instalar Apex Torrent.
- No necesita privilegios elevados ni abre puertos.
- Se necesita el ZIP de código fuente de Thunderbolt 1.3.5 y Smart Files 1.3 para conectar **sus APIs concretas**, validar los callbacks y probar ambos receptores en Windows.
- La versión compilada de Apex Torrent necesita acceso a un intérprete Python para ejecutar receptores `.py`; con su instalación mediante `.venv` ya lo tienes.
