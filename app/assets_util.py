"""Resolución de recursos válida para Python normal y PyInstaller --onedir."""
from pathlib import Path
import sys


def asset_path(filename: str) -> Path:
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle is not None:
        return Path(bundle) / "assets" / filename
    return Path(__file__).resolve().parent / "assets" / filename
