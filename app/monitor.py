"""Métricas del proceso e historial LOCAL compacto para Apex Torrent.

Sin capturar contenido, nombres de torrent, IPs ni trackers.
Persistencia acotada; errores del monitor nunca deben detener las descargas.
"""
from __future__ import annotations
import os
from contextlib import contextmanager
import sqlite3
import time
from pathlib import Path


class ProcessSampler:
    """psutil es opcional: devuelve N/D si no se puede consultar el proceso."""
    def __init__(self):
        try:
            import psutil
            self._proc = psutil.Process(os.getpid())
            self._proc.cpu_percent(interval=None)
        except (ImportError, OSError, RuntimeError):
            self._proc = None

    def read(self) -> dict:
        if self._proc is None:
            return {'cpu_percent': None, 'rss_bytes': None}
        try:
            return {'cpu_percent': max(0.0, self._proc.cpu_percent(interval=None)),
                    'rss_bytes': max(0, int(self._proc.memory_info().rss))}
        except (OSError, RuntimeError, AttributeError):
            return {'cpu_percent': None, 'rss_bytes': None}


class PerformanceJournal:
    """Una fila cada ~15 s, retención máxima 7 días; no toca descargas."""
    MAX_AGE_SECONDS = 7 * 86400

    def __init__(self, directory: Path):
        self.path = Path(directory) / 'performance.sqlite3'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._writes = 0
        with self._connect() as connection:
            connection.execute('''CREATE TABLE IF NOT EXISTS samples (
                timestamp INTEGER PRIMARY KEY,
                download_bps INTEGER NOT NULL,
                upload_bps INTEGER NOT NULL,
                peers INTEGER NOT NULL,
                cpu_pct REAL,
                rss_bytes INTEGER
            )''')

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(str(self.path), timeout=0.3)
        try:
            connection.execute('PRAGMA busy_timeout=300')
            with connection:
                yield connection
        finally:
            connection.close()

    def append(self, down: int, up: int, peers: int, cpu: float | None,
               rss: int | None, timestamp: int | None = None) -> None:
        ts = int(time.time()) if timestamp is None else int(timestamp)
        with self._connect() as connection:
            connection.execute('''INSERT OR REPLACE INTO samples
                (timestamp, download_bps, upload_bps, peers, cpu_pct, rss_bytes)
                VALUES (?, ?, ?, ?, ?, ?)''', (
                ts, max(0, int(down)), max(0, int(up)), max(0, int(peers)),
                max(0., float(cpu)) if cpu is not None else None,
                max(0, int(rss)) if rss is not None else None,
            ))
            self._writes += 1
            if self._writes == 1 or self._writes % 240 == 0:
                connection.execute('DELETE FROM samples WHERE timestamp < ?',
                                   (ts - self.MAX_AGE_SECONDS,))

    def summary(self, hours: int = 24, now: int | None = None) -> dict:
        if not 1 <= hours <= 168:
            raise ValueError('El intervalo debe estar entre 1 y 168 horas.')
        ts = int(time.time()) if now is None else int(now)
        with self._connect() as connection:
            result = connection.execute('''SELECT COUNT(*), MAX(download_bps),
                MAX(upload_bps), AVG(download_bps), AVG(upload_bps)
                FROM samples WHERE timestamp >= ? AND timestamp <= ?''',
                (ts - hours * 3600, ts)).fetchone()
        count, peak_down, peak_up, average_down, average_up = result
        return {'count': int(count), 'peak_down': int(peak_down or 0),
                'peak_up': int(peak_up or 0),
                'average_down': int(average_down or 0),
                'average_up': int(average_up or 0)}
