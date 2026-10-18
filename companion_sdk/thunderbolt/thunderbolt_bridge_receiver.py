"""Plantilla para incorporar DENTRO del código de Thunderbolt.

PENDIENTE: sustituir None por una callback del motor antivirus REAL.
No declares un manifiesto Apex Bridge hasta implementar y probar la callback.
"""
import argparse
import sys
from pathlib import Path
# Al integrar, coloca bridge_ipc.py, bridge_sdk.py e integrations.py junto al receptor.
from bridge_sdk import thunderbolt_handle


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--request', type=Path, required=True)
    args = parser.parse_args()
    # TODO: importar la función REAL de Thunderbolt; debe esperar resultado
    actual_scan_callback = None
    return 0 if thunderbolt_handle(args.request, actual_scan_callback) == 'scan_finished' else 1


if __name__ == '__main__':
    sys.exit(main())
