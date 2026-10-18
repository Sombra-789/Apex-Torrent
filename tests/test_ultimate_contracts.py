"""Verifica límites de integración de la fase 1 sin suponer Qt instalado."""
import ast
from pathlib import Path
import tempfile
import unittest
from test_engine_mock import engine, Store

ROOT = Path(__file__).resolve().parents[1]


class UltimateContracts(unittest.TestCase):
    def test_no_runtime_reset_for_tray_preference(self):
        with tempfile.TemporaryDirectory() as temp:
            item = engine.TorrentEngine(Store(Path(temp)))
            captured = []
            prev = item.session.apply_settings
            def spy(x):
                captured.append(x)
                return prev(x)
            item.session.apply_settings = spy
            item.apply_settings({'background_enabled': True, 'notify_finished': False})
            self.assertTrue(item.settings['background_enabled'])
            self.assertFalse(item.store.load_settings()['notify_finished'])
            self.assertEqual(captured, [])

    def test_legacy_auto_port_unchanged(self):
        with tempfile.TemporaryDirectory() as temp:
            item = engine.TorrentEngine(Store(Path(temp)))
            item.apply_settings({'network_mode':'compatibility'})
            self.assertEqual(item.session.options['listen_interfaces'], '0.0.0.0:0,[::]:0')

    def test_new_ui_ast_and_quit_control(self):
        ui = (ROOT/'app/ui.py').read_text('utf-8')
        ast.parse(ui)
        self.assertIn('def exit_completely', ui)
        self.assertIn('self.engine.close(seconds=3.0)', ui)
        self.assertIn('self._exit_requested', ui)
        self.assertIn('QApplication.instance().quit()', ui)

    def test_windows_registration_is_optional_and_current_user_only(self):
        text = (ROOT/'scripts/registrar_asociaciones.ps1').read_text('utf-8')
        self.assertIn('HKCU:', text)
        self.assertNotIn('HKLM:', text)
        self.assertNotIn('UserChoice', text.split('try {')[-1])
        self.assertTrue((ROOT/'QUITAR_ASOCIACIONES_WINDOWS.bat').is_file())

    def test_local_open_ipc_revalidates(self):
        main = (ROOT/'app/main.py').read_text('utf-8')
        ui = (ROOT/'app/ui.py').read_text('utf-8')
        self.assertIn('QLocalServer', main)
        self.assertIn('if len(payload) <= 32768', main)
        self.assertIn('self.engine.add_torrent_file(source)', ui)
        self.assertIn('self.engine.add_magnet(source)', ui)

if __name__ == '__main__':
    unittest.main()
