"""Apex Torrent Black Edition: temas de líneas intercambiables en caliente.

El negro total elimina los acentos decorativos; las etiquetas siempre mantienen
contraste alto para que el modo permanezca utilizable.
"""
from string import Template

THEMES = {
    "Rojo": {"accent": "#ff3d5b", "accent_hover": "#ff8495", "selection": "#40121e"},
    "Azul": {"accent": "#35aaff", "accent_hover": "#88d4ff", "selection": "#0d2846"},
    "Morado": {"accent": "#b576ff", "accent_hover": "#d3aaff", "selection": "#29183e"},
    "Blanco": {"accent": "#e5e7eb", "accent_hover": "#ffffff", "selection": "#282828"},
    "Verde": {"accent": "#24df96", "accent_hover": "#79ffd0", "selection": "#10382c"},
    "Negro total": {"accent": "#090909", "accent_hover": "#363636", "selection": "#191919"},
}
DEFAULT_THEME = "Azul"


def accent_color(theme: str) -> str:
    """Color de línea para cada tema, sin valores no verificados del usuario."""
    return THEMES.get(theme, THEMES[DEFAULT_THEME])["accent"]


def theme_for(theme: str) -> str:
    options = THEMES.get(theme, THEMES[DEFAULT_THEME])
    is_black = theme == "Negro total"
    # Aun en Negro total los controles deben distinguirse del fondo puro.
    values = {
        "accent": options["accent"], "accent_hover": options["accent_hover"],
        "selection": options["selection"], "root": "#000000", "sidebar": "#030303",
        "panel": "#070707", "panel_alt": "#101010", "inset": "#040404",
        "border": "#080808" if is_black else options["accent"],
        "subtle": "#111111" if is_black else "#242424",
        "text": "#f3f4f6", "muted": "#a0a4ae",
        "action_bg": "#131313", "action_hover": "#222222",
        "accent_text": "#f6f7f9" if is_black else options["accent_hover"],
        "primary_bg": "#252525" if is_black else options["accent"],
        "primary_fg": "#ffffff" if is_black else "#030303",
    }
    return Template(_CSS).substitute(values)


COLORS = {"bg": "#000000", "panel": "#070707", "panel_alt": "#101010",
          "line": accent_color(DEFAULT_THEME), "primary": accent_color(DEFAULT_THEME),
          "secondary": "#b576ff", "text": "#f3f4f6", "muted": "#a0a4ae",
          "danger": "#ff718b"}

