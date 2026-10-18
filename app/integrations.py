"""Apex Bridge v1: apertura conservadora de los programas complementarios.

NUNCA se presume que una app soporte un argumento CLI. Un manifiesto local
explícito, junto al .exe elegido por el usuario, es necesario para transmitir
solicitudes de archivo/carpeta. Ni lanzar ni pedir análisis implica seguridad.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

COMPANIONS = {
    'thunderbolt': 'Apex Antivirus Thunderbolt',
    'smart_files': 'Apex Smart Files',
}
BRIDGE_PROTOCOL = 'apex-bridge-v1'
ACTIONS = {'thunderbolt': ('scan_file',), 'smart_files': ('open_folder',)}
FLAGS = {'scan_file': '--apex-scan-file', 'open_folder': '--apex-open-folder'}


class IntegrationError(Exception):
    pass


def executable_path(text: str) -> Path:
    """Solo instaladores elegidos por el usuario; no busca y ejecuta binarios ajenos."""
    if not isinstance(text, str) or not text.strip() or len(text) > 4096:
        raise IntegrationError('Selecciona primero el ejecutable del programa.')
    target = Path(text.strip().strip('"')).expanduser()
    if target.suffix.lower() not in ('.exe', '.bat') or not target.is_file():
        raise IntegrationError('Elige un archivo .exe o INICIAR_WINDOWS.bat existente.')
    return target.resolve()


def capability(executable: Path, app: str, action: str) -> bool:
    """El contrato debe declarar la acción exacta; nunca inferir soporte por nombre."""
    if app not in COMPANIONS or action not in ACTIONS[app] or executable.suffix.lower() != '.exe':
        return False
    manifest = executable.parent / 'apex-bridge.json'
    try:
        if not manifest.is_file() or manifest.stat().st_size > 4096:
            return False
        obj = json.loads(manifest.read_text(encoding='utf-8'))
        return (isinstance(obj, dict) and obj.get('protocol') == BRIDGE_PROTOCOL
                and obj.get('app') == app and isinstance(obj.get('actions'), list)
                and action in obj['actions'])
    except (OSError, UnicodeError, ValueError, TypeError):
        return False


def selected_complete_file(root: str, candidate: str, complete: bool) -> Path:
    """Solo archivos reales dentro del directorio, completados según libtorrent."""
    if not complete:
        raise IntegrationError('Espera a que termine la descarga antes de enviar un archivo a revisión.')
    base = Path(root).expanduser().resolve(strict=True)
    path = Path(candidate).expanduser().resolve(strict=True)
    if path == base or not path.is_relative_to(base) or not path.is_file():
        raise IntegrationError('El archivo elegido no pertenece a la carpeta de la descarga.')
    return path


def selected_folder(root: str) -> Path:
    folder = Path(root).expanduser().resolve(strict=True)
    if not folder.is_dir():
        raise IntegrationError('La carpeta de descarga no existe todavía.')
    return folder


def start_companion(executable: str, app: str, action: str = 'open', target: Path | None = None) -> str:
    """No usa shell=True ni ejecuta documentos .torrent o archivos descargados.

    Retorna 'open' o 'requested'. 'requested' NO significa escaneado ni aprobado.
    """
    if app not in COMPANIONS or action not in ('open', *ACTIONS[app]):
        raise IntegrationError('Acción de integración no permitida.')
    path = executable_path(executable)
    if action != 'open' and not capability(path, app, action):
        raise IntegrationError('La aplicación elegida no declara compatibilidad Apex Bridge para esta acción.')
    if action != 'open':
        if target is None:
            raise IntegrationError('No se ha seleccionado un archivo o carpeta.')
        target = Path(target).resolve(strict=True)
        if action == 'scan_file' and not target.is_file():
            raise IntegrationError('Selecciona un archivo existente.')
        if action == 'open_folder' and not target.is_dir():
            raise IntegrationError('Selecciona una carpeta existente.')
    try:
        if path.suffix.lower() == '.bat':
            if action != 'open' or sys.platform != 'win32':
                raise IntegrationError('Los scripts .bat solo admiten apertura manual en Windows.')
            # Os.startfile usa ShellExecute; solo se usa para script elegido expresamente.
            os.startfile(str(path))
        else:
            argv = [str(path)] + ([FLAGS[action], str(target)] if action != 'open' else [])
            options = {'cwd': str(path.parent), 'shell': False}
            if sys.platform == 'win32':
                options['creationflags'] = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            subprocess.Popen(argv, **options)
    except (OSError, PermissionError) as exc:
        raise IntegrationError(f'No se pudo abrir {COMPANIONS[app]}: {exc}') from exc
    return 'requested' if action != 'open' else 'open'


def integration_state(executable: str, app: str) -> str:
    try:
        path = executable_path(executable)
    except IntegrationError:
        return 'No configurado o ruta no disponible'
    active = [a for a in ACTIONS[app] if capability(path, app, a)]
    if active:
        return 'Conectado · Apex Bridge: ' + ', '.join(active)
    return 'Disponible · apertura manual (sin contrato de análisis/importación)'
