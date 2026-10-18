"""Tests específicos de Black Edition que no necesitan Qt ni Windows."""
import ast
from pathlib import Path
import struct
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
from cyber_theme import THEMES, accent_color, theme_for
from performance import profile_settings
from state import Store, initial_settings


class BlackEditionTests(unittest.TestCase):
    def test_palette_has_six_user_choices(self):
        self.assertEqual(tuple(THEMES), ('Rojo','Azul','Morado','Blanco','Verde','Negro total'))
        self.assertEqual(initial_settings()['accent_theme'], 'Azul')

    def test_black_root_is_true_black_and_selection_legible(self):
        for name in THEMES:
            css=theme_for(name)
            self.assertIn('background:#000000;',css)
            self.assertIn('QPushButton#nav:checked',css)
            self.assertNotIn('$accent',css)
        self.assertIn('color:#f3f4f6',theme_for('Negro total'))
        self.assertIn('border:1px solid #080808',theme_for('Negro total'))

    def test_visual_switch_cannot_generate_untrusted_css(self):
        self.assertEqual(accent_color('no existe'),accent_color('Azul'))

    def test_active_queues_are_bounded_and_profiles_distinct(self):
        for profile in ('Equilibrado','Máximo rendimiento','Red limitada'):
            data=profile_settings(profile)
            self.assertGreaterEqual(data['active_downloads'],1)
            self.assertGreaterEqual(data['active_seeds'],1)
        self.assertNotEqual(profile_settings('Red limitada')['active_downloads'],
                            profile_settings('Máximo rendimiento')['active_downloads'])

    def test_shortcut_and_taskbar_identity(self):
        script=(ROOT/'scripts/crear_acceso_directo.ps1').read_text(encoding='utf-8')
        main=(ROOT/'app/main.py').read_text(encoding='utf-8')
        self.assertIn('WScript.Shell',script)
        self.assertIn('pythonw.exe',script)
        self.assertIn('Apex Torrent.lnk',script)
        self.assertIn('SetCurrentProcessExplicitAppUserModelID',main)

    def test_new_icon_has_windows_ico_and_multi_sizes(self):
        data=(ROOT/'app/assets/apex-torrent.ico').read_bytes()
        self.assertEqual(data[:4],b'\x00\x00\x01\x00')
        count=struct.unpack_from('<H',data,4)[0]
        self.assertGreaterEqual(count,6)

    def test_assets_path_works_when_unbundled(self):
        from assets_util import asset_path
        self.assertTrue(asset_path('apex-torrent.ico').is_file())

    def test_python_syntax(self):
        for path in (ROOT/'app').glob('*.py'):
            ast.parse(path.read_text(encoding='utf-8'))

if __name__=='__main__':
    unittest.main()
