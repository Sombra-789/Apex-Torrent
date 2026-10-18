"""Plantilla para incorporar DENTRO del código de Apex Smart Files.

PENDIENTE: sustituir None por una callback de navegación en el explorador REAL.
No declares el manifiesto hasta que confirme la navegación interna.
"""
import argparse
import sys
from pathlib import Path
from bridge_sdk import smart_files_handle


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--request', type=Path, required=True)
    args = parser.parse_args()
    # TODO: invocar el método REAL del gestor para navegar al directorio
    actual_open_folder_callback = None
    return 0 if smart_files_handle(args.request, actual_open_folder_callback) == 'folder_opened' else 1


if __name__ == '__main__':
    sys.exit(main())
