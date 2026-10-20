# Apex Swarm Radar — Alpha 1

**Rama:** `develop/1.4-evolution`. La rama `main` continúa como Apex Torrent 1.3.8 Stable.

## Alcance de esta entrega
- Nueva pestaña **Swarm Radar** en detalles del torrent seleccionado.
- Observación de pares conectados, semillas conectadas, máxima proporción declarada entre pares consultados y tasa de tráfico de contenido **solo cuando libtorrent la proporciona**.
- Interpretación conservadora: **0 semillas conectadas no demuestra ausencia global de fuentes**; el progreso máximo de un par no equivale a cobertura de todas las piezas del enjambre.
- Sin cambios en puertos, DHT, trackers, caché, descargas, archivos o configuración existente.

## Pruebas
- Nueve pruebas de lógica independiente de Qt/libtorrent en `tests/test_swarm_radar.py`.
- Pendiente validar las pruebas completas de Windows, la pestaña visual, una descarga Ubuntu de referencia y que no exista degradación mensurable del motor.
- Comparar memoria, CPU y velocidad con v1.3.8 en la misma red y contenido, repitiendo muestras.

## Criterios de salida de Alpha 1
1. Pruebas previas de regresión + Swarm Radar sin fallos.
2. La UI abre y cambia de pestañas sin congelamientos, especialmente con 0 y 100 pares.
3. Los mensajes no afirman que un torrent esté muerto sin evidencia.
4. La rama estable `main` y el instalador de 1.3.8 permanecen sin cambios.

## Próxima iteración
Añadir historial de disponibilidad limitada temporalmente (solo agregados numéricos locales) y cobertura de piezas si el binding de libtorrent permite obtener datos fiables y medibles sin escaneos caros. No almacenar direcciones IP de pares.
