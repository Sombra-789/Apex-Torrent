"""Receptor de compatibilidad para apps antiguas sin API Apex Bridge.

Esto confirma APERTURA, no ejecución de análisis ni navegación interna.
Solo se llama después de una acción explícita del usuario.
"""
from __future__ import annotations
import argparse
import os
import subprocess
import sys
from pathlib import Path

from bridge_ipc import read_request, write_receipt
from integrations import executable_path


def run(request: Path, launcher: Path) -> str:
    obj = read_request(request)
    launcher = executable_path(str(launcher))
    if sys.platform == 'win32' and launcher.suffix.lower() == '.bat':
        os.startfile(str(launcher))
    else:
        opts = {'cwd': str(launcher.parent), 'shell': False,
                'stdin': subprocess.DEVNULL}
        if sys.platform == 'win32':
            opts['creationflags'] = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        subprocess.Popen([str(launcher)], **opts)
    if obj['app'] == 'smart_files':
        if sys.platform == 'win32':
            os.startfile(str(Path(obj['target'])))
        write_receipt(request, status='folder_opened', message='Smart Files y Explorador iniciados; apertura interna no confirmada.')
        return 'folder_opened'
    write_receipt(request, status='manual_required', message='Thunderbolt abierto. El usuario debe elegir el archivo y analizarlo manualmente.')
    return 'manual_required'


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--launcher', type=Path, required=True)
    args = parser.parse_args()
    try:
        run(args.request, args.launcher)
    except Exception as exc:
        try:
            write_receipt(args.request, status='failed', message=f'No se pudo abrir el programa: {type(exc).__name__}')
        except Exception:
            pass
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
