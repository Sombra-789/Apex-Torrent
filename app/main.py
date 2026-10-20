"""Inicio de la aplicación Apex Torrent para Windows."""
from __future__ import annotations
import logging
import sys
import traceback
import json
import os
from pathlib import Path
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QIcon
from PySide6.QtCore import QLockFile, QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from state import DATA_DIR, Store
from engine import TorrentEngine
from ui import MainWindow
from assets_util import asset_path


def main():
    # Windows agrupa las ventanas en la barra de tareas por AppUserModelID.
    # Debe establecerse antes de inicializar QApplication.
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "ApexSoftware.ApexTorrent.Alpha")
        except (AttributeError, OSError) as exc:
            logging.warning("No se pudo establecer el identificador de tarea: %s", exc)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=str(DATA_DIR / "apex_torrent.log"), level=logging.ERROR,
                        format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8")
    app = QApplication(sys.argv)
    app.setApplicationName("Apex Torrent Alpha")
    app.setQuitOnLastWindowClosed(False)  # cierre controlado con/sin bandeja
    app.setOrganizationName("Apex Visual Studio")
    app.setStyle("Fusion")
    single_instance = QLockFile(str(DATA_DIR / "apex_torrent.lock"))
    single_instance.setStaleLockTime(10000)
    server_name = "ApexSoftware.ApexTorrentAlpha.LocalOpen.v1"
    external = next((v for v in sys.argv[1:] if v.lower().startswith("magnet:?") or v.lower().endswith(".torrent")), None)
    if not single_instance.tryLock(100):
        if external:
            other = QLocalSocket()
            other.connectToServer(server_name)
            if other.waitForConnected(1200):
                other.write(json.dumps({"open": external}, ensure_ascii=False).encode("utf-8"))
                other.flush()
                if other.waitForBytesWritten(1200) or other.bytesToWrite() == 0:
                    other.disconnectFromServer()
                    return 0
        QMessageBox.warning(None, "Apex Torrent", "Apex Torrent ya está abierto. Ábrelo desde la bandeja del sistema.")
        return 2
    icon = asset_path("apex-torrent.ico")
    if icon.is_file():
        app.setWindowIcon(QIcon(str(icon)))

    def handle_exception(exc_type, exc, tb):
        message = "".join(traceback.format_exception(exc_type, exc, tb))
        logging.error(message)
        QMessageBox.critical(None, "Apex Torrent — error", f"Ocurrió un error inesperado.\n\n{exc}\n\nDetalles: {DATA_DIR / 'apex_torrent.log'}")

    sys.excepthook = handle_exception
    try:
        engine = TorrentEngine(Store(DATA_DIR))
        window = MainWindow(engine)
        window.show()
        # Qt usa un canal local del usuario; los datos siempre se validan en el motor.
        local_server = QLocalServer(window)
        QLocalServer.removeServer(server_name)  # ya poseemos el QLockFile
        if local_server.listen(server_name):
            def process_pending():
                while local_server.hasPendingConnections():
                    sock = local_server.nextPendingConnection()
                    sock.waitForReadyRead(800)
                    try:
                        payload = bytes(sock.readAll())
                        if len(payload) <= 32768:
                            obj = json.loads(payload.decode("utf-8"))
                            if isinstance(obj, dict) and isinstance(obj.get("open"), str):
                                window.open_external(obj["open"])
                    except (ValueError, UnicodeError, TypeError) as exc:
                        logging.warning("IPC local rechazado: %s", exc)
                    finally:
                        sock.disconnectFromServer()
                        sock.deleteLater()
            local_server.newConnection.connect(process_pending)
        else:
            logging.warning("No se pudo iniciar canal local para asociaciones de Windows: %s", local_server.errorString())
        if external:
            QTimer.singleShot(250, lambda: window.open_external(external))
    except Exception as exc:
        logging.exception("Error inicializando aplicación")
        QMessageBox.critical(None, "No se pudo iniciar Apex Torrent", f"{exc}\n\nConsulta apex_torrent.log")
        return 1
    try:
        return app.exec()
    finally:
        single_instance.unlock()


if __name__ == "__main__":
    sys.exit(main())
