"""Pruebas sin Qt para assets y contratos del rediseño cyberpunk."""
import ast
from pathlib import Path
import re
import struct
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "app"

class CyberpunkUiTests(unittest.TestCase):
    def test_source_is_valid_python(self):
        for name in ("ui.py", "cyber_theme.py", "main.py", "engine.py"):
            ast.parse((SRC / name).read_text(encoding="utf-8"))

    def test_version_is_consistent(self):
        state = (SRC / "state.py").read_text(encoding="utf-8")
        self.assertIn('VERSION = "1.4.0-alpha.1"', state)
        self.assertIn('ApexTorrent/1.4.0-alpha.1', (SRC / "engine.py").read_text(encoding="utf-8"))

    def test_sidebar_is_scrollable_and_fixed_sections_exist(self):
        source = (SRC / "ui.py").read_text(encoding="utf-8")
        self.assertIn('nav_scroll = QScrollArea()', source)
        self.assertIn('left.addWidget(nav_scroll, 1)', source)
        self.assertIn('left.addWidget(status_box)', source)
        self.assertIn('left.addWidget(brand_plate)', source)
        self.assertIn('tools_menu.addAction', source)
        self.assertNotIn('sidebar.setFixedWidth(235)', source)

    def test_assets_have_valid_file_signatures(self):
        png = (SRC / "assets/apex-torrent-mark.png").read_bytes()
        ico = (SRC / "assets/apex-torrent.ico").read_bytes()
        svg = (SRC / "assets/apex-torrent-mark.svg").read_text(encoding="utf-8")
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(struct.unpack_from(">I", png, 16)[0], 512)
        self.assertEqual(ico[:4], b"\x00\x00\x01\x00")
        self.assertIn('<svg', svg)
        self.assertIn('#', svg)

    def test_theme_is_used_and_neon_colors_defined(self):
        ui = (SRC / "ui.py").read_text(encoding="utf-8")
        theme = (SRC / "cyber_theme.py").read_text(encoding="utf-8")
        self.assertIn('from cyber_theme import STYLE, COLORS', ui)
        self.assertIn('"Azul"', theme)
        self.assertIn('"Morado"', theme)
        self.assertIn('QPushButton#nav:checked', theme)

    def test_auto_port_default_unchanged(self):
        text = (SRC / "state.py").read_text(encoding="utf-8")
        self.assertIn('"listen_port": 0', text)

if __name__ == "__main__":
    unittest.main()
