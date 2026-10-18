"""Pruebas de motor 1.2 con la simulación libtorrent ya existente."""
import tempfile
import unittest
from pathlib import Path
from test_engine_mock import engine, Store


class BlackEngineTests(unittest.TestCase):
    def test_visual_change_does_not_rebind_session(self):
        with tempfile.TemporaryDirectory() as folder:
            app = engine.TorrentEngine(Store(Path(folder)))
            apply_calls = []
            original = app.session.apply_settings
            def intercept(settings):
                apply_calls.append(settings)
                return original(settings)
            app.session.apply_settings = intercept
            app.apply_settings({"accent_theme": "Rojo"})
            self.assertEqual(app.settings["accent_theme"], "Rojo")
            self.assertEqual(app.store.load_settings()["accent_theme"], "Rojo")
            self.assertEqual(apply_calls, [])

    def test_runtime_queue_limits_and_auto_port(self):
        with tempfile.TemporaryDirectory() as folder:
            app = engine.TorrentEngine(Store(Path(folder)))
            app.apply_settings({"active_downloads": 7, "active_seeds": 5})
            self.assertEqual(app.session.options["active_downloads"], 7)
            self.assertEqual(app.session.options["active_seeds"], 5)
            self.assertEqual(app.session.options["active_limit"], 12)
            self.assertEqual(app.session.options['listen_interfaces'], engine.interface_settings('route',0,app._route)['listen_interfaces'])

    def test_invalid_theme_and_queue_do_not_mutate_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            app = engine.TorrentEngine(Store(Path(folder)))
            baseline = dict(app.settings)
            for payload in ({"accent_theme": "a; background: green"}, {"active_downloads": 0},
                            {"active_seeds": 51}, {"connections_limit": 99999}):
                with self.assertRaises(engine.EngineError):
                    app.apply_settings(payload)
                self.assertEqual(app.settings, baseline)
