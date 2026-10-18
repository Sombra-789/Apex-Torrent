"""Apex Torrent 1.3.7: present real libtorrent peer data without Python repr noise.

This module performs no network actions and is usable without Qt/libtorrent.
"""
from __future__ import annotations
import ast
import ipaddress
import re


def human_client(value: object) -> str:
    if value is None:
        return "No identificado"
    if isinstance(value, (bytes, bytearray, memoryview)):
        try:
            value = bytes(value).decode("utf-8", "replace")
        except Exception:
            return "No identificado"
    text = str(value).strip().strip("\x00")
    return text if text and text not in ("b''", 'b""', "None", "—") else "No identificado"


def human_endpoint(value: object) -> str:
    if not value:
        return "No disponible"
    if isinstance(value, tuple) and len(value) >= 2:
        addr, port = value[0], value[1]
        if not isinstance(addr, str) or not isinstance(port, int) or not 0 <= port <= 65535:
            return "No disponible"
        try:
            ipaddress.ip_address(addr)
        except ValueError:
            return "No disponible"
        return f"[{addr}]:{port}" if ':' in addr else f"{addr}:{port}"
    text = str(value).strip()
    # libtorrent Python bindings sometimes stringify tcp::endpoint as a tuple.
    if text.startswith('(') and text.endswith(')'):
        try:
            result = ast.literal_eval(text)
        except (ValueError, SyntaxError):
            return "No disponible"
        return human_endpoint(result)
    return text if text and len(text) < 256 else "No disponible"


def peer_availability(progress: object) -> str:
    try:
        number = float(progress)
    except (TypeError, ValueError):
        return "No conocida"
    if number <= 0:
        return "Sin piezas anunciadas"
    if number >= 0.99999:
        return "Fuente completa (reportada)"
    return f"Parcial · {number * 100:.1f}%"


def download_activity(row: dict) -> tuple[str, str]:
    """Separates payload movement from bandwidth; never assumes zero seeds == dead torrent."""
    if row.get("progress", 0) >= 1.0:
        return "Completado", "Archivo completo; puede seguir compartiéndose."
    raw = max(0, int(row.get("down", 0) or 0))
    useful = row.get("payload_down")
    connected = max(0, int(row.get("peers", 0) or 0))
    if useful is not None and int(useful) > 0:
        return "Recibiendo piezas", "Hay tráfico de contenido útil, no solo protocolo."
    if useful == 0 and raw > 0:
        return "Solo protocolo", "Se intercambian bytes de control, sin piezas útiles medidas."
    if connected == 0:
        return "Buscando fuentes", "No hay pares conectados; no implica que el torrent esté abandonado."
    return "Sin piezas nuevas", "Hay pares conectados, pero no se registran piezas nuevas por ahora."


def displayed_payload_rate(row: dict) -> int:
    """Use actual payload rate when libtorrent provides it; preserve legacy fallback otherwise."""
    rate = row.get("payload_down", None)
    return max(0, int(rate if rate is not None else row.get("down", 0) or 0))
