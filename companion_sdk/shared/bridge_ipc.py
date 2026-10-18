"""Apex Bridge v2: intercambio local con acuse explícito, sin red ni ejecución de descargas.

Ningún recibo constituye por sí mismo un resultado antivirus. Para un veredicto
real, el receptor Thunderbolt debe implementar una operación de análisis y
confirmarla después de terminar, usando su propio motor.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from integrations import (ACTIONS, COMPANIONS, IntegrationError, executable_path)

PROTOCOL = 'apex-bridge-v2'
STATUSES = frozenset({'received', 'manual_required', 'folder_opened', 'scanning',
                      'scan_finished', 'scan_failed', 'failed', 'unsupported'})
VERDICTS = frozenset({'clean', 'threat', 'inconclusive'})
MAX_JSON_BYTES = 8192
MAX_AGE_SECONDS = 3600


@dataclass(frozen=True)
class BridgeTicket:
    id: str
    app: str
    action: str
    request_path: Path
    receipt_path: Path
    launched_at: float


def _atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.parent / ('.' + uuid.uuid4().hex + '.tmp')
    try:
        with temp.open('x', encoding='utf-8') as handle:
            json.dump(data, handle, ensure_ascii=False, separators=(',', ':'))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _read_json(path: Path) -> dict:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_JSON_BYTES:
            raise IntegrationError('Archivo Apex Bridge inválido o excesivo.')
        data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            raise ValueError('Objeto JSON requerido')
        return data
    except (OSError, UnicodeError, ValueError) as exc:
        raise IntegrationError('No se pudo leer una respuesta válida de Apex Bridge.') from exc


def _allowed_target(app: str, action: str, target: Path) -> Path:
    if app not in COMPANIONS or action not in ACTIONS[app]:
        raise IntegrationError('Acción de Apex Bridge no admitida.')
    path = Path(target).expanduser().resolve(strict=True)
    if (action == 'scan_file' and not path.is_file()) or (action == 'open_folder' and not path.is_dir()):
        raise IntegrationError('El destino de la solicitud no existe o tiene un tipo incorrecto.')
    return path


def _python() -> str:
    if not getattr(sys, 'frozen', False):
        return sys.executable
    # En una distribución compilada buscar primero su entorno virtual local.
    base = Path(sys.executable).resolve().parent
    local = (base / '.venv' / 'Scripts' / 'pythonw.exe',
             base.parent / '.venv' / 'Scripts' / 'pythonw.exe',
             base / '.venv' / 'Scripts' / 'python.exe',
             base.parent / '.venv' / 'Scripts' / 'python.exe')
    candidate = next((str(path) for path in local if path.is_file()), None)
    candidate = candidate or shutil.which('pythonw') or shutil.which('python')
    if candidate:
        return candidate
    raise IntegrationError('El receptor Apex Bridge requiere Python. Abre la app manualmente o instala el runtime.')


def receiver_script(launcher: Path, app: str, action: str) -> Path | None:
    """Un manifiesto explícito declara un receptor real dentro de su propia carpeta.

    No toma comandos arbitrarios de un JSON: solo permite un archivo .py
    resuelto dentro del directorio elegido manualmente por el usuario.
    """
    manifest = launcher.parent / 'apex-bridge-v2.json'
    if not manifest.is_file() or manifest.is_symlink() or manifest.stat().st_size > 4096:
        return None
    try:
        obj = json.loads(manifest.read_text(encoding='utf-8'))
        if (not isinstance(obj, dict) or obj.get('protocol') != PROTOCOL or
            obj.get('app') != app or action not in obj.get('actions', [])):
            return None
        name = obj.get('receiver')
        if not isinstance(name, str) or not name.endswith('.py') or name != Path(name).name:
            return None
        candidate = (launcher.parent / name).resolve(strict=True)
        if not candidate.is_file() or not candidate.is_relative_to(launcher.parent.resolve()):
            return None
        return candidate
    except (OSError, ValueError, TypeError):
        return None


def prepare_ticket(root: Path, app: str, action: str, target: Path,
                   approved_root: Path | None = None) -> BridgeTicket:
    target = _allowed_target(app, action, target)
    if approved_root is None:
        approved_root = target.parent if action == 'scan_file' else target
    approved_root = Path(approved_root).expanduser().resolve(strict=True)
    if not approved_root.is_dir() or not target.is_relative_to(approved_root):
        raise IntegrationError('El archivo no pertenece a la carpeta de descarga autorizada.')
    key = uuid.uuid4().hex
    folder = Path(root) / 'bridge' / key
    folder.mkdir(parents=True, exist_ok=False)
    request = folder / 'request.json'
    receipt = folder / 'receipt.json'
    timestamp = time.time()
    _atomic_json(request, {
        'protocol': PROTOCOL, 'request_id': key, 'app': app, 'action': action,
        'target': str(target), 'approved_root': str(approved_root), 'created_at': int(timestamp),
        'origin': 'Apex Torrent',
    })
    return BridgeTicket(key, app, action, request, receipt, timestamp)


def send_request(root: Path, executable: str, app: str, action: str,
                 target: Path, approved_root: Path | None = None) -> tuple[BridgeTicket, str]:
    launcher = executable_path(executable)
    ticket = prepare_ticket(root, app, action, target, approved_root)
    receiver = receiver_script(launcher, app, action)
    try:
        python = _python()
    except IntegrationError:
        discard(ticket)
        raise
    if receiver is not None:
        argv = [python, str(receiver), '--request', str(ticket.request_path)]
        mode = 'native_receiver'
    else:
        relay = Path(__file__).with_name('bridge_relay.py')
        argv = [python, str(relay), '--request', str(ticket.request_path), '--launcher', str(launcher)]
        mode = 'manual_relay'
    options: dict[str, Any] = {'cwd': str(launcher.parent), 'shell': False,
                               'stdin': subprocess.DEVNULL, 'stdout': subprocess.DEVNULL,
                               'stderr': subprocess.DEVNULL}
    if sys.platform == 'win32':
        options['creationflags'] = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    try:
        subprocess.Popen(argv, **options)
    except OSError as exc:
        discard(ticket)
        raise IntegrationError(f'No se pudo iniciar Apex Bridge: {exc}') from exc
    return ticket, mode


def read_request(path: Path, app: str | None = None) -> dict:
    path = Path(path).resolve(strict=True)
    if path.name != 'request.json':
        raise IntegrationError('El nombre de la solicitud Apex Bridge no es válido.')
    obj = _read_json(path)
    if (obj.get('protocol') != PROTOCOL or not isinstance(obj.get('request_id'), str)
            or obj['request_id'] != path.parent.name or not isinstance(obj.get('created_at'), int)
            or abs(time.time() - obj['created_at']) > MAX_AGE_SECONDS):
        raise IntegrationError('Solicitud Apex Bridge inválida o caducada.')
    if app is not None and obj.get('app') != app:
        raise IntegrationError('Solicitud para otra aplicación.')
    target = _allowed_target(obj.get('app'), obj.get('action'), Path(str(obj.get('target', ''))))
    root = Path(str(obj.get('approved_root', ''))).resolve(strict=True)
    if not root.is_dir() or not target.is_relative_to(root):
        raise IntegrationError('La ruta del receptor queda fuera de la carpeta autorizada.')
    return obj


def write_receipt(request_path: Path, *, status: str, message: str, verdict: str | None = None) -> Path:
    req = read_request(request_path)
    if status not in STATUSES or not isinstance(message, str):
        raise IntegrationError('Estado de respuesta no permitido.')
    if verdict is not None and (status != 'scan_finished' or req['app'] != 'thunderbolt'
                                or verdict not in VERDICTS):
        raise IntegrationError('Veredicto no admitido para esta respuesta.')
    receipt = Path(request_path).parent / 'receipt.json'
    data = {'protocol': PROTOCOL, 'request_id': req['request_id'], 'app': req['app'],
            'action': req['action'], 'status': status, 'message': message[:512],
            'updated_at': int(time.time())}
    if verdict is not None:
        data['verdict'] = verdict
    _atomic_json(receipt, data)
    return receipt


def read_receipt(ticket: BridgeTicket) -> dict | None:
    if not ticket.receipt_path.exists():
        return None
    obj = _read_json(ticket.receipt_path)
    if (obj.get('protocol') != PROTOCOL or obj.get('request_id') != ticket.id or
        obj.get('app') != ticket.app or obj.get('action') != ticket.action or
        obj.get('status') not in STATUSES or
        not isinstance(obj.get('updated_at'), int) or
        abs(obj['updated_at'] - ticket.launched_at) > MAX_AGE_SECONDS):
        raise IntegrationError('La respuesta no coincide con la solicitud enviada.')
    if obj.get('verdict') is not None and (obj['status'] != 'scan_finished' or
        ticket.app != 'thunderbolt' or obj.get('verdict') not in VERDICTS):
        raise IntegrationError('La respuesta contiene un veredicto no autorizado.')
    if not isinstance(obj.get('message'), str):
        raise IntegrationError('La respuesta no contiene mensaje.')
    return obj


def discard(ticket: BridgeTicket) -> None:
    ticket.request_path.unlink(missing_ok=True)
    ticket.receipt_path.unlink(missing_ok=True)
    try:
        ticket.request_path.parent.rmdir()
    except OSError:
        pass


def receipt_message(receipt: dict, app: str, mode: str) -> str:
    status = receipt['status']
    if mode == 'manual_relay':
        if app == 'thunderbolt':
            return 'Thunderbolt abierto. Revisión MANUAL pendiente; no existe resultado antivirus confirmado.'
        return 'Smart Files abierto y ubicación mostrada en Explorador; navegación interna no confirmada.'
    if status == 'scan_finished':
        verdict = receipt.get('verdict', 'inconclusive')
        return f'Thunderbolt informó finalización de análisis ({verdict}). Confirma el informe dentro del antivirus.'
    return f'Apex Bridge · {status}: {receipt["message"][:260]}'


def bridge_connection_state(executable: str, app: str) -> str:
    try:
        launcher = executable_path(executable)
    except IntegrationError:
        return 'No configurado · Selecciona el programa.'
    if any(receiver_script(launcher, app, action) for action in ACTIONS[app]):
        return 'Apex Bridge v2 · Receptor nativo declarado (pendiente de verificación en Windows)'
    return 'Apex Bridge v2 · Relay manual disponible · No confirma análisis automático'
