"""Apex Torrent 1.3.8 Ultimate — Final Polish & Source Recovery."""
from __future__ import annotations
import os
import logging
import time
import shutil
import sys
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QRect, QSize, QSignalBlocker, QObject, Signal, Slot, QRunnable, QThreadPool, QEvent
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QBrush, QDesktopServices, QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFrame,
    QLabel, QPushButton, QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QStyledItemDelegate, QStyleOptionViewItem, QSplitter, QTabWidget, QFileDialog,
    QDialog, QDialogButtonBox, QMessageBox, QAbstractItemView, QMenu, QStackedWidget,
    QScrollArea, QSpinBox, QCheckBox, QFormLayout, QGridLayout, QComboBox, QPlainTextEdit,
    QSizePolicy, QSystemTrayIcon,
)
from PySide6.QtCore import QUrl
from state import VERSION, DATA_DIR, readable_size, readable_speed, readable_eta
from peer_intelligence import download_activity, displayed_payload_rate
from swarm_radar import summarize_swarm, radar_text
from engine import TorrentEngine, EngineError
from widgets import TransferGraph
from performance import PROFILES, network_insight
from cyber_theme import STYLE, COLORS, THEMES, theme_for, accent_color
from assets_util import asset_path
from ultimate import tracker_summary, inspect_names, disk_estimate, safe_download_path, file_sha256
from monitor import ProcessSampler, PerformanceJournal
from smart_engine import effective_upload_limit_kib, smart_upload_report, tracker_diagnosis, swarm_hint
from scheduler import schedule_caption
from integrations import (COMPANIONS, IntegrationError, integration_state, start_companion,
                          executable_path, selected_complete_file, selected_folder, capability)
from bridge_ipc import (send_request, read_receipt, discard, receipt_message,
                        receiver_script, MAX_AGE_SECONDS, bridge_connection_state)



class ProgressDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        progress = index.data(Qt.ItemDataRole.UserRole)
        if progress is None:
            super().paint(painter, option, index)
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect.adjusted(9, 14, -9, -14)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#181818"))
        painter.drawRoundedRect(rect, 5, 5)
        filled = QRect(rect.x(), rect.y(), max(0, round(rect.width() * float(progress))), rect.height())
        painter.setBrush(QColor((QApplication.instance().property("apex_plot_accent") or "#35aaff") if progress < 1 else "#3ef0b1"))
        painter.drawRoundedRect(filled, 5, 5)
        painter.setPen(QColor("#f1fbff"))
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{float(progress)*100:.1f}%")
        painter.restore()


class AddMagnetDialog(QDialog):
    def __init__(self, folder: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Agregar enlace magnet")
        self.resize(600, 240)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(12)
        head = QLabel("NUEVA DESCARGA · MAGNET")
        head.setStyleSheet("font-weight:700;color:#52e9d0;font-size:15px;")
        lay.addWidget(head)
        lay.addWidget(QLabel("Pega un enlace magnet de contenido que puedes descargar y compartir."))
        self.uri = QLineEdit()
        self.uri.setPlaceholderText("magnet:?xt=urn:btih:...")
        lay.addWidget(self.uri)
        lay.addWidget(QLabel("Guardar archivos en:"))
        self.folder = QLineEdit(folder)
        browse = QPushButton("Examinar")
        browse.clicked.connect(self.choose_folder)
        row = QHBoxLayout()
        row.addWidget(self.folder, 1)
        row.addWidget(browse)
        lay.addLayout(row)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        box.button(QDialogButtonBox.StandardButton.Ok).setText("Agregar descarga")
        box.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)
        self.uri.setFocus()

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Carpeta de descarga", self.folder.text())
        if folder:
            self.folder.setText(folder)


class StatCard(QFrame):
    """Indicadores compactos y consistentes para distintos anchos de ventana."""
    def __init__(self, title: str, initial: str, badge: str):
        super().__init__()
        self.setObjectName("stat")
        self.setMinimumHeight(82)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(13, 8, 13, 8)
        lay.setSpacing(5)
        row = QHBoxLayout()
        title_widget = QLabel(title.upper())
        title_widget.setObjectName("statLabel")
        title_widget.setMinimumWidth(0)
        row.addWidget(title_widget, 1)
        logo = QLabel(badge)
        logo.setObjectName("statGlyph")
        row.addWidget(logo)
        lay.addLayout(row)
        self.value = QLabel(initial)
        self.value.setObjectName("statValue")
        self.value.setMinimumWidth(0)
        lay.addWidget(self.value)


class _HashSignals(QObject):
    finished = Signal(str, str)


class _HashJob(QRunnable):
    """Hash de archivo elegido por el usuario sin bloquear la interfaz."""
    def __init__(self, path):
        super().__init__()
        self.path = path
        self.signals = _HashSignals()

    def run(self):
        try:
            result = file_sha256(self.path)
        except Exception as exc:
            result = f"ERROR: {exc}"
        self.signals.finished.emit(str(self.path), result)


class ElidedDetailValue(QLabel):
    """Compact value label with non-destructive display and full-text tooltip.

    A long local path/hash stays accessible in its entirety via tooltip and
    selection, while the grid retains a stable height on compact displays.
    """
    def __init__(self, text="—", parent=None):
        super().__init__(parent)
        self._original_text = ""
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(21)
        self.setWordWrap(False)
        self.setFullText(text)

    def setFullText(self, value):
        self._original_text = str(value)
        self.setToolTip(self._original_text)
        self._elide()

    def _elide(self):
        if not self._original_text:
            self.setText("—")
            return
        self.setText(self.fontMetrics().elidedText(
            self._original_text, Qt.TextElideMode.ElideMiddle, max(20, self.width()-6)))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide()


