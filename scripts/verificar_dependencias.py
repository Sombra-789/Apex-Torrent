"""Autocomprobacion: compatible con Windows PowerShell 5.1 (sin python -c)."""
from __future__ import annotations
import sys
import struct

try:
    import libtorrent as lt
    import PySide6
    from PySide6.QtCore import QLibraryInfo
    from PySide6.QtWidgets import QApplication
except Exception as exc:
    print(f"ERROR comprobando dependencias: {type(exc).__name__}: {exc}", file=sys.stderr)
    raise SystemExit(1)

print(f"Python: {sys.version.split()[0]} ({struct.calcsize('P') * 8} bits)")
print(f"libtorrent: {lt.version}")
print(f"PySide6: {PySide6.__version__}")
print("DEPENDENCIAS CORRECTAS")
