# Apex Bridge v2 — Kit para Thunderbolt y Smart Files

Este kit contiene **plantillas para desarrolladores, NO receptores listos para usar**.
No renombres los archivos `.example.json` a `apex-bridge-v2.json` todavía.

## Para Thunderbolt

1. Copia `shared/bridge_ipc.py`, `shared/bridge_sdk.py`, `shared/integrations.py` y `thunderbolt/thunderbolt_bridge_receiver.py` junto al lanzador o al código de Thunderbolt.
2. Adapta `actual_scan_callback` para llamar al **motor de análisis real**; esa función recibe `Path` y devuelve `clean`, `threat` o `inconclusive` **solo al terminar el análisis**.
3. Prueba archivo limpio, simulación de fallo, archivo de prueba EICAR solo en entorno controlado de pruebas (sin incluirlo en la distribución), cancelación y archivo no autorizado.
4. Solo cuando termine la implementación, renombra `apex-bridge-v2.example.json` a `apex-bridge-v2.json` y colócalo junto al `.bat` o `.exe` seleccionado en Apex Torrent. Ajusta `receiver` si corresponde.
5. Prueba que Apex Torrent muestre un resultado reportado por Thunderbolt y que no acepte falsos estados de limpieza.

## Para Apex Smart Files

1. Copia los tres módulos `shared` y `smart_files/smartfiles_bridge_receiver.py` junto al lanzador de Smart Files.
2. Implementa `actual_open_folder_callback` usando la **navegación real** de Smart Files. Si ya hay una instancia abierta, usa el mecanismo de IPC existente o define uno antes de confirmar el acuse.
3. Devuelve `True` solo cuando la carpeta aparezca dentro de la app, no cuando Explorer la abra.
4. Solo cuando funcione, activa el manifiesto nativo `apex-bridge-v2.json`.

En versiones antiguas de ambas aplicaciones, Apex Torrent utiliza su **relay de compatibilidad** (apertura manual) sin necesidad de instalar este kit.
