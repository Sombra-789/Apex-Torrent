"""Apex Bridge v2 SDK para incorporar en Thunderbolt y Smart Files.

El receptor DEBE proporcionar una función real de su aplicación. Sin ella
este SDK devuelve 'unsupported' y NUNCA un veredicto inventado.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable
from bridge_ipc import IntegrationError, read_request, write_receipt


def thunderbolt_handle(request_path: Path,
                       scan_callback: Callable[[Path], str] | None = None) -> str:
    """scan_callback real devuelve 'clean', 'threat' o 'inconclusive'.

    Debe bloquear hasta que TERMINE el análisis real del motor y devolver
    únicamente su resultado. Prohibido usar solo Popen(...) como escaneo.
    """
    req = read_request(request_path, 'thunderbolt')
    if req['action'] != 'scan_file':
        raise IntegrationError('Acción no compatible con Thunderbolt.')
    if scan_callback is None:
        write_receipt(request_path, status='unsupported',
                      message='Esta versión de Thunderbolt todavía no implementa el análisis por Apex Bridge.')
        return 'unsupported'
    file = Path(req['target'])
    write_receipt(request_path, status='scanning',
                  message='Thunderbolt ha iniciado el análisis del archivo elegido.')
    try:
        verdict = scan_callback(file)
        if verdict not in ('clean', 'threat', 'inconclusive'):
            raise ValueError('El análisis no devolvió un veredicto válido.')
        write_receipt(request_path, status='scan_finished',
                      message='El motor Thunderbolt finalizó el análisis.', verdict=verdict)
        return 'scan_finished'
    except Exception as exc:
        write_receipt(request_path, status='scan_failed',
                      message=f'El motor Thunderbolt no completó el análisis: {type(exc).__name__}')
        return 'scan_failed'


def smart_files_handle(request_path: Path,
                       open_folder_callback: Callable[[Path], bool] | None = None) -> str:
    """El callback debe abrir la carpeta DENTRO de Smart Files, no en Explorer."""
    req = read_request(request_path, 'smart_files')
    if req['action'] != 'open_folder':
        raise IntegrationError('Acción no compatible con Smart Files.')
    if open_folder_callback is None:
        write_receipt(request_path, status='unsupported',
                      message='Esta versión de Smart Files todavía no implementa navegación por Apex Bridge.')
        return 'unsupported'
    folder = Path(req['target'])
    try:
        if open_folder_callback(folder) is not True:
            raise RuntimeError('Smart Files no confirmó la navegación interna.')
        write_receipt(request_path, status='folder_opened',
                      message='Smart Files confirmó la apertura interna de la carpeta.')
        return 'folder_opened'
    except Exception as exc:
        write_receipt(request_path, status='failed',
                      message=f'Smart Files no abrió la carpeta: {type(exc).__name__}')
        return 'failed'