_CSS = """
QWidget { color:$text; font-family:'Segoe UI'; font-size:12px; }
QMainWindow, QWidget#appRoot, QWidget#page, QWidget#scrollContent { background:$root; }
QLabel { background:transparent; border:0; }
QWidget#tabContents { background:$panel; }
QFrame#sidebar { background:$sidebar; border-right:1px solid $border; }
QFrame#brandPlate { background:$panel; border:1px solid $border; border-radius:11px; }
QLabel#brand { color:$text; font-size:16px; font-weight:800; }
QLabel#edition { color:$accent_text; font-size:10px; font-weight:700; }
QLabel#logoImage { background:transparent; }
QLabel#navSection { color:$muted; font-size:10px; font-weight:700; padding:9px 9px 4px 9px; }
QScrollArea#navScroll, QWidget#navBody { background:transparent; border:0; }
QFrame#systemStatus { background:$panel_alt; border:1px solid $border; border-radius:10px; }
QLabel#connectionTitle { color:#49e8bb; font-size:11px; font-weight:800; }
QLabel#connectionSub, QLabel#copyright, QLabel#muted, QLabel#hint { color:$muted; }
QLabel#copyright { font-size:9px; }
QLabel#headerTitle { color:$text; font-size:25px; font-weight:800; }
QFrame#stat { background:$panel; border:1px solid $border; border-radius:10px; }
QLabel#statValue { color:$text; font-size:22px; font-weight:800; }
QLabel#statLabel { color:$muted; font-size:10px; font-weight:700; }
QLabel#statGlyph { color:$accent_text; font-size:17px; font-weight:800; }
QFrame#detail { background:$panel; border:1px solid $border; border-radius:11px; }
QFrame#headBox { background:transparent; }
QFrame#errorBanner { background:#2a1018; border:1px solid #9c3554; border-radius:9px; }
QLabel#errorLabel { color:#ffdbe5; font-weight:600; }
QFrame#insight { background:$panel_alt; border:1px solid $subtle; border-radius:9px; }
QLabel#insightText { color:$text; font-size:12px; }
QPushButton { background:$action_bg; color:$text; border:1px solid $subtle;
 border-radius:8px; padding:8px 12px; font-size:12px; font-weight:650; }
QPushButton:hover { background:$action_hover; border-color:$border; }
QPushButton:pressed { background:$selection; }
QPushButton:disabled { color:#606060; background:#090909; border-color:#101010; }
QPushButton#primary { background:$primary_bg; color:$primary_fg; border:1px solid $accent_hover; }
QPushButton#primary:hover { background:$accent_hover; color:#000000; }
QPushButton#danger { color:#ff92a5; background:#1c0b0e; border:1px solid #7b293f; }
QPushButton#danger:hover { background:#4b1824; }
QPushButton#tools { border-color:$border; }
QPushButton#nav { background:transparent; border:1px solid transparent; border-left:3px solid transparent;
 border-radius:7px; text-align:left; padding:8px 10px; color:#c3c7cf; }
QPushButton#nav:hover { color:$text; background:$action_hover; border-left:3px solid $border; }
QPushButton#nav:checked { color:$text; background:$selection; border-left:3px solid $accent_hover; }
QPushButton#compactButton { padding:7px 10px; color:$muted; }
QPushButton#filter { background:$action_bg; color:#bfc3c9; border:1px solid $subtle; padding:7px 11px; }
QPushButton#filter:checked { background:$selection; color:$text; border-color:$border; }
QComboBox, QLineEdit, QSpinBox { background:$inset; color:$text; border:1px solid $subtle;
 border-radius:7px; padding:8px 10px; selection-background-color:$selection; }
QComboBox { min-width:145px; }
QLineEdit:focus, QSpinBox:focus, QComboBox:focus { border-color:$accent_hover; }
QComboBox QAbstractItemView { background:$panel_alt; selection-background-color:$selection; color:$text; }
QSpinBox { min-height:24px; }
QSpinBox::up-button, QSpinBox::down-button { background:$action_hover; width:20px; }
QPlainTextEdit { background:$inset; color:$text; font-family:Consolas; font-size:11px;
 border:1px solid $subtle; border-radius:8px; padding:10px; }
QTableWidget { background:$panel; alternate-background-color:$panel_alt; border:1px solid $subtle;
 border-radius:9px; gridline-color:transparent; selection-background-color:$selection;
 selection-color:$text; outline:none; }
QTableWidget::item { padding:6px; border-bottom:1px solid $subtle; }
QTableWidget::item:selected { background:$selection; }
QHeaderView::section { color:#d5d7df; background:$panel_alt; border:0; border-bottom:1px solid $border;
 padding:8px 5px; font-size:10px; font-weight:750; }
QTabWidget::pane { border:0; background:$panel; }
QTabBar::tab { color:$muted; background:$panel_alt; border:0; border-bottom:2px solid transparent; padding:10px 15px; }
QTabBar::tab:selected { color:$text; border-bottom:2px solid $accent_hover; }
QTabBar::tab:hover:!selected { color:$text; background:$action_hover; }
QScrollArea#pageScroll { border:0; background:$root; }
QScrollBar:vertical { width:9px; background:$panel; }
QScrollBar::handle:vertical { background:#353535; border-radius:4px; min-height:25px; }
QScrollBar:horizontal { height:9px; background:$panel; }
QScrollBar::handle:horizontal { background:#353535; border-radius:4px; min-width:25px; }
QScrollBar::add-line, QScrollBar::sub-line { width:0; height:0; }
QSplitter::handle { background:#202020; height:10px; border-top:1px solid $border; }
QSplitter::handle:hover { background:$selection; }
QSplitter::handle:pressed { background:$accent; }
QCheckBox { background:transparent; color:$text; padding:6px 0; spacing:9px; }
QCheckBox::indicator { width:16px; height:16px; }
QCheckBox::indicator:checked { background:$accent_hover; border:1px solid $border; border-radius:4px; }
QCheckBox::indicator:unchecked { background:$panel_alt; border:1px solid #666; border-radius:4px; }
QDialog, QMessageBox { background:$panel; }
QMenu { background:$panel_alt; color:$text; border:1px solid $border; padding:5px; }
QMenu::item { padding:8px 22px; }
QMenu::item:selected { background:$selection; color:$text; }
QToolTip { background:$panel_alt; color:$text; border:1px solid $border; }
"""

STYLE = theme_for(DEFAULT_THEME)

# Ultimate Interface 2.0: estados vacíos y legibilidad del panel de archivos.
# Se aplica como adición final, respetando los seis colores del tema.
_PREMIUM_CSS = """
QFrame#emptyPanel { background:#060606; border:1px solid $subtle; border-radius:10px; }
QLabel#emptyTitle { color:$text; font-size:18px; font-weight:800; }
QFrame#stat { border-radius:12px; }
QFrame#detail { border-radius:12px; }
QTableWidget::item:hover { background:$action_hover; }
QTabBar::tab { min-height:18px; }
QLineEdit, QComboBox, QSpinBox { min-height:25px; }
QTableWidget QScrollBar:horizontal { height:8px; }
QTableWidget QScrollBar:vertical { width:8px; }
"""
_legacy_theme_for = theme_for

def theme_for(theme: str) -> str:
    options = THEMES.get(theme, THEMES[DEFAULT_THEME])
    is_black = theme == "Negro total"
    values = {"text":"#f3f4f6", "subtle":"#181818" if is_black else "#292929",
              "action_hover":"#222222"}
    return _legacy_theme_for(theme) + "\n" + Template(_PREMIUM_CSS).substitute(values)

STYLE = theme_for(DEFAULT_THEME)
