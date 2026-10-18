"""Apex Torrent Ultimate: diagnósticos prudentes sin alterar el tráfico P2P.

No deduce si un torrent está muerto ni afirma que un archivo sea seguro.
"""
from __future__ import annotations
import hashlib
import shutil
from pathlib import Path, PurePosixPath

DANGEROUS_EXTENSIONS = frozenset({'.exe', '.com', '.scr', '.bat', '.cmd', '.ps1', '.vbs',
                                  '.vbe', '.js', '.jse', '.msi', '.msp', '.hta', '.lnk', '.wsf'})
ARCHIVE_EXTENSIONS = frozenset({'.zip', '.rar', '.7z', '.iso', '.tar', '.gz'})


def tracker_summary(entries: list[dict]) -> dict:
    """Cuenta respuestas comprobadas; «Anunciando» no significa éxito."""
    counts = {'total': 0, 'respondieron': 0, 'errores': 0, 'anunciando': 0,
              'sin_respuesta': 0}
    seen = set()
    for entry in entries:
        url = str(entry.get('url', ''))
        if url in seen or not url.startswith(('udp://', 'http://', 'https://')):
            continue
        seen.add(url)
        counts['total'] += 1
        state = str(entry.get('state', '')).casefold()
        if state == 'respondió':
            counts['respondieron'] += 1
        elif state == 'error':
            counts['errores'] += 1
        elif state == 'anunciando':
            counts['anunciando'] += 1
        else:
            counts['sin_respuesta'] += 1
    return counts


def inspect_names(entries: list[dict]) -> dict:
    """Metadatos .torrent, nunca ejecuta, lee ni abre contenido no confiable."""
    executable = []
    archives = 0
    for entry in entries:
        path = str(entry.get('path', ''))
        extension = PurePosixPath(path.replace('\\', '/')).suffix.casefold()
        if extension in DANGEROUS_EXTENSIONS:
            executable.append(path)
        if extension in ARCHIVE_EXTENSIONS:
            archives += 1
    return {'files': len(entries), 'executable_count': len(executable),
            'executable_samples': executable[:12], 'archives': archives}


def disk_estimate(save_path: str, expected_bytes: int, downloaded_bytes: int) -> dict:
    """Aviso orientativo; disco disperso y archivos compartidos cambian el resultado."""
    try:
        root = Path(save_path).expanduser()
        root = next((p for p in (root, *root.parents) if p.is_dir()), None)
        if root is None:
            return {'available': None, 'remaining': None, 'enough': None}
        available = shutil.disk_usage(root).free
        remaining = max(0, int(expected_bytes) - max(0, int(downloaded_bytes)))
        return {'available': available, 'remaining': remaining,
                'enough': available >= remaining}
    except (OSError, ValueError, TypeError, OverflowError):
        return {'available': None, 'remaining': None, 'enough': None}


def safe_download_path(root: str, name: str) -> Path:
    """Restringe operaciones voluntarias de análisis a la carpeta destino."""
    base = Path(root).expanduser().resolve()
    path = (base / name).resolve()
    if not path.is_relative_to(base) or path == base:
        raise ValueError('El archivo está fuera de la carpeta de descarga.')
    if not path.is_file():
        raise ValueError('El archivo todavía no existe o no es regular.')
    return path


def file_sha256(path: Path, block_size: int = 1024 * 1024) -> str:
    """Lectura secuencial en segundo plano: no modifica archivos."""
    if block_size <= 0:
        raise ValueError('Bloque inválido')
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for data in iter(lambda: stream.read(block_size), b''):
            digest.update(data)
    return digest.hexdigest()
