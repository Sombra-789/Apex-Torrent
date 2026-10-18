"""Perfiles de transferencia y muestras de ancho de banda, sin dependencias gráficas."""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass, field

PROFILES = {
    "Equilibrado": {"download_limit_kib": 0, "upload_limit_kib": 0, "connections_limit": 200, "active_downloads": 4, "active_seeds": 6},
    "Máximo rendimiento": {"download_limit_kib": 0, "upload_limit_kib": 0, "connections_limit": 350, "active_downloads": 8, "active_seeds": 8},
    "Red limitada": {"download_limit_kib": 2048, "upload_limit_kib": 256, "connections_limit": 80, "active_downloads": 2, "active_seeds": 3},
}

def profile_settings(name: str) -> dict:
    if name not in PROFILES:
        raise ValueError(f"Perfil desconocido: {name}")
    return {"profile": name, **PROFILES[name]}

@dataclass
class TransferHistory:
    capacity: int = 180
    downloads: deque = field(init=False)
    uploads: deque = field(init=False)

    def __post_init__(self):
        if self.capacity < 2:
            raise ValueError("La capacidad del historial debe ser al menos 2.")
        self.downloads = deque(maxlen=self.capacity)
        self.uploads = deque(maxlen=self.capacity)

    def append(self, down: float, up: float):
        self.downloads.append(max(0.0, float(down)))
        self.uploads.append(max(0.0, float(up)))

    def peak(self) -> float:
        return max((*self.downloads, *self.uploads, 1.0))


def network_insight(row: dict, tracker_list: list[dict]) -> str:
    """Nunca declara que un torrent esté muerto sin una prueba de disponibilidad."""
    if row.get("error"):
        return "Hay un error del motor: consulta el diagnóstico antes de cambiar ajustes."
    if row.get("paused"):
        return "La descarga está pausada. Reanúdala para buscar fuentes."
    if row.get("progress", 0) >= 1:
        return "Descarga completa. Puedes seguir compartiendo con otros pares."
    if row.get("seeds", 0) == 0 and row.get("down", 0) == 0:
        problems = sum(1 for x in tracker_list if str(x.get("state", "")).lower() == "error")
        suffix = f" ({problems} trackers con error registrados)." if problems else "."
        return "Sin semillas conectadas; esto no demuestra que el torrent carezca de fuentes" + suffix
    if row.get("down", 0) > 0:
        return "Descargando. La velocidad depende de tu red y de los pares que compartan piezas."
    return "Conectado pero sin transferencia útil por ahora; revisa semillas, pares y trackers."
