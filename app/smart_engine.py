"""Smart Engine: límites conservadores y recomendaciones observables.

No mide por sí solo la capacidad contratada de la red y no bloquea trackers.
El control automático de subida solo se aplica con consentimiento explícito y
una velocidad ascendente suministrada por el usuario.
"""
from __future__ import annotations
from collections import Counter


def effective_upload_limit_kib(settings: dict) -> int:
    """Devuelve el límite real (0 = ilimitado). Respeta siempre el límite manual."""
    manual = max(0, int(settings.get('upload_limit_kib', 0)))
    if not settings.get('smart_engine_enabled', False):
        return manual
    mbps = int(settings.get('upload_capacity_mbps', 0))
    reserve = int(settings.get('smart_upload_percent', 80))
    if not 1 <= mbps <= 1000 or not 50 <= reserve <= 90:
        raise ValueError('Smart Engine requiere subida medida entre 1–1000 Mbps y objetivo entre 50–90 %.')
    candidate = max(1, round(mbps * 1_000_000 / 8 / 1024 * reserve / 100))
    return min(candidate, manual) if manual else candidate


def smart_upload_report(settings: dict) -> str:
    if not settings.get('smart_engine_enabled', False):
        return 'Smart Engine desactivado: se aplican los límites manuales.'
    limit = effective_upload_limit_kib(settings)
    pct = int(settings.get('smart_upload_percent', 80))
    return (f'Smart Engine activo: límite de subida {limit:,} KiB/s. '
            f'Objetivo {pct}% de la capacidad declarada, respetando cualquier límite manual inferior. '
            'No detecta automáticamente la velocidad contratada ni cambia el puerto.')


def classify_tracker_error(message: str) -> str:
    m = str(message or '').casefold()
    if any(term in m for term in ('host desconocido', 'name or service not known',
                                   'getaddrinfo failed', 'no such host', 'dns',
                                   'resolución de nombres', 'name resolution')):
        return 'DNS / nombre no resuelto'
    if any(term in m for term in ('timed out', 'timeout', 'tiempo de espera',
                                   'no respondió', 'no respond', 'periodo de tiempo')):
        return 'Tiempo de espera'
    if any(term in m for term in ('[::1]', '192.168.56.', 'red no accesible',
                                   'network is unreachable', 'skipping tracker announce')):
        return 'Interfaz / red no accesible'
    if any(term in m for term in ('denegó', 'refused', 'rechazó', 'forbidden')):
        return 'Conexión rechazada'
    return 'Otros errores'


def tracker_diagnosis(entries: list[dict]) -> dict:
    """No penaliza anuncios pendientes ni deduce semillas de errores de tracker."""
    from ultimate import tracker_summary
    summary = tracker_summary(entries)
    causes = Counter()
    visited = set()
    for entry in entries:
        url = str(entry.get('url', ''))
        if url in visited or not url.startswith(('http://','https://','udp://')):
            continue
        visited.add(url)
        if str(entry.get('state', '')).casefold() == 'error':
            causes[classify_tracker_error(entry.get('message', ''))] += 1
    return {'counts': summary, 'causes': causes.most_common(4)}


def swarm_hint(row: dict | None, entry_count: dict | None = None) -> str:
    if not row:
        return 'Selecciona un torrent para diagnosticar la disponibilidad.'
    if row.get('error'):
        return 'El motor informa un error; abre Diagnóstico antes de cambiar la red.'
    if row.get('paused'):
        return 'Torrent pausado; no es posible evaluar su actividad hasta reanudarlo.'
    if row.get('progress', 0) >= 1:
        return 'Descarga completa: las semillas son fuentes, no una medida de calidad de internet.'
    if row.get('down', 0) > 0:
        return 'Transferencia activa. Aumentar el número de conexiones no garantiza más velocidad.'
    if row.get('seeds', 0) <= 0:
        return 'No hay semillas conectadas. Podría ser escasez de fuentes o descubrimiento insuficiente.'
    if row.get('peers', 0) > 0:
        return 'Hay pares conectados pero no transfieren datos útiles todavía.'
    return 'Sin pares conectados; revisa los trackers y prueba una descarga legal con semillas conocidas.'
