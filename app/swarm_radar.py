"""Apex Swarm Radar alpha.1: observación local, sin acciones de red.

No infiere disponibilidad global de un torrent a partir de pares conectados.
Los porcentajes de peers son autorreportados y no demuestran que todas las
piezas requeridas estén presentes en el enjambre.
"""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class SwarmSnapshot:
    label: str
    detail: str
    peers: int
    seeds: int
    observed_max_progress: float | None
    payload_bps: int
    confidence: str

def _count(value: object) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError, OverflowError):
        return 0

def _progress(value: object) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not 0.0 <= result <= 1.0:
        return None
    return result

def summarize_swarm(row: dict, peers: list[dict] | None = None) -> SwarmSnapshot:
    peers_count = _count(row.get("peers"))
    seeds = min(peers_count, _count(row.get("seeds")))
    useful = _count(row.get("payload_down"))
    if row.get("payload_down") is None:
        useful = 0  # El tráfico total no prueba transferencia de piezas.
    readings = [_progress(p.get("progress")) for p in (peers or []) if isinstance(p, dict)]
    reported = [x for x in readings if x is not None]
    max_reported = max(reported) if reported else None
    state = str(row.get("state") or "")
    if state in ("Pausado", "Fuera de horario"):
        label, detail = "En pausa", "No se deduce disponibilidad mientras el torrent está pausado."
    elif _progress(row.get("progress")) == 1.0:
        label, detail = "Completado", "El contenido local figura como completo; los pares pueden cambiar."
    elif useful > 0:
        label, detail = "Transfiriendo piezas", "Libtorrent informa velocidad útil positiva en este instante."
    elif seeds > 0:
        label, detail = "Semillas conectadas", "Hay semillas conectadas; no se garantiza transferencia."
    elif peers_count > 0:
        label, detail = "Pares parciales", "Hay pares conectados, pero ninguna semilla conectada confirmada."
    else:
        label, detail = "Sin fuentes conectadas", "No hay pares conectados ahora; NO significa torrent abandonado."
    return SwarmSnapshot(label, detail, peers_count, seeds, max_reported, useful,
                         "Instantánea local; no mide el enjambre completo")

def radar_text(snapshot: SwarmSnapshot) -> str:
    observed = ("No medido" if snapshot.observed_max_progress is None
                else f"{snapshot.observed_max_progress * 100:.1f}% (máximo observado; no cobertura total)")
    return (f"{snapshot.label}\n{snapshot.detail}\n"
            f"Pares conectados: {snapshot.peers} | Semillas conectadas: {snapshot.seeds}\n"
            f"Progreso mayor entre pares consultados: {observed}\n"
            f"Tráfico útil: {snapshot.payload_bps} B/s\n{snapshot.confidence}")
