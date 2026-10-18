"""Persistencia local y utilidades de Apex Torrent 1.0."""
from __future__ import annotations
import json
import os
import tempfile
from pathlib import Path

VERSION = "1.3.8"
APP_NAME = "Apex Torrent"
DATA_DIR = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / ".local" / "share")) / "ApexTorrent"


def initial_settings() -> dict:
    return {
        "download_dir": str(Path.home() / "Downloads" / "Apex Torrent"),
        "download_limit_kib": 0,
        "upload_limit_kib": 0,
        "connections_limit": 200,
        "profile": "Equilibrado",
        "accent_theme": "Azul",
        "active_downloads": 4,
        "active_seeds": 6,
        "listen_port": 0,  # 0=automático: Windows selecciona puerto libre.
        "network_mode": "route",  # ruta de Windows, sin desviar tráfico por interfaces virtuales.
        "auto_resume": True,
        "dht": True,
        "upnp": True,
        "background_enabled": False,  # Cerrar ventana no oculta la app salvo opt-in.
        "notify_finished": True,
        "notify_problems": False,  # Avisos emergentes opcionales, nunca por defecto.
        "schedule_enabled": False,
        "schedule_start_hour": 0,
        "schedule_end_hour": 0,
        "smart_engine_enabled": False,
        "upload_capacity_mbps": 0,  # 0 = no medida; nunca activado automáticamente.
        "smart_upload_percent": 80,  # capacidad declarada reservada a BitTorrent.
    }


def readable_size(number: float | int | None) -> str:
    if number is None or number < 0:
        return "—"
    value = float(number)
    for suffix in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(value) < 1024 or suffix == "TiB":
            return f"{value:.0f} B" if suffix == "B" else f"{value:.1f} {suffix}"
        value /= 1024
    return "—"


def readable_speed(number: float | int | None) -> str:
    return f"{readable_size(number)}/s" if number and number > 0 else "0 B/s"


def readable_eta(seconds: int | float | None) -> str:
    if seconds is None or seconds < 0 or seconds > 6048000:
        return "—"
    n = int(seconds)
    if n < 60:
        return f"{n} s"
    if n < 3600:
        return f"{n // 60} min"
    if n < 86400:
        return f"{n // 3600} h {n % 3600 // 60} min"
    return f"{n // 86400} d {n % 86400 // 3600} h"


class Store:
    """JSON atómico bajo el perfil local del usuario; sin servicios externos."""
    def __init__(self, base: Path = DATA_DIR):
        self.base = Path(base)
        self.base.mkdir(parents=True, exist_ok=True)
        (self.base / "torrents").mkdir(exist_ok=True)
        (self.base / "resume").mkdir(exist_ok=True)

    def load_json(self, filename: str, default):
        path = self.base / filename
        if not path.is_file():
            return default
        try:
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError, UnicodeError):
            return default

    def save_json(self, filename: str, data) -> None:
        destination = self.base / filename
        fd, filename_tmp = tempfile.mkstemp(prefix=".apex-", suffix=".tmp", dir=self.base)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(filename_tmp, destination)
        finally:
            if os.path.exists(filename_tmp):
                os.unlink(filename_tmp)

    def load_settings(self) -> dict:
        settings = initial_settings()
        saved = self.load_json("settings.json", {})
        if isinstance(saved, dict):
            settings.update({key: value for key, value in saved.items() if key in settings})
        return settings

    def load_records(self) -> list[dict]:
        data = self.load_json("downloads.json", [])
        if not isinstance(data, list):
            return []
        return [d for d in data if isinstance(d, dict) and all(k in d for k in ("id", "source", "save_path", "kind"))]

    def save_records(self, records: dict[str, dict]):
        self.save_json("downloads.json", list(records.values()))