class MainWindow(QMainWindow):
    def __init__(self, engine: TorrentEngine):
        super().__init__()
        self.engine = engine
        self.setWindowTitle(f"Apex Torrent {VERSION} — Ultimate Edition (Final Polish)")
        self.resize(1450, 865)
        self.setMinimumSize(980, 630)
        self.setStyleSheet(theme_for(self.engine.settings.get("accent_theme", "Azul")))
        QApplication.instance().setProperty("apex_accent", accent_color(self.engine.settings.get("accent_theme", "Azul")))
        QApplication.instance().setProperty("apex_plot_accent", "#d7d7d7" if self.engine.settings.get("accent_theme") == "Negro total" else accent_color(self.engine.settings.get("accent_theme", "Azul")))
        icon = asset_path("apex-torrent.ico")
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))
        self.active_filter = "Todos"
        self.cached_rows: dict[str, dict] = {}
        self._tick_count = 0
        self._files_id = None
        self._last_detail_id = None
        self._current_nav = "Biblioteca"
        self._selected_graph_id = None
        self._exit_requested = False
        self._tray_tip_shown = False
        self._seen_completed = None
        self._last_table_signature = None
        self._latest_trackers = []
        self._layout_save_timer = QTimer(self)
        self._layout_save_timer.setSingleShot(True)
        self._layout_save_timer.timeout.connect(self._save_library_layout)
        self._last_diagnosis_signature = None
        self._last_schedule_tick = 0.0
        self._problem_notifications: dict[tuple[str, str], float] = {}
        self._bridge_pending = {}
        self._hash_workers = []
        self._hash_current = None
        raw_integrations = self.engine.store.load_json("integrations.json", {})
        if not isinstance(raw_integrations, dict):
            raw_integrations = {}
        self.integration_paths = {
            key: str(raw_integrations.get(key, ""))[:4096]
            for key in COMPANIONS
        }
        # Telemetría de proceso y velocidad: solo datos numéricos locales.
        # Si la base de datos no está disponible, el motor P2P continúa normalmente.
        self._sampler = ProcessSampler()
        self._history_error = ""
        try:
            self._journal = PerformanceJournal(self.engine.store.base)
        except Exception as exc:
            self._journal = None
            self._history_error = f"Historial no disponible: {type(exc).__name__}"
            logging.warning("Historial de rendimiento deshabilitado: %s", exc)
        self._next_monitor_sample = 0.0
        self._build()
        self._setup_tray()
        self._add_shortcuts()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(1500)
        self.bridge_timer = QTimer(self)
        self.bridge_timer.timeout.connect(self._poll_bridge)
        self.bridge_timer.start(2000)
        self.resume_timer = QTimer(self)
        self.resume_timer.timeout.connect(engine.save_all_resume)
        self.resume_timer.start(90000)
        self.refresh()
        if engine.load_errors:
            QTimer.singleShot(300, lambda: self.error("Algunos torrents no pudieron recuperarse:\n" + "\n".join(engine.load_errors[:5])))

    def _build(self):
        root = QWidget()
        root.setObjectName("appRoot")
        self.setCentralWidget(root)
        horizontal = QHBoxLayout(root)
        horizontal.setContentsMargins(0, 0, 0, 0)
        horizontal.setSpacing(0)
        # La cabecera y el pie quedan fijos. SOLO la navegación puede
        # desplazarse: ningún botón ni el estado del motor se recortan.
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(258)
        left = QVBoxLayout(sidebar)
        left.setContentsMargins(14, 18, 14, 14)
        left.setSpacing(9)
        brand_plate = QFrame()
        brand_plate.setObjectName("brandPlate")
        plate_layout = QVBoxLayout(brand_plate)
        plate_layout.setContentsMargins(8, 9, 8, 12)
        plate_layout.setSpacing(4)
        logo = QLabel()
        logo.setObjectName("logoImage")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setFixedHeight(76)
        mark_path = asset_path("apex-torrent-mark.png")
        from PySide6.QtGui import QPixmap
        pixmap = QPixmap(str(mark_path))
        if not pixmap.isNull():
            logo.setPixmap(pixmap.scaled(76, 76, Qt.AspectRatioMode.KeepAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation))
        plate_layout.addWidget(logo)
        brand = QLabel("APEX // TORRENT")
        brand.setObjectName("brand")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        plate_layout.addWidget(brand)
        edition = QLabel(f"ULTIMATE EDITION  //  {VERSION}")
        edition.setObjectName("edition")
        edition.setAlignment(Qt.AlignmentFlag.AlignCenter)
        plate_layout.addWidget(edition)
        left.addWidget(brand_plate)

        nav_scroll = QScrollArea()
        nav_scroll.setObjectName("navScroll")
        nav_scroll.setWidgetResizable(True)
        nav_scroll.setFrameShape(QFrame.Shape.NoFrame)
        nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        nav_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        nav_body = QWidget()
        nav_body.setObjectName("navBody")
        nav = QVBoxLayout(nav_body)
        nav.setContentsMargins(0, 5, 4, 5)
        nav.setSpacing(4)
        nav.addWidget(self._sidebar_label("01  /  BIBLIOTECA"))
        self.nav_buttons = {}
        for label, glyph in (("Biblioteca", "▦"), ("Activos", "◉"),
                             ("Completados", "✓"), ("Pausados", "Ⅱ")):
            self._nav_button(nav, label, glyph)
        nav.addSpacing(9)
        nav.addWidget(self._sidebar_label("02  /  CONTROL"))
        for label, glyph in (("Rendimiento", "⌁"), ("Red / Diagnóstico", "◎"),
                             ("Configuración", "⚙"), ("Ecosistema Apex", "⬡"), ("Acerca de", "ⓘ")):
            self._nav_button(nav, label, glyph)
        nav.addStretch(1)
        nav_scroll.setWidget(nav_body)
        left.addWidget(nav_scroll, 1)

        status_box = QFrame()
        status_box.setObjectName("systemStatus")
        small = QVBoxLayout(status_box)
        small.setContentsMargins(11, 9, 11, 10)
        small.setSpacing(3)
        self.connection_text = QLabel("●  MOTOR BITTORRENT")
        self.connection_text.setObjectName("connectionTitle")
        small.addWidget(self.connection_text)
        self.connection_sub = QLabel("EN LÍNEA  /  DHT · PEX · uTP")
        self.connection_sub.setObjectName("connectionSub")
        small.addWidget(self.connection_sub)
        left.addWidget(status_box)
        notice = QLabel("APEX SOFTWARE  //  WINDOWS")
        notice.setObjectName("copyright")
        notice.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left.addWidget(notice)
        horizontal.addWidget(sidebar)
        self.pages = QStackedWidget()
        horizontal.addWidget(self.pages, 1)
        self.pages.addWidget(self._downloads_page())       # 0
        self.pages.addWidget(self._performance_page())     # 1
        self.pages.addWidget(self._network_page())         # 2
        self.pages.addWidget(self._settings_page())        # 3
        self.pages.addWidget(self._about_page())           # 4
        self.pages.addWidget(self._integrations_page())    # 5
        self.change_page(0)

    @staticmethod
    def _sidebar_label(text: str):
        label = QLabel(text)
        label.setObjectName("navSection")
        return label

    def _nav_button(self, layout, label: str, glyph: str):
        button = QPushButton(f"{glyph}    {label}")
        button.setMinimumHeight(39)
        button.setToolTip(label)
        button.setObjectName("nav")
        button.setCheckable(True)
        button.clicked.connect(lambda _checked=False, name=label: self.navigate(name))
        layout.addWidget(button)
        self.nav_buttons[label] = button

    def navigate(self, name: str):
        self._current_nav = name
        if name in ("Biblioteca", "Activos", "Completados", "Pausados"):
            self.pages.setCurrentIndex(0)
            chosen = {"Biblioteca": "Todos", "Activos": "Descargando",
                      "Completados": "Completados", "Pausados": "Pausados"}[name]
            self.change_filter(chosen)
        else:
            index = {"Rendimiento": 1, "Red / Diagnóstico": 2,
                     "Configuración": 3, "Acerca de": 4, "Ecosistema Apex": 5}[name]
            self.pages.setCurrentIndex(index)
            if name == "Red / Diagnóstico":
                self.update_network_page()
        for label, btn in self.nav_buttons.items():
            btn.setChecked(label == name)

    def change_page(self, idx: int):
        name = {0:"Biblioteca",1:"Rendimiento",2:"Red / Diagnóstico",3:"Configuración",4:"Acerca de",5:"Ecosistema Apex"}[idx]
        self.navigate(name)

    def _downloads_page(self):
        page = QWidget()
        page.setObjectName("page")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(18, 13, 18, 10)
        lay.setSpacing(8)
        heading = QHBoxLayout()
        textblock = QVBoxLayout()
        title = QLabel("Centro de transferencias")
        title.setObjectName("headerTitle")
        textblock.addWidget(title)
        sub = QLabel("ULTIMATE EDITION  /  CONTROL · SEGURIDAD · DIAGNÓSTICOS")
        sub.setObjectName("muted")
        textblock.addWidget(sub)
        heading.addLayout(textblock)
        heading.addStretch()
        btn_torrent = QPushButton("＋  Abrir .torrent")
        btn_torrent.clicked.connect(self.add_file)
        heading.addWidget(btn_torrent)
        btn_magnet = QPushButton("↗  Nuevo magnet")
        btn_magnet.setObjectName("primary")
        btn_magnet.clicked.connect(self.add_magnet)
        heading.addWidget(btn_magnet)
        lay.addLayout(heading)
        stats = QHBoxLayout()
        stats.setSpacing(9)
        self.count_stat = StatCard("Torrents", "0", "◈")
        self.down_stat = StatCard("Descarga actual", "0 B/s", "↓")
        self.up_stat = StatCard("Subida actual", "0 B/s", "↑")
        self.finish_stat = StatCard("Completados", "0", "✓")
        self.peers_stat = StatCard("Pares en línea", "0", "◎")
        for card in (self.count_stat, self.down_stat, self.up_stat, self.peers_stat, self.finish_stat):
            stats.addWidget(card, 1)
        lay.addLayout(stats)
        actionbar = QHBoxLayout()
        self.filters = []
        for text in ("Todos", "Descargando", "Completados", "Pausados"):
            button = QPushButton(text)
            button.setObjectName("filter")
            button.setCheckable(True)
            button.setChecked(text == "Todos")
            button.clicked.connect(lambda _checked=False, value=text: self.change_filter(value))
            actionbar.addWidget(button)
            self.filters.append(button)
        actionbar.addStretch()
        self.search = QLineEdit()
        self.search.setPlaceholderText("⌕  Buscar en la biblioteca")
        self.search.setMaximumWidth(285)
        self.search.textChanged.connect(self.refresh_table)
        actionbar.addWidget(self.search)
        lay.addLayout(actionbar)
        operations = QHBoxLayout()
        operations.setSpacing(8)
        self.resume_button = QPushButton("▶  Reanudar")
        self.resume_button.clicked.connect(self.resume_selected)
        operations.addWidget(self.resume_button)
        self.pause_button = QPushButton("Ⅱ  Pausar")
        self.pause_button.clicked.connect(self.pause_selected)
        operations.addWidget(self.pause_button)
        folder = QPushButton("▣  Abrir carpeta")
        folder.clicked.connect(self.open_folder)
        operations.addWidget(folder)
        # Menú de utilidades: evita el desbordamiento horizontal de 1.1.0
        tools = QPushButton("⋯  Herramientas  ▾")
        tools.setObjectName("tools")
        tools_menu = QMenu(tools)
        tools_menu.addAction("⟳  Verificar archivos", self.recheck_selected)
        tools_menu.addAction("↻  Reanunciar trackers", self.reannounce_selected)
        tools_menu.addAction("✦  Intentar recuperar fuentes", self.recover_selected)
        tools_menu.addAction("?  ¿Por qué no descarga?", self.show_torrent_diagnosis)
        tools_menu.addAction("▤  Copiar diagnóstico", self.copy_network_diagnostic)
        tools_menu.addAction("⇅  Límites del torrent", self.change_torrent_limits)
        tools_menu.addSeparator()
        tools_menu.addAction("🛡  Revisar con Thunderbolt", self.review_with_thunderbolt)
        tools_menu.addAction("▣  Abrir en Smart Files", self.open_with_smart_files)
        tools.setMenu(tools_menu)
        operations.addWidget(tools)
        operations.addStretch(1)
        remove = QPushButton("✕  Quitar")
        remove.setObjectName("danger")
        remove.clicked.connect(self.remove_selected)
        operations.addWidget(remove)
        lay.addLayout(operations)
        self.error_box = QFrame()
        self.error_box.setObjectName("errorBanner")
        error_layout = QHBoxLayout(self.error_box)
        error_layout.setContentsMargins(14, 8, 12, 8)
        error_layout.setSpacing(8)
        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        error_layout.addWidget(self.error_label, 1)
        error_view = QPushButton("Ver error")
        error_view.clicked.connect(self.show_first_error)
        error_layout.addWidget(error_view)
        error_copy = QPushButton("Copiar diagnóstico")
        error_copy.clicked.connect(self.copy_diagnostic)
        error_layout.addWidget(error_copy)
        self.error_box.setVisible(False)
        lay.addWidget(self.error_box)
        self.insight_box = QFrame()
        self.insight_box.setObjectName("insight")
        ins_lay = QHBoxLayout(self.insight_box)
        ins_lay.setContentsMargins(16, 8, 16, 8)
        self.insight_text = QLabel("Selecciona un torrent para consultar su disponibilidad.")
        self.insight_text.setObjectName("insightText")
        self.insight_text.setWordWrap(False)
        self.insight_text.setMinimumWidth(0)
        self.insight_box.setMaximumHeight(43)
        ins_lay.addWidget(self.insight_text, 1)
        lay.addWidget(self.insight_box)
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(10)
        splitter.setOpaqueResize(False)
        self.main_splitter = splitter
        self.table = QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels(["NOMBRE", "TAMAÑO", "PROGRESO", "ESTADO", "BAJADA", "SUBIDA", "PARES", "SEMILLAS", "ETA", "RATIO"])
        self.table.setAlternatingRowColors(True)
        self.table.setMinimumHeight(110)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(45)
        self.table.setItemDelegateForColumn(2, ProgressDelegate(self.table))
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 250)
        self.table.horizontalHeader().setMinimumSectionSize(42)
        for col, width in enumerate([0, 80, 105, 122, 92, 92, 51, 62, 70, 52]):
            if col:
                self.table.setColumnWidth(col, width)
        self.table.viewport().installEventFilter(self)
        self.table.itemSelectionChanged.connect(self.update_details)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        self.table.itemDoubleClicked.connect(lambda _item: self.open_folder())
        self.library_stack = QStackedWidget()
        self.library_stack.addWidget(self.table)
        empty_page = QFrame()
        empty_page.setObjectName("emptyPanel")
        empty_lay = QVBoxLayout(empty_page)
        empty_lay.setContentsMargins(25, 20, 25, 20)
        empty_lay.addStretch()
        self.empty_title = QLabel("No hay descargas en esta vista")
        self.empty_title.setObjectName("emptyTitle")
        self.empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_lay.addWidget(self.empty_title)
        self.empty_hint = QLabel("Puedes cambiar el filtro o agregar un archivo .torrent.")
        self.empty_hint.setObjectName("muted")
        self.empty_hint.setWordWrap(True)
        self.empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_lay.addWidget(self.empty_hint)
        empty_actions = QHBoxLayout()
        empty_actions.addStretch()
        empty_add = QPushButton("＋  Abrir .torrent")
        empty_add.setObjectName("primary")
        empty_add.clicked.connect(self.add_file)
        empty_actions.addWidget(empty_add)
        empty_mag = QPushButton("↗  Magnet")
        empty_mag.clicked.connect(self.add_magnet)
        empty_actions.addWidget(empty_mag)
        empty_actions.addStretch()
        empty_lay.addLayout(empty_actions)
        empty_lay.addStretch()
        self.library_stack.addWidget(empty_page)
        splitter.addWidget(self.library_stack)
        detail = QFrame()
        detail.setObjectName("detail")
        dlay = QVBoxLayout(detail)
        dlay.setContentsMargins(9, 4, 9, 5)
        detail.setMinimumHeight(132)
        self._detail_panel = detail
        self.tabs = QTabWidget()
        self.tabs.setUsesScrollButtons(True)
        self.tabs.setMinimumHeight(114)
        self.tabs.setDocumentMode(True)
        # The scrollable overview fixes the 1.3.7 clipping: six rows of
        # labels must never be squeezed onto three overlapping baselines.
        overview = QWidget()
        overview.setObjectName("tabContents")
        ovl = QGridLayout(overview)
        ovl.setContentsMargins(16, 13, 16, 16)
        ovl.setHorizontalSpacing(25)
        ovl.setVerticalSpacing(13)
        ovl.setColumnStretch(0, 1)
        ovl.setColumnStretch(1, 1)
        self.details_labels = {}
        labels = [("Estado", 0, 0), ("Guardado en", 0, 1),
                  ("Completado", 1, 0), ("Descargado", 1, 1),
                  ("Pares / Semillas", 2, 0), ("Info hash", 2, 1)]
        for name, r, c in labels:
            cell = QWidget()
            cell.setObjectName("detailCell")
            cell_layout = QVBoxLayout(cell)
            cell_layout.setContentsMargins(3, 4, 3, 5)
            cell_layout.setSpacing(4)
            caption = QLabel(name.upper())
            caption.setObjectName("statLabel")
            caption.setMinimumHeight(16)
            value = ElidedDetailValue("Selecciona un torrent")
            value.setObjectName("detailValue")
            cell_layout.addWidget(caption)
            cell_layout.addWidget(value)
            cell.setMinimumHeight(53)
            ovl.addWidget(cell, r, c)
            self.details_labels[name] = value
        overview.setMinimumHeight(205)
        overview_scroll = QScrollArea()
        overview_scroll.setObjectName("detailScroll")
        overview_scroll.setWidgetResizable(True)
        overview_scroll.setFrameShape(QFrame.Shape.NoFrame)
        overview_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        overview_scroll.setWidget(overview)
        self.tabs.addTab(overview_scroll, "Detalles")
        files_tab = QWidget()
        files_tab.setObjectName("tabContents")
        flay = QVBoxLayout(files_tab)
        flay.setContentsMargins(0, 8, 0, 0)
        file_toolbar = QHBoxLayout()
        self.file_selected_hint = QLabel("Selecciona archivos para cambiar su prioridad.")
        self.file_selected_hint.setObjectName("muted")
        file_toolbar.addWidget(self.file_selected_hint, 1)
        file_tools = QPushButton("Prioridad de archivos ▾")
        file_tools.setObjectName("tools")
        file_menu = QMenu(file_tools)
        file_menu.addAction("Todos · Normal", lambda: self._set_file_priorities_bulk(4, all_files=True))
        file_menu.addAction("Todos · No descargar", lambda: self._set_file_priorities_bulk(0, all_files=True))
        file_menu.addSeparator()
        file_menu.addAction("Seleccionados · Alta", lambda: self._set_file_priorities_bulk(7))
        file_menu.addAction("Seleccionados · Normal", lambda: self._set_file_priorities_bulk(4))
        file_menu.addAction("Seleccionados · Baja", lambda: self._set_file_priorities_bulk(1))
        file_menu.addAction("Seleccionados · No descargar", lambda: self._set_file_priorities_bulk(0))
        file_tools.setMenu(file_menu)
        file_toolbar.addWidget(file_tools)
        flay.addLayout(file_toolbar)
        self.files_table = QTableWidget(0, 4)
        self.files_table.setHorizontalHeaderLabels(["ARCHIVO (MARCAR PARA DESCARGAR)", "TAMAÑO", "DESCARGADO", "PRIORIDAD"])
        self.files_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.files_table.setColumnWidth(1, 130)
        self.files_table.setColumnWidth(2, 115)
        self.files_table.setColumnWidth(3, 100)
        self.files_table.verticalHeader().setVisible(False)
        self.files_table.setAlternatingRowColors(True)
        self.files_table.itemChanged.connect(self.change_file_priority)
        flay.addWidget(self.files_table)
        self.tabs.addTab(files_tab, "Archivos")
        trackers_tab = QWidget()
        trackers_tab.setObjectName("tabContents")
        trlay = QVBoxLayout(trackers_tab)
        self.tracker_summary_label = QLabel("Sin respuestas registradas todavía")
        self.tracker_summary_label.setObjectName("statLabel")
        controls_trackers = QHBoxLayout()
        controls_trackers.addWidget(self.tracker_summary_label, 1)
        controls_trackers.addWidget(QLabel("Mostrar:"))
        self.tracker_filter = QComboBox()
        self.tracker_filter.setMinimumWidth(120)
        self.tracker_filter.addItems(["Todos", "Respondieron", "Anunciando", "Con error"])
        self.tracker_filter.currentTextChanged.connect(self._render_trackers)
        controls_trackers.addWidget(self.tracker_filter)
        trlay.addLayout(controls_trackers)
        self.trackers_table = QTableWidget(0, 2)
        self.trackers_table.setHorizontalHeaderLabels(["RASTREADOR", "ESTADO / ÚLTIMO RESULTADO"])
        self.trackers_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.trackers_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.trackers_table.horizontalHeader().setMinimumSectionSize(150)
        self.trackers_table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.trackers_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.trackers_table.verticalHeader().setVisible(False)
        trlay.addWidget(self.trackers_table)
        self.tabs.addTab(trackers_tab, "Trackers")
        peer_tab = QWidget()
        peer_tab.setObjectName("tabContents")
        peer_layout = QVBoxLayout(peer_tab)
        self.peer_summary = QLabel("Selecciona un torrent para ver sus fuentes.")
        self.peer_summary.setObjectName("muted")
        self.peer_summary.setWordWrap(True)
        peer_layout.addWidget(self.peer_summary)
        self._last_peers_signature = None
        self.peers_table = QTableWidget(0, 5)
        self.peers_table.setHorizontalHeaderLabels(["IP / PUERTO", "CLIENTE", "BAJADA", "SUBIDA", "DISPONIBILIDAD"])
        peer_header = self.peers_table.horizontalHeader()
        peer_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        peer_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for col, width in ((2, 95), (3, 95), (4, 160)):
            peer_header.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
            self.peers_table.setColumnWidth(col, width)
        peer_header.setMinimumSectionSize(110)
        self.peers_table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.peers_table.verticalHeader().setVisible(False)
        self.peers_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        peer_layout.addWidget(self.peers_table)
        self.tabs.addTab(peer_tab, "Pares")
        graph_tab = QWidget()
        graph_tab.setObjectName("tabContents")
        graph_lay = QVBoxLayout(graph_tab)
        graph_lay.addWidget(QLabel("TRÁFICO DEL TORRENT SELECCIONADO · ÚLTIMOS 3.75 MINUTOS"))
        self.selected_graph = TransferGraph(capacity=150)
        graph_lay.addWidget(self.selected_graph)
        self.tabs.addTab(graph_tab, "Gráficas")
        safety_tab = QWidget()
        safety_tab.setObjectName("tabContents")
        safety_layout = QVBoxLayout(safety_tab)
        safety_layout.setContentsMargins(16, 14, 16, 14)
        safety_heading = QLabel("SEGURIDAD LOCAL · INSPECCIÓN INFORMATIVA")
        safety_heading.setObjectName("statLabel")
        safety_layout.addWidget(safety_heading)
        self.safety_summary = QLabel("Selecciona un torrent para revisar sus nombres y espacio disponible.")
        self.safety_summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.safety_summary.setWordWrap(True)
        safety_layout.addWidget(self.safety_summary)
        safety_layout.addWidget(QLabel("Para calcular SHA-256, selecciona un archivo ya descargado desde el diálogo."))
        verify_file = QPushButton("Calcular SHA-256 de un archivo descargado")
        verify_file.clicked.connect(self.calculate_file_hash)
        safety_layout.addWidget(verify_file)
        self.hash_result = QLineEdit()
        self.hash_result.setReadOnly(True)
        self.hash_result.setPlaceholderText("El resultado SHA-256 aparecerá aquí")
        safety_layout.addWidget(self.hash_result)
        copy_hash = QPushButton("Copiar SHA-256")
        copy_hash.clicked.connect(lambda: QApplication.clipboard().setText(self.hash_result.text()))
        safety_layout.addWidget(copy_hash)
        security_note = QLabel("Este informe NO sustituye a un antivirus: las extensiones y hashes no determinan si un archivo es seguro. No se ejecutan archivos.")
        security_note.setWordWrap(True)
        security_note.setObjectName("muted")
        safety_layout.addWidget(security_note)
        safety_layout.addStretch()
        self.tabs.addTab(safety_tab, "Seguridad")
        # Panel de interpretación por torrent: no ejecuta conexiones ni cambia ajustes.
        diagnosis_tab = QWidget()
        diagnosis_tab.setObjectName("tabContents")
        why = QVBoxLayout(diagnosis_tab)
        why.setContentsMargins(18, 12, 18, 14)
        self.why_title = QLabel("Selecciona un torrent")
        self.why_title.setObjectName("emptyTitle")
        self.why_title.setTextFormat(Qt.TextFormat.PlainText)
        self.why_title.setWordWrap(True)
        why.addWidget(self.why_title)
        self.why_body = QLabel("El diagnóstico mostrará evidencia observada y pasos recomendados.")
        self.why_body.setTextFormat(Qt.TextFormat.PlainText)
        self.why_body.setWordWrap(True)
        self.why_body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        why.addWidget(self.why_body)
        why_actions = QHBoxLayout()
        copy_reason = QPushButton("Copiar explicación")
        copy_reason.clicked.connect(self.copy_torrent_reason)
        why_actions.addWidget(copy_reason)
        reannounce_why = QPushButton("Intentar recuperar fuentes")
        reannounce_why.setToolTip("Reintenta DHT y/o trackers sin añadir servidores ni modificar archivos; puede no encontrar semillas.")
        reannounce_why.clicked.connect(self.recover_selected)
        why_actions.addWidget(reannounce_why)
        why_actions.addStretch()
        why.addLayout(why_actions)
        why.addStretch(1)
        self.tabs.addTab(diagnosis_tab, "Diagnóstico")
        radar_tab = QWidget()
        radar_layout = QVBoxLayout(radar_tab)
        radar_layout.setContentsMargins(18, 14, 18, 16)
        radar_heading = QLabel("SWARM RADAR · FUENTES OBSERVADAS")
        radar_heading.setObjectName("statLabel")
        radar_layout.addWidget(radar_heading)
        self.radar_summary = QLabel("Selecciona un torrent para consultar su enjambre.")
        self.radar_summary.setTextFormat(Qt.TextFormat.PlainText)
        self.radar_summary.setWordWrap(True)
        self.radar_summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        radar_layout.addWidget(self.radar_summary)
        radar_note = QLabel("Observación local: no se modifican trackers, DHT ni puertos. Sin semillas conectadas no significa torrent muerto.")
        radar_note.setObjectName("muted")
        radar_note.setWordWrap(True)
        radar_layout.addWidget(radar_note)
        radar_layout.addStretch(1)
        self.tabs.addTab(radar_tab, "Swarm Radar")
        self.tabs.setTabToolTip(6, "¿Por qué no descarga? Explicación de causas y pasos recomendados")
        self.why_body.setMinimumHeight(60)
        self.tabs.currentChanged.connect(lambda _index: self.update_details())
        dlay.addWidget(self.tabs)
        splitter.addWidget(detail)
        splitter.setStretchFactor(0, 7)
        splitter.setStretchFactor(1, 3)
        saved_layout = self.engine.store.load_json("ui_layout.json", {})
        if not isinstance(saved_layout, dict):
            saved_layout = {}
        raw_ratio = saved_layout.get("library_ratio", 61)
        self._library_ratio = max(35, min(85, raw_ratio)) if isinstance(raw_ratio, int) else 61
        splitter.setSizes([self._library_ratio * 5, (100 - self._library_ratio) * 5])
        splitter.splitterMoved.connect(lambda *_: self._layout_save_timer.start(750))
        QTimer.singleShot(0, self._restore_library_splitter)
        # El usuario puede ocultar/mostrar detalles y ampliar la biblioteca.
        detail_action = QPushButton("▾  Ocultar detalles")
        detail_action.setObjectName("compactButton")
        detail_action.setToolTip("Mostrar u ocultar el panel inferior. Arrastra la línea divisoria para ajustar su altura.")
        detail_action.clicked.connect(self.toggle_details)
        self.detail_toggle = detail_action
        operations.insertWidget(operations.count() - 2, detail_action)
        lay.addWidget(splitter, 1)
        self.bottom = QLabel("Listo para agregar archivos .torrent o enlaces magnet.")
        self.bottom.setStyleSheet("font-size:11px;color:#a0a4ae;")
        lay.addWidget(self.bottom)
        return page

    def _restore_library_splitter(self):
        if not hasattr(self, "main_splitter") or not self._detail_panel.isVisible():
            return
        total = max(250, self.main_splitter.height())
        upper = round(total * self._library_ratio / 100)
        self.main_splitter.setSizes([upper, max(132, total - upper)])
        self._adapt_table_columns()

    def _save_library_layout(self):
        if not hasattr(self, "main_splitter") or not self._detail_panel.isVisible():
            return
        sizes = self.main_splitter.sizes()
        total = sum(sizes)
        if total < 200:
            return
        ratio = round(100 * sizes[0] / total)
        if not 20 <= ratio <= 90:
            return
        self._library_ratio = ratio
        try:
            self.engine.store.save_json("ui_layout.json", {"library_ratio": ratio})
        except OSError as exc:
            logging.warning("No se pudo guardar distribución de la UI: %s", exc)

    def toggle_details(self):
        if self._detail_panel.isVisible():
            self._save_library_layout()
            self._detail_panel.hide()
            self.detail_toggle.setText("▸  Mostrar detalles")
        else:
            self._detail_panel.show()
            self.detail_toggle.setText("▾  Ocultar detalles")
            QTimer.singleShot(0, self._restore_library_splitter)

    def eventFilter(self, watched, event):
        if hasattr(self, "table") and watched is self.table.viewport() and event.type() == QEvent.Type.Resize:
            QTimer.singleShot(0, self._adapt_table_columns)
        return super().eventFilter(watched, event)

    def _adapt_table_columns(self):
        if not hasattr(self, "table"):
            return
        width = self.table.viewport().width()
        # Las columnas secundarias se ocultan automáticamente en pantallas
        # pequeñas; los datos siguen disponibles en Detalles y en el tooltip.
        self.table.setColumnHidden(9, width < 1090)  # Ratio
        self.table.setColumnHidden(8, width < 940)   # ETA
        self.table.setColumnHidden(5, width < 800)   # Subida
        self.table.setColumnHidden(7, width < 720)   # Semillas
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

    def _short_banner(self, message: str) -> str:
        # Evita que el aviso largo reduzca la altura útil de la biblioteca.
        max_pixels = max(150, self.insight_box.width() - 60)
        return self.insight_text.fontMetrics().elidedText(message, Qt.TextElideMode.ElideRight, max_pixels)

    def _performance_page(self):
        page = QWidget()
        page.setObjectName("page")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        body.setObjectName("scrollContent")
        lay = QVBoxLayout(body)
        lay.setContentsMargins(32, 24, 32, 25)
        lay.setSpacing(14)
        scroll.setWidget(body)
        outer.addWidget(scroll)
        title = QLabel("Rendimiento en tiempo real")
        title.setObjectName("headerTitle")
        lay.addWidget(title)
        subtitle = QLabel("Datos de transferencia observados localmente. Los perfiles no aumentan la velocidad de tu proveedor.")
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)
        lay.addWidget(subtitle)
        metrics = QHBoxLayout()
        values = (("DESCARGA ACTUAL", "performance_down"),
                  ("SUBIDA ACTUAL", "performance_up"),
                  ("PARES CONECTADOS", "performance_peers"),
                  ("TORRENTS", "performance_count"))
        for caption, prop in values:
            tile = StatCard(caption, "0", "◉")
            setattr(self, prop, tile.value)
            metrics.addWidget(tile)
        lay.addLayout(metrics)
        graph_card = QFrame()
        graph_card.setObjectName("detail")
        graph_lay = QVBoxLayout(graph_card)
        graph_lay.setContentsMargins(19, 15, 19, 13)
        heading = QLabel("ACTIVIDAD GLOBAL  ·  HISTORIAL DE APROX. 4.5 MINUTOS")
        heading.setObjectName("statLabel")
        graph_lay.addWidget(heading)
        self.performance_graph = TransferGraph(capacity=180)
        self.performance_graph.setMinimumHeight(180)
        graph_lay.addWidget(self.performance_graph, 1)
        lay.addWidget(graph_card, 1)
        profile_box = QFrame()
        profile_box.setObjectName("detail")
        form = QHBoxLayout(profile_box)
        form.setContentsMargins(20, 16, 20, 16)
        name_box = QVBoxLayout()
        name = QLabel("PERFIL DE TRANSFERENCIA")
        name.setObjectName("statLabel")
        name_box.addWidget(name)
        desc = QLabel("Equilibrado: 4 descargas activas · Máximo: 8 · Red limitada: 2. Las fuentes y tu velocidad real determinan el rendimiento.")
        desc.setObjectName("muted")
        desc.setWordWrap(True)
        name_box.addWidget(desc)
        form.addLayout(name_box, 1)
        self.profile_combo = QComboBox()
        self.profile_combo.addItems(list(PROFILES))
        self.profile_combo.setCurrentText(self.engine.settings.get("profile", "Equilibrado"))
        form.addWidget(self.profile_combo)
        apply = QPushButton("Aplicar perfil")
        apply.setObjectName("primary")
        apply.clicked.connect(self.apply_performance_profile)
        form.addWidget(apply)
        lay.addWidget(profile_box)
        smart_box = QFrame()
        smart_box.setObjectName("detail")
        smart_layout = QVBoxLayout(smart_box)
        smart_layout.setContentsMargins(20, 16, 20, 15)
        header = QLabel("SMART ENGINE  /  CONTROL CONSERVADOR DE SUBIDA")
        header.setObjectName("statLabel")
        smart_layout.addWidget(header)
        desc = QLabel("Optativo: usa la capacidad de subida que declares para reservar ancho de banda. "
                      "Nunca mide tu plan automáticamente ni cambia puertos o trackers.")
        desc.setObjectName("muted")
        desc.setWordWrap(True)
        smart_layout.addWidget(desc)
        controls = QGridLayout()
        controls.setHorizontalSpacing(14)
        controls.setVerticalSpacing(8)
        self.smart_enabled = QCheckBox("Activar optimización de subida")
        self.smart_enabled.setChecked(bool(self.engine.settings.get("smart_engine_enabled", False)))
        controls.addWidget(self.smart_enabled, 0, 0, 1, 4)
        capacity_label = QLabel("SUBIDA MEDIDA (MBPS)")
        capacity_label.setObjectName("statLabel")
        controls.addWidget(capacity_label, 1, 0)
        self.smart_capacity = QSpinBox()
        self.smart_capacity.setRange(0, 1000)
        self.smart_capacity.setSuffix(" Mbps")
        self.smart_capacity.setSpecialValueText("Sin medir")
        self.smart_capacity.setValue(int(self.engine.settings.get("upload_capacity_mbps", 0)))
        self.smart_capacity.setMinimumWidth(140)
        controls.addWidget(self.smart_capacity, 2, 0)
        percent_label = QLabel("OBJETIVO PARA BITTORRENT")
        percent_label.setObjectName("statLabel")
        controls.addWidget(percent_label, 1, 1)
        self.smart_percent = QSpinBox()
        self.smart_percent.setRange(50, 90)
        self.smart_percent.setSuffix(" %")
        self.smart_percent.setValue(int(self.engine.settings.get("smart_upload_percent", 80)))
        self.smart_percent.setMinimumWidth(105)
        controls.addWidget(self.smart_percent, 2, 1)
        submit = QPushButton("Aplicar configuración")
        submit.setObjectName("primary")
        submit.clicked.connect(self.apply_smart_engine)
        controls.addWidget(submit, 2, 2)
        controls.setColumnStretch(3, 1)
        smart_layout.addLayout(controls)
        self.smart_feedback = QLabel(smart_upload_report(self.engine.settings))
        self.smart_feedback.setWordWrap(True)
        self.smart_feedback.setObjectName("muted")
        smart_layout.addWidget(self.smart_feedback)
        lay.addWidget(smart_box)
        monitor_box = QFrame()
        monitor_box.setObjectName("detail")
        monitor_layout = QVBoxLayout(monitor_box)
        monitor_layout.setContentsMargins(20, 14, 20, 15)
        info = QLabel("TELEMETRÍA LOCAL  /  PROCESO E HISTORIAL")
        info.setObjectName("statLabel")
        monitor_layout.addWidget(info)
        self.process_metrics_label = QLabel("CPU/RAM del proceso: esperando medición...")
        self.process_metrics_label.setWordWrap(True)
        monitor_layout.addWidget(self.process_metrics_label)
        self.history_metrics_label = QLabel("Historial: preparando registro local...")
        self.history_metrics_label.setWordWrap(True)
        monitor_layout.addWidget(self.history_metrics_label)
        note = QLabel("Una muestra cada ~15 s; hasta 7 días en tu equipo, sin guardar nombres, IP ni enlaces.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        monitor_layout.addWidget(note)
        lay.addWidget(monitor_box)
        hint = QLabel("Consejo: aumentar las conexiones no crea semillas. Si las fuentes son escasas, espera o prueba otro torrent autorizado.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        return page

    def _network_page(self):
        page = QWidget()
        page.setObjectName("page")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(32, 27, 32, 24)
        lay.setSpacing(14)
        heading = QLabel("Red y diagnóstico")
        heading.setObjectName("headerTitle")
        lay.addWidget(heading)
        tip = QLabel("Interfaces y eventos que libtorrent informó. No se supone que NAT esté abierto ni que una VPN ofrezca anonimato.")
        tip.setObjectName("muted")
        tip.setWordWrap(True)
        lay.addWidget(tip)
        card = QFrame()
        card.setObjectName("detail")
        section = QVBoxLayout(card)
        section.setContentsMargins(20, 16, 20, 15)
        self.net_summary = QLabel("Recopilando información de conexión...")
        self.net_summary.setWordWrap(True)
        self.net_summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        section.addWidget(self.net_summary)
        lay.addWidget(card)
        route_actions = QHBoxLayout()
        route_probe = QPushButton("⟳  Detectar ruta de Windows")
        route_probe.setToolTip("Actualiza la interfaz local de libtorrent. No hace pruebas de velocidad ni conexiones a Internet.")
        route_probe.clicked.connect(self.redetect_network_route)
        route_actions.addWidget(route_probe)
        route_actions.addStretch()
        lay.addLayout(route_actions)
        self.tracker_insight = QLabel("Selecciona un torrent para consultar sus rastreadores.")
        self.tracker_insight.setWordWrap(True)
        self.tracker_insight.setObjectName("muted")
        lay.addWidget(self.tracker_insight)
        lay.addWidget(QLabel("EVENTOS DE RED (ÚLTIMOS REGISTRADOS)"))
        self.net_console = QPlainTextEdit()
        self.net_console.setReadOnly(True)
        self.net_console.setMinimumHeight(165)
        lay.addWidget(self.net_console, 1)
        actions = QHBoxLayout()
        refresh = QPushButton("⟳  Actualizar diagnóstico")
        refresh.clicked.connect(self.update_network_page)
        actions.addWidget(refresh)
        report = QPushButton("▤  Copiar diagnóstico del torrent seleccionado")
        report.clicked.connect(self.copy_network_diagnostic)
        actions.addWidget(report)
        actions.addStretch()
        lay.addLayout(actions)
        note = QLabel("Privacidad: BitTorrent puede revelar tu dirección IP a los pares. No desactives el firewall para acelerar descargas.")
        note.setStyleSheet("color:#ffc08d;")
        note.setWordWrap(True)
        lay.addWidget(note)
        return page

    def redetect_network_route(self):
        try:
            changed = self.engine.refresh_network_route(force=True)
            self.update_network_page()
            if changed:
                QMessageBox.information(self, "Apex Torrent", "Ruta local actualizada. Comprueba los trackers en los próximos minutos.")
            else:
                QMessageBox.information(self, "Apex Torrent", "No se detectaron cambios en la ruta, o tienes activado el modo Compatibilidad.")
        except Exception as exc:
            self.error(f"No se pudo actualizar la ruta de red: {exc}")

    def update_network_page(self):
        try:
            info = self.engine.network_overview()
            rows = list(self.cached_rows.values())
            seeds = sum(r.get("seeds",0) for r in rows)
            peers = sum(r.get("peers",0) for r in rows)
            self.net_summary.setText(
                f"Perfil: {info['profile']}     •     Límite de conexiones: {info['connections_limit']}\n"
                f"Pares conectados: {peers}     •     Semillas conectadas: {seeds}\n"
                f"DHT configurada: {'Sí' if info['dht_enabled'] else 'No'}"
                f"     •     UPnP / NAT-PMP: {'Sí' if info['upnp_enabled'] else 'No'}\n"
                f"{info['route_info']}\n"
                f"Escucha TCP/uTP/DHT: {info['requested_interfaces']}\n"
                f"Salida TCP: {info['outgoing_interfaces']}\n"
                f"Escuchas correctas registradas: {len(info['listen'])}     •     Fallos de escucha registrados: {len(info['failures'])}"
            )
            self.net_summary.setText(self.net_summary.text() + "\n" + info['smart'])
            rid, selected = self._selected()
            if rid is not None and selected is not None:
                insight = tracker_diagnosis(self.engine.tracker_details(rid))
                counts = insight['counts']
                failures = ", ".join(f"{name}: {count}" for name, count in insight['causes']) or "ninguno clasificado"
                self.tracker_insight.setText(
                    f"{swarm_hint(selected)}\n"
                    f"Trackers: {counts['total']} · Respondieron: {counts['respondieron']} · "
                    f"Anunciando: {counts['anunciando']} · Errores: {counts['errores']}\n"
                    f"Categorías de fallos observados: {failures}. El resultado puede cambiar con el tiempo."
                )
            else:
                self.tracker_insight.setText("Selecciona un torrent para consultar sus rastreadores.")
            events = info['listen'] + info['failures']
            self.net_console.setPlainText("\n".join(events) if events else "No hay eventos de escucha registrados todavía.")
        except Exception as exc:
            self.net_summary.setText(f"No fue posible consultar el motor: {exc}")

    def apply_performance_profile(self):
        name = self.profile_combo.currentText()
        try:
            limits = self.engine.apply_profile(name)
            self.connections.setValue(limits["connections_limit"])
            self.limit_down.setValue(limits["download_limit_kib"])
            self.limit_up.setValue(limits["upload_limit_kib"])
            self.profile_in_settings.setText(name)
            self.update_network_page()
            QMessageBox.information(self, "Perfil aplicado", f"Perfil «{name}» aplicado al motor y guardado."
                                    "\nLa velocidad también depende de tu internet y de las semillas disponibles.")
        except Exception as exc:
            self.error(str(exc))

    def apply_smart_engine(self):
        """Solo responde a un clic. Respeta los límites manuales existentes."""
        config = {
            "smart_engine_enabled": self.smart_enabled.isChecked(),
            "upload_capacity_mbps": self.smart_capacity.value(),
            "smart_upload_percent": self.smart_percent.value(),
        }
        try:
            self.engine.apply_settings(config)
            self.smart_feedback.setText(smart_upload_report(self.engine.settings))
            self.update_network_page()
        except Exception as exc:
            self.smart_enabled.setChecked(bool(self.engine.settings.get("smart_engine_enabled", False)))
            self.error(str(exc))

    def _sample_monitor(self, down: int, up: int, peers: int):
        """Un fallo en telemetría no puede cancelar el temporizador P2P."""
        stats = self._sampler.read()
        cpu, rss = stats.get("cpu_percent"), stats.get("rss_bytes")
        cpu_label = f"{cpu:.1f}%" if cpu is not None else "N/D (instala psutil con INSTALAR_WINDOWS.bat)"
        ram_label = readable_size(rss) if rss is not None else "N/D"
        self.process_metrics_label.setText(f"Proceso Apex Torrent: CPU {cpu_label}  ·  RAM {ram_label}")
        if self._journal is None:
            self.history_metrics_label.setText(self._history_error or "Historial local no disponible")
            return
        try:
            self._journal.append(down, up, peers, cpu, rss)
            summary = self._journal.summary(hours=24)
            self.history_metrics_label.setText(
                f"Últimas 24 h: {summary['count']} muestras · "
                f"Pico ↓ {readable_speed(summary['peak_down'])} · "
                f"Pico ↑ {readable_speed(summary['peak_up'])} · "
                f"Media ↓ {readable_speed(summary['average_down'])} · "
                f"Media ↑ {readable_speed(summary['average_up'])}"
            )
        except Exception as exc:
            self._history_error = f"Historial no disponible: {type(exc).__name__}"
            self.history_metrics_label.setText(self._history_error)
            logging.warning("Error al guardar telemetría (transferencias intactas): %s", exc)
            self._journal = None

    def change_torrent_limits(self):
        rid, selected = self._selected()
        if rid is None or selected is None:
            QMessageBox.information(self, "Límites", "Selecciona un torrent de la biblioteca.")
            return
        record = self.engine.records.get(rid, {})
        dialog = QDialog(self)
        dialog.setWindowTitle("Límites de transferencia · " + selected["name"])
        form = QFormLayout(dialog)
        form.setContentsMargins(24, 20, 24, 20)
        down = QSpinBox()
        up = QSpinBox()
        for spin, key in ((down, "download_limit_kib"), (up, "upload_limit_kib")):
            spin.setRange(0, 1000000)
            spin.setSuffix(" KiB/s")
            spin.setSpecialValueText("Sin límite")
            spin.setValue(int(record.get(key, 0)))
        form.addRow("Máximo de descarga", down)
        form.addRow("Máximo de subida", up)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Aplicar")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                self.engine.set_torrent_limits(rid, down.value(), up.value())
            except Exception as exc:
                self.error(str(exc))

    def _settings_page(self):
        page = QWidget()
        page.setObjectName("page")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setObjectName("pageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content.setObjectName("scrollContent")
        lay = QVBoxLayout(content)
        lay.setContentsMargins(32, 24, 32, 22)
        lay.setSpacing(14)
        scroll.setWidget(content)
        outer.addWidget(scroll)
        title = QLabel("Configuración de Apex Torrent")
        title.setObjectName("headerTitle")
        lay.addWidget(title)
        text = QLabel("Personaliza la red y los límites. Los cambios de velocidad se aplican en caliente.")
        text.setObjectName("muted")
        lay.addWidget(text)
        section = QFrame()
        section.setObjectName("detail")
        section.setMaximumWidth(770)
        form = QFormLayout(section)
        form.setContentsMargins(26, 24, 26, 24)
        form.setSpacing(19)
        self.target = QLineEdit(self.engine.settings["download_dir"])
        row = QHBoxLayout()
        row.addWidget(self.target, 1)
        browse = QPushButton("Cambiar carpeta")
        browse.clicked.connect(self.pick_settings_folder)
        row.addWidget(browse)
        form.addRow("Carpeta predeterminada", row)
        self.limit_down = QSpinBox()
        self.limit_down.setRange(0, 1000000)
        self.limit_down.setSuffix(" KiB/s")
        self.limit_down.setSpecialValueText("Sin límite")
        self.limit_down.setValue(int(self.engine.settings["download_limit_kib"]))
        form.addRow("Límite de descarga", self.limit_down)
        self.limit_up = QSpinBox()
        self.limit_up.setRange(0, 1000000)
        self.limit_up.setSuffix(" KiB/s")
        self.limit_up.setSpecialValueText("Sin límite")
        self.limit_up.setValue(int(self.engine.settings["upload_limit_kib"]))
        form.addRow("Límite de subida", self.limit_up)
        self.connections = QSpinBox()
        self.connections.setRange(10, 2000)
        self.connections.setValue(int(self.engine.settings["connections_limit"]))
        form.addRow("Máximo de conexiones", self.connections)
        self.profile_in_settings = QLabel(self.engine.settings.get("profile", "Equilibrado"))
        form.addRow("Perfil actual", self.profile_in_settings)
        self.appearance_combo = QComboBox()
        self.appearance_combo.addItems(list(THEMES))
        self.appearance_combo.setCurrentText(self.engine.settings.get("accent_theme", "Azul"))
        self.appearance_combo.setToolTip("Solo cambia colores de la interfaz; no altera el motor ni tu conexión.")
        self.appearance_combo.currentTextChanged.connect(self.preview_theme)
        form.addRow("Líneas / apariencia", self.appearance_combo)
        self.active_down = QSpinBox()
        self.active_down.setRange(1, 50)
        self.active_down.setValue(int(self.engine.settings.get("active_downloads", 4)))
        form.addRow("Descargas activas", self.active_down)
        self.active_seeds = QSpinBox()
        self.active_seeds.setRange(1, 50)
        self.active_seeds.setValue(int(self.engine.settings.get("active_seeds", 6)))
        form.addRow("Compartiendo activos", self.active_seeds)
        self.listen_port = QSpinBox()
        self.listen_port.setRange(0, 65535)
        self.listen_port.setSpecialValueText("Automático (recomendado)")
        self.listen_port.setValue(int(self.engine.settings.get("listen_port", 0)))
        self.listen_port.setToolTip("0 = Windows elige puerto libre; 1024–65535 = puerto fijo. Reinicia la app tras cambiar.")
        form.addRow("Puerto de escucha", self.listen_port)
        self.network_mode = QComboBox()
        self.network_mode.addItem("Ruta principal de Windows (recomendado)", "route")
        self.network_mode.addItem("Compatibilidad: todas las interfaces", "compatibility")
        current_network_mode = self.engine.settings.get("network_mode", "route")
        self.network_mode.setCurrentIndex(0 if current_network_mode == "route" else 1)
        self.network_mode.setToolTip("Ruta principal excluye adaptadores sin salida. Compatibilidad restaura el modo anterior; si hay VPN, revisa tu privacidad.")
        form.addRow("Adaptador de red", self.network_mode)
        route_note = QLabel("La ruta se detecta localmente y se vuelve a evaluar cuando cambia tu conexión. "
                            "No se fija una IP permanente. Si no hay ruta, se detienen las conexiones nuevas en modo recomendado.")
        route_note.setObjectName("muted")
        route_note.setWordWrap(True)
        form.addRow("", route_note)
        self.autoresume = QCheckBox("Reanudar descargas guardadas al abrir Apex Torrent")
        self.autoresume.setChecked(bool(self.engine.settings["auto_resume"]))
        form.addRow("Inicio", self.autoresume)
        self.dht = QCheckBox("Activar DHT para descubrimiento de pares")
        self.dht.setChecked(bool(self.engine.settings["dht"]))
        form.addRow("DHT", self.dht)
        self.tray_enabled = QCheckBox("Mantener transferencias en la bandeja al cerrar la ventana")
        self.tray_enabled.setChecked(bool(self.engine.settings.get("background_enabled", False)))
        self.tray_enabled.setToolTip("Desactivado por defecto. Si activas esto, utiliza Salir en el icono de bandeja para cerrar por completo.")
        form.addRow("Segundo plano", self.tray_enabled)
        self.notify_finished = QCheckBox("Mostrar notificaciones de descarga completada")
        self.notify_finished.setChecked(bool(self.engine.settings.get("notify_finished", True)))
        form.addRow("Avisos", self.notify_finished)
        self.notify_problems = QCheckBox("Alertar si una descarga lleva varios minutos sin fuentes o reporta un error")
        self.notify_problems.setChecked(bool(self.engine.settings.get("notify_problems", False)))
        self.notify_problems.setToolTip("Opcional. Avisa como máximo una vez cada 30 minutos por causa/torrent. No demuestra que no existan semillas.")
        form.addRow("Diagnóstico", self.notify_problems)
        self.upnp = QCheckBox("Activar UPnP / NAT-PMP (apertura automática de puertos)")
        self.upnp.setChecked(bool(self.engine.settings["upnp"]))
        form.addRow("Red", self.upnp)
        lay.addWidget(section)
        # Planificador por horas locales: optativo y no altera la sesión de red.
        schedule_card = QFrame()
        schedule_card.setObjectName("detail")
        schedule_layout = QVBoxLayout(schedule_card)
        schedule_layout.setContentsMargins(18, 16, 18, 16)
        heading = QLabel("DESCARGAS PROGRAMADAS")
        heading.setObjectName("statLabel")
        schedule_layout.addWidget(heading)
        self.schedule_enabled = QCheckBox("Descargar solo dentro de la ventana horaria")
        self.schedule_enabled.setChecked(bool(self.engine.settings.get("schedule_enabled", False)))
        schedule_layout.addWidget(self.schedule_enabled)
        schedule_row = QHBoxLayout()
        schedule_row.addWidget(QLabel("Desde"))
        self.schedule_start = QComboBox()
        self.schedule_start.addItems([f"{i:02d}:00" for i in range(24)])
        self.schedule_start.setCurrentIndex(int(self.engine.settings.get("schedule_start_hour", 0)))
        schedule_row.addWidget(self.schedule_start)
        schedule_row.addWidget(QLabel("Hasta"))
        self.schedule_end = QComboBox()
        self.schedule_end.addItems([f"{i:02d}:00" for i in range(24)])
        self.schedule_end.setCurrentIndex(int(self.engine.settings.get("schedule_end_hour", 0)))
        schedule_row.addWidget(self.schedule_end)
        schedule_row.addStretch()
        schedule_layout.addLayout(schedule_row)
        explanation = QLabel("La ventana admite horarios nocturnos. Inicio = fin permite todo el día. "
                             "No pausa torrents completados ni reanuda los pausados manualmente. "
                             "Solo se ejecuta mientras Apex Torrent esté abierto.")
        explanation.setObjectName("muted")
        explanation.setWordWrap(True)
        schedule_layout.addWidget(explanation)
        self.schedule_status = QLabel(schedule_caption(self.engine.settings))
        self.schedule_status.setObjectName("insightText")
        self.schedule_status.setWordWrap(True)
        schedule_layout.addWidget(self.schedule_status)
        lay.addWidget(schedule_card)
        save = QPushButton("Guardar configuración")
        save.setObjectName("primary")
        save.setMaximumWidth(235)
        save.clicked.connect(self.save_settings)
        lay.addWidget(save)
        note = QLabel("Privacidad: BitTorrent revela tu IP pública a otros pares.\n"
                      "Cambiar estos ajustes no convierte la conexión en anónima.")
        note.setStyleSheet("color:#f4b88e;padding-top:12px;")
        lay.addWidget(note)
        lay.addStretch()
        return page

    def _integrations_page(self):
        page = QWidget()
        page.setObjectName("page")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setObjectName("pageScroll")
        scroll.setWidgetResizable(True)
        root = QWidget()
        root.setObjectName("scrollContent")
        lay = QVBoxLayout(root)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(15)
        title = QLabel("Ecosistema Apex")
        title.setObjectName("headerTitle")
        lay.addWidget(title)
        intro = QLabel("Conecta tus programas instalados. Los análisis y la apertura de carpetas siempre requieren tu acción; no se envían archivos a internet.")
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        self.integration_edits = {}
        self.integration_labels = {}
        descriptions = {
            "thunderbolt": "Thunderbolt · Solicita la revisión de un archivo completado. Si Thunderbolt todavía no tiene receptor nativo, Apex Bridge confirma la apertura y solicita revisión manual.",
            "smart_files": "Smart Files · Solicita abrir la carpeta de descarga. Sin receptor nativo, abre el gestor y la ubicación en Explorador.",
        }
        for app, name in COMPANIONS.items():
            card = QFrame()
            card.setObjectName("detail")
            card_lay = QVBoxLayout(card)
            card_lay.setContentsMargins(18, 16, 18, 16)
            card_lay.setSpacing(9)
            heading = QLabel(name.upper())
            heading.setObjectName("statLabel")
            card_lay.addWidget(heading)
            description = QLabel(descriptions[app])
            description.setWordWrap(True)
            card_lay.addWidget(description)
            inputs = QHBoxLayout()
            entry = QLineEdit(self.integration_paths[app])
            entry.setPlaceholderText("Selecciona la aplicación .exe o INICIAR_WINDOWS.bat")
            entry.setToolTip("Solo se abre un ejecutable elegido por ti, nunca el contenido descargado")
            inputs.addWidget(entry, 1)
            choose = QPushButton("Buscar programa")
            choose.clicked.connect(lambda checked=False, key=app: self._browse_companion(key))
            inputs.addWidget(choose)
            card_lay.addLayout(inputs)
            self.integration_edits[app] = entry
            status = QLabel(bridge_connection_state(self.integration_paths[app], app))
            status.setObjectName("muted")
            status.setWordWrap(True)
            card_lay.addWidget(status)
            self.integration_labels[app] = status
            response = QLabel("Apex Bridge: sin solicitudes en esta sesión.")
            response.setObjectName("muted")
            response.setWordWrap(True)
            response.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            card_lay.addWidget(response)
            if not hasattr(self, 'bridge_status_labels'):
                self.bridge_status_labels = {}
            self.bridge_status_labels[app] = response
            actions = QHBoxLayout()
            launch = QPushButton("Abrir " + name)
            launch.clicked.connect(lambda checked=False, key=app: self._launch_integration(key))
            actions.addWidget(launch)
            if app == "thunderbolt":
                special = QPushButton("Revisar archivo completado")
                special.clicked.connect(self.review_with_thunderbolt)
            else:
                special = QPushButton("Abrir carpeta seleccionada")
                special.clicked.connect(self.open_with_smart_files)
            actions.addWidget(special)
            actions.addStretch(1)
            card_lay.addLayout(actions)
            lay.addWidget(card)
        store_btn = QPushButton("Guardar rutas de integración")
        store_btn.setObjectName("primary")
        store_btn.clicked.connect(self._save_integrations)
        store_btn.setMaximumWidth(280)
        lay.addWidget(store_btn)
        warning = QLabel("Apex Bridge v2 intercambia solicitudes y acuses LOCALES. Para Thunderbolt, solo su propio motor puede confirmar un análisis. Si tu versión no incluye receptor nativo, se abrirá para revisión MANUAL. El puente no declara seguro ningún archivo por sí solo: sin resultado de análisis confirmado, exige revisión manual.")
        warning.setWordWrap(True)
        warning.setObjectName("muted")
        lay.addWidget(warning)
        lay.addStretch()
        scroll.setWidget(root)
        outer.addWidget(scroll)
        return page

    def _browse_companion(self, app):
        initial = self.integration_edits[app].text() or str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self, "Elegir " + COMPANIONS[app], initial,
            "Aplicaciones Windows (*.exe *.bat)")
        if path:
            self.integration_edits[app].setText(path)

    def _save_integrations(self):
        settings = {key: edit.text().strip().strip('"') for key, edit in self.integration_edits.items()}
        try:
            for key, value in settings.items():
                if value:
                    executable_path(value)
            self.engine.store.save_json("integrations.json", settings)
        except (IntegrationError, OSError) as exc:
            self.error(str(exc))
            return False
        self.integration_paths = settings
        for key in COMPANIONS:
            self.integration_labels[key].setText(bridge_connection_state(settings[key], key))
        QMessageBox.information(self, "Ecosistema Apex", "Rutas guardadas localmente. No se ejecutó ningún análisis ni se modificó otro programa.")
        return True

    def _launch_integration(self, app):
        try:
            start_companion(self.integration_paths[app], app)
        except IntegrationError as exc:
            self.error(str(exc) + "\nConfigura la ruta en Ecosistema Apex.")

    def _download_context(self):
        rid, rec = self._selected()
        if not rid or not rec:
            raise IntegrationError("Selecciona primero un torrent en Biblioteca.")
        return rec

    def _bridge_launch(self, app: str, action: str, target: Path, approved_root: Path):
        if app in self._bridge_pending:
            QMessageBox.information(self, "Apex Bridge", "Ya hay una solicitud pendiente para esta aplicación. Consulta su estado en Ecosistema Apex.")
            return
        ticket, mode = send_request(self.engine.store.base,
                                    self.integration_paths[app], app, action, target, approved_root)
        self._bridge_pending[app] = (ticket, mode)
        label = self.bridge_status_labels.get(app)
        if label:
            label.setText("Apex Bridge: solicitud enviada · esperando acuse local.")
        QMessageBox.information(self, "Apex Bridge", "Solicitud entregada al puente local. Todavía NO hay un resultado de análisis confirmado. Revisa Ecosistema Apex para conocer el estado.")

    def _poll_bridge(self):
        for app, (ticket, mode) in list(self._bridge_pending.items()):
            label = self.bridge_status_labels.get(app)
            try:
                response = read_receipt(ticket)
                if response is None:
                    if time.time() - ticket.launched_at < MAX_AGE_SECONDS:
                        continue
                    message = "Apex Bridge: no se recibió respuesta; consulta el programa receptor."
                    final = True
                else:
                    message = receipt_message(response, app, mode)
                    final = response['status'] not in ('received', 'scanning')
            except IntegrationError as exc:
                message = "Apex Bridge: respuesta inválida: " + str(exc)
                final = True
            if label:
                label.setText(message)
            if final:
                discard(ticket)
                self._bridge_pending.pop(app, None)

    def review_with_thunderbolt(self):
        try:
            rec = self._download_context()
            if rec.get("progress", 0) < 1 or rec.get("error"):
                raise IntegrationError("Thunderbolt solo recibe archivos completados y sin error.")
            root = rec.get("save_path", "")
            file_name, _ = QFileDialog.getOpenFileName(self, "Archivo completado para revisar", root)
            if not file_name:
                return
            path = selected_complete_file(root, file_name, True)
            QApplication.clipboard().setText(str(path))
            self._bridge_launch("thunderbolt", "scan_file", path, Path(root))
        except (IntegrationError, OSError, ValueError) as exc:
            self.error(str(exc))

    def open_with_smart_files(self):
        try:
            rec = self._download_context()
            root = selected_folder(rec.get("save_path", ""))
            self._bridge_launch("smart_files", "open_folder", root, root)
        except (IntegrationError, OSError, ValueError) as exc:
            self.error(str(exc))

    def _about_page(self):
        page = QWidget()
        page.setObjectName("page")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setObjectName("pageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content.setObjectName("scrollContent")
        lay = QVBoxLayout(content)
        lay.setContentsMargins(32, 26, 32, 25)
        lay.setSpacing(14)
        scroll.setWidget(content)
        outer.addWidget(scroll)
        logo = QLabel("◈  APEX TORRENT  /  BLACK EDITION")
        logo.setStyleSheet("font-size:25px;font-weight:800;")
        lay.addWidget(logo)
        sub = QLabel(f"Versión {VERSION} · Cliente BitTorrent de escritorio para Windows")
        sub.setObjectName("hint")
        lay.addWidget(sub)
        intro = QLabel("Descarga y comparte archivos mediante el protocolo BitTorrent sin anuncios "
                       "ni depender de µTorrent. Interfaz creada con PySide6 y motor libtorrent.")
        intro.setWordWrap(True)
        intro.setMaximumWidth(730)
        intro.setStyleSheet("font-size:14px;color:#c8dbe8;")
        lay.addWidget(intro)
        lay.addSpacing(14)
        for heading, content in [
            ("MOTOR", "libtorrent 2.0 · DHT · PEX · trackers · magnet · BitTorrent v1/v2"),
            ("INTERFAZ", "Qt / PySide6 · Windows · Black Edition · temas de líneas"),
            ("TUS DATOS", "La biblioteca, ajustes y archivos de reanudación se almacenan localmente."),
            ("LICENCIAS", "libtorrent: licencia BSD. PySide6: LGPL/comercial según su distribución."),
        ]:
            one = QLabel(heading)
            one.setStyleSheet("font-weight:800;font-size:11px;")
            lay.addWidget(one)
            two = QLabel(content)
            two.setStyleSheet("color:#a0b7c9;")
            lay.addWidget(two)
        lay.addSpacing(20)
        dirbutton = QPushButton("Abrir datos locales de Apex Torrent")
        dirbutton.setMaximumWidth(310)
        dirbutton.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(DATA_DIR))))
        lay.addWidget(dirbutton)
        lay.addStretch()
        return page

    def _add_shortcuts(self):
        for seq, action in [("Ctrl+O", self.add_file), ("Ctrl+M", self.add_magnet),
                            ("Delete", self.remove_selected), ("F5", self.refresh)]:
            QShortcut(QKeySequence(seq), self, activated=action)

    def change_filter(self, value: str):
        self.active_filter = value
        for btn in self.filters:
            btn.setChecked(btn.text() == value)
        self.refresh_table()
        if self.pages.currentIndex() == 0:
            self._current_nav = {"Todos": "Biblioteca", "Descargando": "Activos",
                                 "Completados": "Completados", "Pausados": "Pausados"}.get(value, "Biblioteca")
            for label, btn in self.nav_buttons.items():
                btn.setChecked(label == self._current_nav)

    def _selected_id(self):
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _selected(self):
        rid = self._selected_id()
        if not rid:
            return None, None
        return rid, self.cached_rows.get(rid)

    def refresh(self):
        self.engine.process_alerts()
        now = time.monotonic()
        try:
            self.engine.refresh_network_route()
        except Exception as exc:
            logging.warning("Ruta de red: %s", exc)
        if now - self._last_schedule_tick >= 30:
            self._last_schedule_tick = now
            try:
                self.engine.apply_schedule()
            except Exception as exc:
                logging.warning("Planificador no disponible: %s", exc)
        current_rows = self.engine.rows()
        self.cached_rows = {rec["id"]: rec for rec in current_rows}
        self.refresh_error_banner()
        self.count_stat.value.setText(str(len(current_rows)))
        self.down_stat.value.setText(readable_speed(sum(displayed_payload_rate(r) for r in current_rows)))
        self.down_stat.setToolTip("Velocidad de contenido útil si libtorrent la informa; de lo contrario, tráfico total informado por el motor.")
        self.up_stat.value.setText(readable_speed(sum(r["up"] for r in current_rows)))
        self.finish_stat.value.setText(str(sum(r["progress"] >= 1.0 for r in current_rows)))
        self.peers_stat.value.setText(str(sum(r["peers"] for r in current_rows)))
        down = sum(r["down"] for r in current_rows)
        up = sum(r["up"] for r in current_rows)
        self.performance_graph.add_sample(down, up)
        rid, selected_rec = self._selected()
        if rid != self._selected_graph_id:
            self.selected_graph.history.downloads.clear()
            self.selected_graph.history.uploads.clear()
            self._selected_graph_id = rid
        self.selected_graph.add_sample(selected_rec.get("down",0) if selected_rec else 0,
                                       selected_rec.get("up",0) if selected_rec else 0)
        if self.tray is not None:
            self.tray.setToolTip(f"Apex Torrent · ↓ {readable_speed(down)} · ↑ {readable_speed(up)}")
        self.performance_down.setText(readable_speed(down))
        self.performance_up.setText(readable_speed(up))
        self.performance_peers.setText(str(sum(r["peers"] for r in current_rows)))
        self.performance_count.setText(str(len(current_rows)))
        if now >= self._next_monitor_sample:
            self._next_monitor_sample = now + 15.0
            self._sample_monitor(down, up, sum(r["peers"] for r in current_rows))
        if self.pages.currentIndex() == 3 and self._tick_count % 20 == 0:
            self.schedule_status.setText(schedule_caption(self.engine.settings))
        if self.pages.currentIndex() == 2 and self._tick_count % 5 == 0:
            self.update_network_page()
        self.bottom.setText(f"{len(current_rows)} torrents · Descarga {readable_speed(sum(displayed_payload_rate(r) for r in current_rows))} · "
                            f"Subida {readable_speed(sum(r['up'] for r in current_rows))} · "
                            f"Estado guardado localmente")
        if self.pages.currentIndex() == 0:
            self.refresh_table()
        self._notify_completed(current_rows)
        self._notify_problem_rows(current_rows, now)
        self._tick_count += 1
        if self.pages.currentIndex() == 0:
            # Detalles básicos son ligeros; sincronizar cada tick para evitar
            # "Esperando pares" en la tabla pero "Descargando" abajo.
            if self.tabs.currentIndex() == 0 or self._tick_count % 4 == 0:
                self.update_details()

    def refresh_error_banner(self):
        errors = [r for r in self.cached_rows.values() if r.get("state") == "Error"]
        if not errors:
            self.error_box.setVisible(False)
            return
        first = errors[0]
        detail = first.get("error") or "Error no especificado por el motor"
        self.error_label.setText(
            f"⚠ {len(errors)} descarga(s) con error. {first['name']}: {detail}"
        )
        self.error_label.setToolTip(first.get("error_hint", ""))
        self.error_box.setVisible(True)

    def show_first_error(self):
        errors = [r for r in self.cached_rows.values() if r.get("state") == "Error"]
        if errors:
            self.search.clear()
            self.change_filter("Todos")
            self._select_by_id(errors[0]["id"])

    def copy_diagnostic(self):
        errors = [r for r in self.cached_rows.values() if r.get("state") == "Error"]
        if not errors:
            QMessageBox.information(self, "Apex Torrent", "No hay descargas con error para diagnosticar.")
            return
        lines = [f"Apex Torrent {VERSION} - diagnóstico local", "", 
                 "IMPORTANTE: este texto incluye nombres y rutas de archivos locales.", ""]
        for rec in errors:
            path = rec.get("save_path", "")
            lines.extend([
                f"Torrent: {rec.get('name', '—')}",
                f"Estado: {rec.get('state', '—')}",
                f"Mensaje libtorrent: {rec.get('error') or 'Sin detalle'}",
                f"Código numérico: {rec.get('error_code') if rec.get('error_code') is not None else 'No disponible'}",
                f"Categoría: {rec.get('error_category') or 'No disponible'}",
                f"Archivo / componente: {rec.get('error_file') or 'No informado'}",
                f"Alerta del motor: {rec.get('error_alert') or 'Ninguna alerta registrada'}",
                f"Error al leer el binding: {rec.get('error_exception') or 'Ninguno'}",
                f"Orientación: {rec.get('error_hint') or '—'}",
                f"Carpeta: {path or '—'}",
            ])
            if path:
                try:
                    space = shutil.disk_usage(path)
                    lines.append(f"Espacio libre: {readable_size(space.free)}")
                except OSError as exc:
                    lines.append(f"Espacio libre: No disponible ({exc})")
            lines.append("")
        QApplication.clipboard().setText("\n".join(lines))
        QMessageBox.information(self, "Diagnóstico copiado",
                                "Se copió el diagnóstico al portapapeles. Contiene nombres y rutas locales; revísalo antes de compartirlo.")

    def show_torrent_diagnosis(self):
        rid, row = self._selected()
        if not rid or not row:
            QMessageBox.information(self, "Apex Torrent", "Selecciona primero una descarga.")
            return
        self.tabs.setCurrentIndex(6)
        self.update_details()

    def copy_torrent_reason(self):
        rid, row = self._selected()
        if not rid or not row:
            QMessageBox.information(self, "Apex Torrent", "Selecciona primero una descarga.")
            return
        try:
            result = self.engine.diagnose_download(rid, row)
            QApplication.clipboard().setText(
                f"Apex Torrent {VERSION} — explicación de descarga\n"
                f"Torrent: {row.get('name', '—')}\n\n{result.report()}\n\n"
                "Aviso: el nombre y el mensaje técnico pueden incluir datos privados."
            )
            QMessageBox.information(self, "Apex Torrent", "Explicación copiada. Revisa nombres, errores y rutas antes de compartirla.")
        except Exception as exc:
            self.error(str(exc))

    def _refresh_torrent_reason(self, rid, row):
        try:
            result = self.engine.diagnose_download(rid, row)
            self.why_title.setText(result.title)
            self.why_body.setText(result.report().split("\n", 1)[1])
            # La misma interpretación aparece en el panel contextual.
            # Banner compacto: el informe completo sigue en Diagnóstico.
            hint = result.advice.split(". ", 1)[0].rstrip(".")
            activity, explanation = download_activity(row)
            concise = ("◉  " + activity + " · " + explanation) if activity == "Solo protocolo" else ("◉  " + result.title + " · " + hint)
            if len(concise) > 165:
                concise = concise[:162].rsplit(" ", 1)[0] + "…"
            self.insight_text.setText(self._short_banner(concise))
            self.insight_text.setToolTip(result.report())
        except Exception as exc:
            self.why_title.setText("Diagnóstico no disponible")
            self.why_body.setText(type(exc).__name__ + ": " + str(exc))

    def refresh_table(self):
        selected = self._selected_id()
        search = self.search.text().strip().lower()
        matching = []
        for rec in self.cached_rows.values():
            if search not in rec["name"].lower():
                continue
            if self.active_filter == "Descargando" and (rec["progress"] >= 1.0 or rec["paused"]):
                continue
            if self.active_filter == "Completados" and rec["progress"] < 1.0:
                continue
            if self.active_filter == "Pausados" and not rec["paused"]:
                continue
            matching.append(rec)
        # No reconstruir todas las celdas si no hay cambios visibles.
        signature = (self.active_filter, search, tuple(
            (r["id"], r["name"], r["size"], round(r["progress"], 5), r["state"],
             r["down"], r.get("payload_down"), r["up"], r["peers"], r["seeds"], r["eta"], round(r["ratio"], 3))
            for r in matching))
        self.library_stack.setCurrentIndex(0 if matching else 1)
        if not matching:
            empty_text = {"Completados": "Todavía no hay descargas completadas",
                          "Pausados": "No hay torrents pausados",
                          "Descargando": "No hay descargas activas"}.get(self.active_filter, "Tu biblioteca está vacía")
            if search:
                empty_text = "No se encontraron resultados"
            self.empty_title.setText(empty_text)
            self.empty_hint.setText("Prueba otro nombre o cambia el filtro." if search else
                                    "Agrega un archivo .torrent o un magnet para empezar." if not self.cached_rows else
                                    "Tus torrents siguen disponibles en las otras categorías.")
        if signature == self._last_table_signature:
            return
        self._last_table_signature = signature
        with QSignalBlocker(self.table):
            self.table.setRowCount(len(matching))
            for i, rec in enumerate(matching):
                entries = [rec["name"], readable_size(rec["size"]) if rec["size"] else "Pendiente",
                           "", rec["state"], readable_speed(displayed_payload_rate(rec)), readable_speed(rec["up"]),
                           str(rec["peers"]), str(rec["seeds"]), readable_eta(rec["eta"]), f"{rec['ratio']:.2f}"]
                for col, value in enumerate(entries):
                    item = self.table.item(i, col)
                    if item is None:
                        item = QTableWidgetItem()
                        self.table.setItem(i, col, item)
                    item.setText(value)
                    if col == 0:
                        item.setData(Qt.ItemDataRole.UserRole, rec["id"])
                        item.setToolTip(rec["name"])
                    if col == 4:
                        kind, detail = download_activity(rec)
                        item.setToolTip(f"{kind} · {detail}\n"
                                        f"Velocidad total de protocolo: {readable_speed(rec.get('down', 0))}\n"
                                        f"Datos útiles: {readable_speed(rec['payload_down']) if rec.get('payload_down') is not None else 'No disponibles en este motor'}")
                    if col == 2:
                        item.setData(Qt.ItemDataRole.UserRole, rec["progress"])
                    if col == 3:
                        if rec.get("error"):
                            item.setToolTip(rec["error"] + "\n" + rec.get("error_hint", ""))
                        else:
                            item.setToolTip(rec["state"])
                        palette = {"Conectando": "#f0bc78", "Buscando fuentes": "#c1aee0", "Error": "#ff657f", "Compartiendo": "#45f4a8", "Completado": "#45f4a8",
                                   "Descargando": "#26deff", "Pausado": "#b09dcf",
                                   "Fuera de horario": "#f4b86f"}
                        item.setForeground(QColor(palette.get(rec["state"], "#d3e2ef")))
                    if col in (1, 4, 5, 6, 7, 8, 9):
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if rec["id"] == selected:
                    self.table.selectRow(i)
            # En 1.1.0 una biblioteca recuperada podía abrir con el panel vacío.
            if matching and selected is None:
                self.table.selectRow(0)
        if (matching and selected is None) or (selected and selected not in [r["id"] for r in matching]) or not matching:
            self.update_details()

    def update_details(self):
        rid, rec = self._selected()
        if not rid or not rec:
            self.insight_text.setText("Selecciona un torrent para consultar su disponibilidad.")
            self.insight_text.setToolTip("")
            self.why_title.setText("Selecciona un torrent")
            self.why_body.setText("Aquí se mostrarán posibles causas y pasos recomendados.")
            self._last_peers_signature = None
            self.peers_table.setRowCount(0)
            self.peer_summary.setText("Selecciona un torrent para consultar los pares.")
            self.radar_summary.setText("Selecciona un torrent para consultar su enjambre.")
            for label in self.details_labels.values():
                label.setFullText("—")
            self._fill_files([])
            self._latest_trackers = []
            self._render_trackers()
            self._files_id = None
            self._last_detail_id = None
            return
        values = {
            "Estado": rec["state"] + (f" · {rec['error']}" if rec.get("error") else "") +
                (f" [Código {rec['error_code']}]" if rec.get("error_code") is not None and rec.get("error") else ""),
            "Guardado en": rec.get("save_path", "—"),
            "Completado": f"{rec['progress']*100:.1f}%",
            "Descargado": f"{readable_size(rec['done'])} / {readable_size(rec['size'])}",
            "Pares / Semillas": f"{rec['peers']} pares · {rec['seeds']} semillas",
            "Info hash": rec.get("hash", "—"),
        }
        for key, value in values.items():
            self.details_labels[key].setFullText(value)
        # Redibujar únicamente la pestaña visible: evita escanear los archivos,
        # listar todos los trackers y consultar los pares cada 1.5 segundos.
        selected_changed = rid != self._last_detail_id
        self._last_detail_id = rid
        tab = self.tabs.currentIndex()
        trackers = []
        if tab == 1 and (selected_changed or self._files_id != rid or self._tick_count % 6 == 0):
            try:
                self._fill_files(self.engine.files(rid))
                self._files_id = rid
            except Exception as exc:
                logging.warning("No se pudieron leer archivos: %s", exc)
                self._fill_files([])
                self._files_id = None
        if tab == 2 or selected_changed or self._tick_count % 6 == 0:
            try:
                trackers = self.engine.tracker_details(rid)
                if tab == 2:
                    self._latest_trackers = trackers
                    self._render_trackers()
                    info = tracker_summary(trackers)
                    self.tracker_summary_label.setText(
                        f"TRACKERS  {info['total']} total · {info['respondieron']} respondieron · "
                        f"{info['anunciando']} anunciando · {info['errores']} con errores")
            except Exception as exc:
                logging.warning("No se pudieron leer trackers: %s", exc)
                if tab == 2:
                    self._fill_trackers([{"url": "Error de lectura", "state": "Error", "message": str(exc)}])
        if selected_changed or self._tick_count % 6 == 0 or tab == 6:
            self._refresh_torrent_reason(rid, rec)
        if tab == 5 and (selected_changed or self._tick_count % 8 == 0):
            self.refresh_security(rec, rid)
        if tab == 7:
            try:
                peers = self.engine.peer_details(rid)
                snapshot = summarize_swarm(rec, peers)
                self.radar_summary.setText(radar_text(snapshot))
            except Exception as exc:
                logging.warning("Swarm Radar no disponible: %s", exc)
                self.radar_summary.setText("Datos de enjambre no disponibles; descarga sin cambios.")
        if tab == 3:
            try:
                self._fill_peers(self.engine.peer_details(rid))
            except Exception as exc:
                logging.warning("No se pudo leer la lista de pares: %s", exc)
                self._fill_peers([])

    def _fill_peers(self, peers: list[dict]):
        if not peers:
            self.peer_summary.setText("Sin pares conectados en este instante. DHT y trackers pueden seguir buscando fuentes.")
        else:
            complete = sum(peer.get("progress", 0) >= 0.99999 for peer in peers)
            partial = sum(0 < peer.get("progress", 0) < 0.99999 for peer in peers)
            self.peer_summary.setText(
                f"{len(peers)} pares consultados · {complete} reportan archivo completo · "
                f"{partial} reportan piezas parciales. Los datos pueden cambiar en segundos."
            )
        signature = tuple((peer.get("endpoint"), peer.get("client"), peer.get("down"),
                           peer.get("up"), peer.get("progress")) for peer in peers)
        if self._last_peers_signature == signature:
            return
        self._last_peers_signature = signature
        with QSignalBlocker(self.peers_table):
            self.peers_table.setRowCount(len(peers))
            for i, peer in enumerate(peers):
                values = [peer["endpoint"], peer["client"], readable_speed(peer["down"]),
                          readable_speed(peer["up"]), peer.get("availability", f"{peer['progress']*100:.1f}%")]
                for c, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    item.setToolTip(value)
                    if c >= 2:
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.peers_table.setItem(i, c, item)

    def _fill_files(self, data: list[dict]):
        with QSignalBlocker(self.files_table):
            self.files_table.setRowCount(len(data))
            for i, entry in enumerate(data):
                item = QTableWidgetItem(entry["path"])
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked if entry["priority"] else Qt.CheckState.Unchecked)
                item.setData(Qt.ItemDataRole.UserRole, entry["index"])
                self.files_table.setItem(i, 0, item)
                self.files_table.setItem(i, 1, QTableWidgetItem(readable_size(entry["size"])))
                self.files_table.setItem(i, 2, QTableWidgetItem(readable_size(entry["downloaded"])))
                priority_names = {0:"Omitido",1:"Baja",4:"Normal",7:"Alta"}
                self.files_table.setItem(i, 3, QTableWidgetItem(priority_names.get(int(entry["priority"]), "Personalizada")))
        self.file_selected_hint.setText(f"{len(data)} archivo(s) · marca o selecciona para ajustar prioridades")

    def _render_trackers(self, _value=None):
        """Filtra datos de la sesión sin modificar ni anunciar trackers."""
        selection = self.tracker_filter.currentText()
        trackers = [entry for entry in self._latest_trackers if
                    selection == "Todos" or
                    (selection == "Respondieron" and entry.get("state") == "Respondió") or
                    (selection == "Anunciando" and entry.get("state") == "Anunciando") or
                    (selection == "Con error" and entry.get("state") == "Error")]
        self._fill_trackers(trackers)

    def _fill_trackers(self, trackers: list[dict]):
        # Evitar reconstruir cientos de celdas si no cambiaron los datos.
        signature = tuple((r.get("url"), r.get("state"), r.get("message")) for r in trackers)
        if signature == getattr(self, "_last_tracker_signature", None):
            return
        self._last_tracker_signature = signature
        self.trackers_table.setRowCount(len(trackers))
        for i, entry in enumerate(trackers):
            address = entry.get("url", "—")
            state = entry.get("state", "—")
            detail = entry.get("message", "")
            url_item = QTableWidgetItem(address)
            url_item.setToolTip(address)
            status_item = QTableWidgetItem(state + (f" · {detail}" if detail else ""))
            status_item.setToolTip(detail or state)
            if state == "Error":
                status_item.setForeground(QColor("#ff718b"))
            elif state == "Respondió":
                status_item.setForeground(QColor("#42ffbc"))
            self.trackers_table.setItem(i, 0, url_item)
            self.trackers_table.setItem(i, 1, status_item)

    def _set_file_priorities_bulk(self, priority: int, all_files: bool = False):
        rid = self._files_id
        if rid is None:
            QMessageBox.information(self, "Prioridad de archivos", "Selecciona un torrent con metadatos y abre Archivos.")
            return
        selected_rows = range(self.files_table.rowCount()) if all_files else sorted(set(
            index.row() for index in self.files_table.selectedIndexes()))
        changes = {}
        for row in selected_rows:
            item = self.files_table.item(row, 0)
            if item is not None:
                changes[int(item.data(Qt.ItemDataRole.UserRole))] = priority
        if not changes:
            QMessageBox.information(self, "Prioridad de archivos", "Selecciona una o más filas.")
            return
        try:
            self.engine.set_file_priorities(rid, changes)
            self._fill_files(self.engine.files(rid))
        except Exception as exc:
            self.error(str(exc))

    def recover_selected(self):
        """Recovery is a one-shot discovery retry, never a promise of seeds."""
        rid = self._require_id()
        if not rid:
            return
        try:
            outcome = self.engine.attempt_recovery(rid)
        except EngineError as exc:
            self.error(str(exc))
            return
        QMessageBox.information(self, "Comprobación de fuentes", outcome["message"])
        self.refresh()

    def reannounce_selected(self):
        rid = self._require_id()
        if rid is None:
            return
        try:
            self.engine.reannounce(rid)
            self.refresh()
            QMessageBox.information(self, "Apex Torrent",
                                    "Se solicitó un nuevo anuncio a los trackers. "
                                    "Espera unos segundos y revisa la pestaña Trackers.")
        except Exception as exc:
            self.error(str(exc))

    def copy_network_diagnostic(self):
        rid, rec = self._selected()
        if not rid or not rec:
            QMessageBox.information(self, "Apex Torrent", "Primero selecciona un torrent de la biblioteca.")
            return
        try:
            report = self.engine.network_diagnostic(rid, rec)
            QApplication.clipboard().setText(report)
            QMessageBox.information(self, "Diagnóstico copiado",
                                    "Diagnóstico de red copiado. Comprueba las rutas y URLs antes de compartirlo.")
        except Exception as exc:
            self.error(str(exc))

    def change_file_priority(self, item: QTableWidgetItem):
        if item.column() != 0:
            return
        rid = self._files_id
        if not rid:
            return
        idx = item.data(Qt.ItemDataRole.UserRole)
        if idx is None:
            return
        try:
            priority = 4 if item.checkState() == Qt.CheckState.Checked else 0
            self.engine.set_file_priority(rid, int(idx), priority)
            priority_item = self.files_table.item(item.row(), 3)
            if priority_item:
                priority_item.setText("Normal" if priority else "Omitido")
        except Exception as exc:
            self.error(str(exc))

    def _context_menu(self, point):
        if not self.table.itemAt(point):
            return
        menu = QMenu(self)
        menu.addAction("▶  Reanudar", self.resume_selected)
        menu.addAction("Ⅱ  Pausar", self.pause_selected)
        menu.addAction("▣  Abrir carpeta", self.open_folder)
        menu.addAction("⟳  Verificar datos", self.recheck_selected)
        menu.addAction("⇅  Límites de este torrent", self.change_torrent_limits)
        menu.addSeparator()
        menu.addAction("✕  Quitar", self.remove_selected)
        menu.exec(self.table.viewport().mapToGlobal(point))

    def add_file(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Importar torrents", str(Path.home() / "Downloads"), "Archivos Torrent (*.torrent)")
        if not files:
            return
        errors = []
        for path in files:
            try:
                self.engine.add_torrent_file(path)
            except Exception as exc:
                errors.append(f"{Path(path).name}: {exc}")
        self.change_filter("Todos")
        self.search.clear()
        self.refresh()
        if errors:
            self.error("\n".join(errors))
        elif files:
            latest = next(reversed(self.engine.records), None)
            if latest:
                self._select_by_id(latest)

    def add_magnet(self):
        dialog = AddMagnetDialog(self.engine.settings["download_dir"], self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            rid = self.engine.add_magnet(dialog.uri.text(), dialog.folder.text())
            self.change_filter("Todos")
            self.search.clear()
            self.refresh()
            self._select_by_id(rid)
        except Exception as exc:
            self.error(str(exc))

    def _select_by_id(self, rid: str):
        for i in range(self.table.rowCount()):
            if self.table.item(i, 0) and self.table.item(i, 0).data(Qt.ItemDataRole.UserRole) == rid:
                self.table.selectRow(i)
                self.update_details()
                break

    def _require_id(self):
        rid = self._selected_id()
        if not rid:
            QMessageBox.information(self, "Seleccionar descarga", "Primero selecciona un torrent de la biblioteca.")
        return rid

    def pause_selected(self):
        rid = self._require_id()
        if rid:
            try:
                self.engine.pause(rid)
                self.refresh()
            except Exception as exc:
                self.error(str(exc))

    def resume_selected(self):
        rid = self._require_id()
        if rid:
            try:
                self.engine.resume(rid)
                self.refresh()
            except Exception as exc:
                self.error(str(exc))

    def recheck_selected(self):
        rid = self._require_id()
        if rid:
            try:
                self.engine.recheck(rid)
                self.refresh()
            except Exception as exc:
                self.error(str(exc))

    def remove_selected(self):
        rid = self._require_id()
        if not rid:
            return
        name = self.cached_rows.get(rid, {}).get("name", "esta descarga")
        box = QMessageBox(self)
        box.setWindowTitle("Quitar torrent")
        box.setText(f"¿Qué deseas hacer con «{name}»?")
        box.setInformativeText("Quitar de la lista conserva los archivos en disco.")
        only = box.addButton("Solo quitar de la lista", QMessageBox.ButtonRole.AcceptRole)
        delete = box.addButton("Quitar y borrar archivos", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked not in (only, delete):
            return
        deleting = clicked == delete
        if deleting:
            confirm = QMessageBox.question(self, "Confirmar borrado",
                "Se solicitará al motor que borre los archivos de esta descarga. Esta acción no se puede deshacer.\n\n¿Continuar?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if confirm != QMessageBox.StandardButton.Yes:
                return
        try:
            self.engine.remove(rid, delete_data=deleting)
            self.refresh()
            self.update_details()
        except Exception as exc:
            self.error(str(exc))

    def open_folder(self):
        rid = self._require_id()
        if not rid:
            return
        folder = Path(self.engine.records[rid]["save_path"])
        if not folder.is_dir():
            self.error("Todavía no existe la carpeta de descarga.")
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def pick_settings_folder(self):
        result = QFileDialog.getExistingDirectory(self, "Carpeta predeterminada", self.target.text())
        if result:
            self.target.setText(result)

    def preview_theme(self, name: str):
        # El cambio es reversible hasta guardar; se aplica sin reiniciar el motor.
        self.setStyleSheet(theme_for(name))
        QApplication.instance().setProperty("apex_accent", accent_color(name))
        QApplication.instance().setProperty("apex_plot_accent", "#d7d7d7" if name == "Negro total" else accent_color(name))
        self.table.viewport().update()
        self.performance_graph.update()
        self.selected_graph.update()

    def save_settings(self):
        target = self.target.text().strip()
        if not target:
            self.error("Indica una carpeta predeterminada válida.")
            return
        if self.tray_enabled.isChecked() and self.tray is None:
            self.error("Windows no dispone de una bandeja del sistema accesible. No se puede activar segundo plano.")
            return
        try:
            self.engine.apply_settings({
                "download_dir": str(Path(target).expanduser().resolve()),
                "download_limit_kib": self.limit_down.value(),
                "upload_limit_kib": self.limit_up.value(),
                "connections_limit": self.connections.value(),
                "active_downloads": self.active_down.value(),
                "active_seeds": self.active_seeds.value(),
                "accent_theme": self.appearance_combo.currentText(),
                "listen_port": self.listen_port.value(),
                "network_mode": self.network_mode.currentData(),
                "auto_resume": self.autoresume.isChecked(),
                "dht": self.dht.isChecked(), "upnp": self.upnp.isChecked(),
                "background_enabled": self.tray_enabled.isChecked(),
                "notify_finished": self.notify_finished.isChecked(),
                "notify_problems": self.notify_problems.isChecked(),
                "schedule_enabled": self.schedule_enabled.isChecked(),
                "schedule_start_hour": self.schedule_start.currentIndex(),
                "schedule_end_hour": self.schedule_end.currentIndex(),
            })
            self.schedule_status.setText(schedule_caption(self.engine.settings))
            QMessageBox.information(self, "Configuración guardada", "Los cambios se guardaron correctamente.\nEl modo de red se aplica sin reinstalar nada. La reanudación automática se aplica al próximo inicio.")
        except Exception as exc:
            self.preview_theme(self.engine.settings.get("accent_theme", "Azul"))
            self.error(str(exc))

    def error(self, text: str):
        QMessageBox.critical(self, "Apex Torrent", str(text))

    def open_external(self, source: str):
        """Recibe una ruta .torrent o magnet; valida con el motor existente."""
        if not isinstance(source, str) or len(source) > 16384:
            self.error("Solicitud externa demasiado larga o inválida.")
            return
        try:
            if source.lower().startswith("magnet:?"):
                rid = self.engine.add_magnet(source)
            elif source.lower().endswith(".torrent"):
                rid = self.engine.add_torrent_file(source)
            else:
                self.error("Solo se admiten enlaces magnet y archivos .torrent.")
                return
            self.cached_rows = {rec["id"]: rec for rec in self.engine.rows()}
            self.navigate("Biblioteca")
            self.refresh_table()
            self._select_by_id(rid)
        except Exception as exc:
            self.error(str(exc))
            return
        self.show_from_tray()

    def _setup_tray(self):
        self.tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        try:
            self.tray = QSystemTrayIcon(self.windowIcon(), self)
            self.tray.setToolTip("Apex Torrent Ultimate")
            menu = QMenu(self)
            show_action = menu.addAction("Mostrar Apex Torrent")
            show_action.triggered.connect(self.show_from_tray)
            menu.addSeparator()
            quit_action = menu.addAction("Salir completamente")
            quit_action.triggered.connect(self.exit_completely)
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(lambda reason: self.show_from_tray()
                if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None)
            self.tray.show()
        except Exception as exc:
            logging.warning("Bandeja del sistema no disponible: %s", exc)
            self.tray = None

    def show_from_tray(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def exit_completely(self):
        self._exit_requested = True
        self.close()
        QApplication.instance().quit()

    def _notify_problem_rows(self, rows, now):
        """Notificaciones opt-in con anti-spam; no hace anuncios de red."""
        if not (self.engine.settings.get("notify_problems", False)
                and self.tray is not None and self.tray.isVisible()):
            return
        for row in rows:
            if row.get("state") != "Error" and int(row.get("idle_seconds", 0)) < 180:
                continue
            rid = row["id"]
            # Consultar solo las descargas inactivas, máximo cada ~10 s.
            if self._tick_count % 7:
                continue
            try:
                result = self.engine.diagnose_download(rid, row)
            except Exception:
                continue
            if result.severity not in ("warning", "error"):
                continue
            key = (rid, result.code)
            previous = self._problem_notifications.get(key, float("-inf"))
            if now - previous < 1800:
                continue
            self._problem_notifications[key] = now
            self.tray.showMessage("Apex Torrent · Revisión de descarga",
                                  result.title + "\n" + result.advice[:170],
                                  QSystemTrayIcon.MessageIcon.Warning, 5500)

    def _notify_completed(self, rows):
        completed = {r["id"] for r in rows if r.get("progress", 0) >= 1 and not r.get("error")}
        if self._seen_completed is None:
            self._seen_completed = completed
            return
        changes = completed - self._seen_completed
        self._seen_completed = completed
        if not (changes and self.tray and self.engine.settings.get("notify_finished", True)):
            return
        names = [r["name"] for r in rows if r["id"] in changes]
        self.tray.showMessage("Apex Torrent · Descarga completada", "\n".join(names[:2]),
                              QSystemTrayIcon.MessageIcon.Information, 4500)

    def refresh_security(self, row, rid):
        try:
            files = self.engine.files(rid)
            report = inspect_names(files)
            space = disk_estimate(row.get("save_path", ""), row.get("size", 0), row.get("done", 0))
            warnings = "\n".join("• " + name for name in report["executable_samples"])
            if space["available"] is None:
                space_text = "Espacio disponible no comprobado"
            else:
                space_text = f"Espacio libre: {readable_size(space['available'])} · Pendiente estimado: {readable_size(space['remaining'])}"
                if space["enough"] is False:
                    space_text += " · ADVERTENCIA: espacio posiblemente insuficiente"
            self.safety_summary.setText(
                f"Archivos conocidos: {report['files']} · Ejecutables/scripts potenciales: {report['executable_count']} · Archivos comprimidos: {report['archives']}\n"
                f"{space_text}\n" + ("Nombres a revisar (no se han abierto):\n" + warnings if warnings else "Sin extensiones ejecutables reconocidas en los metadatos disponibles."))
        except Exception as exc:
            self.safety_summary.setText("No se pudo realizar la comprobación: " + str(exc))

    def calculate_file_hash(self):
        rid, rec = self._selected()
        if not rid or not rec:
            self.error("Selecciona un torrent antes de calcular un hash.")
            return
        if rec.get("progress", 0) < 1:
            self.error("Espera a que se complete el torrent. El SHA-256 de un archivo todavía en descarga puede cambiar.")
            return
        root = rec.get("save_path", "")
        file_name, _ = QFileDialog.getOpenFileName(self, "Archivo ya descargado para verificar SHA-256", root)
        if not file_name:
            return
        try:
            path = safe_download_path(root, os.path.relpath(file_name, root))
        except (ValueError, OSError) as exc:
            self.error(str(exc))
            return
        self.hash_result.setText("Calculando SHA-256... (el archivo no se modifica)")
        self._hash_current = str(path)
        job = _HashJob(path)
        self._hash_workers.append(job)  # mantener señales Python vivas hasta terminar
        job.signals.finished.connect(self._on_hash_finished, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(job)

    @Slot(str, str)
    def _on_hash_finished(self, filename, digest):
        if filename == self._hash_current:
            self.hash_result.setText(digest)
            if not digest.startswith("ERROR:"):
                self.hash_result.setToolTip(filename)
        self._hash_workers = [job for job in self._hash_workers if str(job.path) != filename]

    def closeEvent(self, event):
        if (not self._exit_requested and self.engine.settings.get("background_enabled", False)
                and self.tray is not None and self.tray.isVisible()):
            self.hide()
            event.ignore()
            if not self._tray_tip_shown:
                self.tray.showMessage("Apex Torrent", "Las transferencias continúan. Usa «Salir» desde la bandeja para cerrar el programa.", QSystemTrayIcon.MessageIcon.Information, 3500)
                self._tray_tip_shown = True
            return
        if self._layout_save_timer.isActive():
            self._layout_save_timer.stop()
        self._save_library_layout()
        self.timer.stop()
        self.resume_timer.stop()
        try:
            self.engine.close(seconds=3.0)
        except Exception as exc:
            print("Error al cerrar Apex Torrent:", exc, file=sys.stderr)
        event.accept()
        QApplication.instance().quit()
