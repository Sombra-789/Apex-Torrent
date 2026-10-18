# APEX Bridge v1 — contrato opcional entre aplicaciones

Esta especificación **no declara que las versiones ya publicadas de Thunderbolt y Smart Files admitan comandos**. Apex Torrent 1.3.4 utiliza un puente conservador.

## Lo que funciona sin modificar las otras aplicaciones

En **Ecosistema Apex**, el usuario elige el `.exe` o `INICIAR_WINDOWS.bat` auténtico de Thunderbolt y de Apex Smart Files. Apex Torrent guarda exclusivamente esas rutas en `%LOCALAPPDATA%\ApexTorrent\integrations.json`.

- Abre Thunderbolt para que el usuario analice manualmente un archivo completado; copia la ruta del archivo en el portapapeles. **Abrir el programa no constituye un análisis.**
- Abre Smart Files y, cuando no hay soporte de ruta nativo, abre en paralelo la carpeta seleccionada en el Explorador de Windows.
- No borra archivos, no hace transferencias a servidores, no desactiva el antivirus ni ejecuta contenido descargado.

## Protocolo optativo que falta implementar en cada aplicación receptora

Únicamente un programa `.exe` seleccionado por el usuario, con un archivo hermano `apex-bridge.json` que declare el contrato, recibe una ruta. Ejemplo **para una futura versión** de Thunderbolt:

```json
{"protocol":"apex-bridge-v1","app":"thunderbolt","actions":["scan_file"]}
```

Cuando el usuario pulsa **Revisar archivo completado** y el archivo es real, completo y está dentro de la carpeta seleccionada, Apex Torrent lanza:

```text
Thunderbolt.exe --apex-scan-file "C:\\ruta\\archivo"
```

Ejemplo para una **futura versión compatible** de Smart Files:

```json
{"protocol":"apex-bridge-v1","app":"smart_files","actions":["open_folder"]}
```

```text
SmartFiles.exe --apex-open-folder "C:\\ruta\\carpeta"
```

El receptor debe implementar explícitamente el argumento, validar la ruta, preguntar al usuario antes de operaciones destructivas y evitar ejecutar archivos no confiables. El manifiesto **declara capacidad**, no garantiza que la acción se haya ejecutado ni que el archivo esté libre de malware. La versión 1 del protocolo **no define un canal de respuestas firmado**; por eso Apex Torrent solamente confirma la solicitud, nunca un resultado de análisis.

Los `.bat` se abren sin argumentos (solo en Windows), para mantener compatibilidad con aplicaciones que todavía se ejecutan por Python.

## Privacidad y seguridad

- La ruta se usa localmente y se transmite a la otra aplicación solo mediante acción explícita del usuario.
- La integración de antivirus solo se ofrece a archivos marcados como completados y sin error; se impide escapar de la carpeta de descarga con rutas `..` o enlaces simbólicos.
- No se modifica el socket BitTorrent, el puerto automático, DHT ni el historial.
- Para probar la interoperabilidad real hace falta modificar el código de Thunderbolt y Smart Files para soportar el contrato y ejecutar pruebas en Windows.
