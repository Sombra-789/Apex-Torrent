"""Diagnóstico prudente de un torrent, sin alterar trackers ni el tráfico.

Distingue hechos observados de hipótesis. Los avisos nunca equivalen a
certificar que un torrent está muerto, ni exigen desactivar protecciones.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Diagnosis:
    code: str
    title: str
    severity: str
    evidence: str
    advice: str

    def report(self) -> str:
        return (f"{self.title}\nNivel: { {'info':'informativo', 'warning':'advertencia', 'error':'error'}.get(self.severity, self.severity)}\n"
                f"Observado: {self.evidence}\nQué hacer: {self.advice}")


def tracker_counts(trackers: list[dict] | None) -> dict[str, int]:
    counts = {'total': 0, 'respondieron': 0, 'errores': 0, 'anunciando': 0, 'otros': 0}
    seen = set()
    for item in trackers or []:
        url = str(item.get('url', ''))
        if not url.startswith(('http://', 'https://', 'udp://')) or url in seen:
            continue
        seen.add(url)
        counts['total'] += 1
        state = str(item.get('state', '')).casefold()
        if state == 'respondió':
            counts['respondieron'] += 1
        elif state == 'error':
            counts['errores'] += 1
        elif state == 'anunciando':
            counts['anunciando'] += 1
        else:
            counts['otros'] += 1
    return counts


def diagnose(row: dict, trackers: list[dict] | None = None, *,
             dht_enabled: bool = True, listen_ok: bool | None = None) -> Diagnosis:
    """Solo orienta usando telemetría conocida; nunca prueba disponibilidad global."""
    status = str(row.get('state', '')).casefold()
    peers = max(0, int(row.get('peers') or 0))
    seeds = max(0, int(row.get('seeds') or 0))
    down = max(0, int(row.get('down') or 0))
    progress = max(0.0, min(1.0, float(row.get('progress') or 0.0)))
    idle = max(0, int(row.get('idle_seconds') or 0))
    counts = tracker_counts(trackers)
    evidence = (f"{peers} pares, {seeds} semillas conectadas; "
                f"trackers: {counts['respondieron']} respondieron, "
                f"{counts['errores']} fallaron, {counts['anunciando']} anunciando. "
                f"Sin transferencia medida durante {idle} s.")
    if row.get('error') or status in ('error', 'no disponible'):
        message = str(row.get('error') or 'La descarga no pudo recuperarse.').strip()
        return Diagnosis('motor_error', 'La descarga reporta un error', 'error', message,
                         str(row.get('error_hint') or 'Revisa el error, la carpeta de destino y el registro de diagnóstico.'))
    if status == 'fuera de horario':
        return Diagnosis('scheduled', 'Fuera de la ventana programada', 'info',
                         'El planificador está activo.', 'Espera el horario permitido o modifícalo en Configuración.')
    if status == 'pausado' or row.get('paused'):
        return Diagnosis('paused', 'Descarga pausada', 'info', 'Pausa manual o del usuario.',
                         'Pulsa Reanudar si deseas continuar.')
    if progress >= 1.0 or status in ('completado', 'compartiendo'):
        return Diagnosis('complete', 'Descarga completada', 'ok',
                         f"Progreso {progress * 100:.1f}%.",
                         'Los datos están completos según libtorrent; puedes verificar las piezas si lo deseas.')
    if down > 0:
        return Diagnosis('transferring', 'Transferencia activa', 'ok',
                         f"Descarga a {down} bytes/s con {peers} pares conectados.",
                         'La velocidad depende de las fuentes y de la conexión disponible.')
    if status in ('verificando', 'reanudando'):
        return Diagnosis('checking', 'Comprobando los datos locales', 'info', status.title(),
                         'Espera a que termine la revisión de las piezas.')
    if listen_ok is False:
        return Diagnosis('listen', 'No se confirmó una interfaz de escucha', 'warning',
                         'Se registraron fallos al abrir los sockets y ninguna escucha confirmada.',
                         'Revisa Red / Diagnóstico. Conserva el puerto automático; no desactives el firewall.')
    if status == 'metadatos':
        return Diagnosis('metadata', 'Esperando metadatos del magnet', 'warning' if idle >= 180 else 'info',
                         evidence, 'Espera la conexión con pares que aporten metadatos; revisa DHT y trackers. '
                                   'El enlace por sí solo no incluye la lista de archivos.')
    if seeds == 0 and down == 0 and counts['total'] and counts['errores'] == counts['total']:
        return Diagnosis('trackers_failed', 'No hay fuentes conectadas y fallaron todos los trackers',
                         'warning', evidence,
                         'Los trackers registrados no han respondido correctamente. DHT/PEX aún pueden localizar pares. '
                         'Comprueba si un torrent oficial conocido descarga en esta red. No agregues listas masivas al azar.')
    if seeds == 0 and down == 0 and counts['errores'] > 0 and counts['respondieron'] == 0:
        return Diagnosis('tracker_partial', 'Sin semillas conectadas; varios trackers fallan',
                         'warning' if idle >= 120 else 'info', evidence,
                         'Puede deberse a trackers obsoletos o falta temporal de fuentes. '
                         'Revisa la pestaña Trackers y compara con un torrent legal de prueba.')
    if seeds == 0 and down == 0 and idle >= 180:
        return Diagnosis('no_seed_observed', 'No se observan semillas que transfieran datos',
                         'warning', evidence,
                         'No demuestra que el torrent esté muerto. Comprueba si el mismo torrent funciona en otro cliente; '
                         'si tampoco avanza, busca una fuente autorizada con más disponibilidad.')
    if down == 0 and not dht_enabled and counts['respondieron'] == 0:
        return Diagnosis('discovery', 'Descubrimiento de pares limitado', 'warning', evidence,
                         'DHT está desactivada y ningún tracker confirmó una respuesta. '
                         'Si el torrent lo permite, activa DHT en Configuración.')
    return Diagnosis('waiting', 'Esperando fuentes de descarga', 'info', evidence,
                     'Es normal al comenzar. Espera unos minutos y revisa los trackers. '
                     'La ausencia de semillas conectadas no demuestra que no existan.')
