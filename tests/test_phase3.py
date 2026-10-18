"""Fase 3: test de lógica de programación, persistencia, archivos y contratos Qt."""
import ast
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from test_engine_mock import Store, engine
from scheduler import hour_allowed, schedule_allowed, schedule_caption
from state import VERSION, initial_settings

ROOT = Path(__file__).resolve().parents[1]


class ScheduleLogic(unittest.TestCase):
    def test_daytime(self):
        self.assertFalse(hour_allowed(8, 18, 7))
        self.assertTrue(hour_allowed(8, 18, 8))
        self.assertTrue(hour_allowed(8, 18, 17))
        self.assertFalse(hour_allowed(8, 18, 18))

    def test_cross_midnight(self):
        self.assertTrue(hour_allowed(23, 4, 23))
        self.assertTrue(hour_allowed(23, 4, 2))
        self.assertFalse(hour_allowed(23, 4, 13))
        self.assertFalse(hour_allowed(23, 4, 4))

    def test_full_day_and_validation(self):
        for hour in range(24):
            self.assertTrue(hour_allowed(0, 0, hour))
        with self.assertRaises(ValueError):
            hour_allowed(-1, 0, 20)
        with self.assertRaises(ValueError):
            hour_allowed(0, 25, 20)
        with self.assertRaises(ValueError):
            hour_allowed(8, 11, True)

    def test_disabled_does_not_gate(self):
        self.assertTrue(schedule_allowed(initial_settings(), datetime(2026, 10, 16, 2)))
        self.assertIn('desactivado', schedule_caption(initial_settings()))

    def test_enabled_gate_and_caption(self):
        s = {**initial_settings(), 'schedule_enabled': True,
             'schedule_start_hour': 21, 'schedule_end_hour': 4}
        self.assertTrue(schedule_allowed(s, datetime(2026, 10, 16, 23)))
        self.assertFalse(schedule_allowed(s, datetime(2026, 10, 16, 15)))
        self.assertIn('Fuera de horario', schedule_caption(s, datetime(2026, 10, 16, 15)))


class EngineSchedule(unittest.TestCase):
    def test_schedule_opt_in_persists_and_refuses_manual_resume_outside(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d))
            app = engine.TorrentEngine(store)
            rid = app.add_magnet('magnet:?xt=urn:btih:11112222')
            app.apply_settings({'schedule_enabled': True, 'schedule_start_hour': 8,
                                'schedule_end_hour': 18})
            app.apply_schedule(datetime(2026, 10, 16, 2))
            self.assertTrue(app.handles[rid].paused)
            self.assertTrue(app.records[rid]['schedule_paused'])
            self.assertFalse(app.records[rid]['paused'])
            self.assertEqual(app.rows()[0]['state'], 'Fuera de horario')
            self.assertTrue(store.load_records()[0]['schedule_paused'])
            # Independiente del reloj real: fuerza configuración fuera de horario.
            app.apply_settings({'schedule_start_hour': 23, 'schedule_end_hour': 23})
            self.assertFalse(app.records[rid]['schedule_paused'])

    def test_schedule_does_not_resume_manual_pause(self):
        with tempfile.TemporaryDirectory() as d:
            app = engine.TorrentEngine(Store(Path(d)))
            rid = app.add_magnet('magnet:?xt=urn:btih:33334444')
            app.pause(rid)
            app.apply_settings({'schedule_enabled': True, 'schedule_start_hour': 8,
                                'schedule_end_hour': 18})
            app.apply_schedule(datetime(2026, 10, 16, 2))
            app.apply_schedule(datetime(2026, 10, 16, 10))
            self.assertTrue(app.handles[rid].paused)
            self.assertTrue(app.records[rid]['paused'])
            self.assertFalse(app.records[rid].get('schedule_paused', False))

    def test_seeding_is_not_paused(self):
        with tempfile.TemporaryDirectory() as d:
            app = engine.TorrentEngine(Store(Path(d)))
            rid = app.add_magnet('magnet:?xt=urn:btih:55556666')
            handle = app.handles[rid]
            original = handle.status
            def seeding():
                result = original()
                result.is_seeding = True
                result.progress = 1.0
                return result
            handle.status = seeding
            app.apply_settings({'schedule_enabled': True, 'schedule_start_hour': 8,
                                'schedule_end_hour': 18})
            app.apply_schedule(datetime(2026, 10, 16, 2))
            self.assertFalse(handle.paused)
            self.assertFalse(app.records[rid].get('schedule_paused', False))

    def test_invalid_time_rejected_before_save(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d))
            app = engine.TorrentEngine(store)
            with self.assertRaises(engine.EngineError):
                app.apply_settings({'schedule_start_hour': 24})
            self.assertEqual(store.load_settings()['schedule_start_hour'], 0)

    def test_opt_out_releases_schedule_pause(self):
        with tempfile.TemporaryDirectory() as d:
            app = engine.TorrentEngine(Store(Path(d)))
            rid = app.add_magnet('magnet:?xt=urn:btih:77778888')
            app.apply_settings({'schedule_enabled': True, 'schedule_start_hour': 8,
                                'schedule_end_hour': 18})
            app.apply_schedule(datetime(2026, 10, 16, 2))
            app.apply_settings({'schedule_enabled': False})
            self.assertFalse(app.handles[rid].paused)
            self.assertFalse(app.records[rid]['schedule_paused'])


class BulkPriority(unittest.TestCase):
    def test_bulk_file_priority_applies_after_full_validation(self):
        with tempfile.TemporaryDirectory() as d:
            app = engine.TorrentEngine(Store(Path(d)))
            rid = app.add_magnet('magnet:?xt=urn:btih:12345678')
            h = app.handles[rid]
            h.get_file_priorities = lambda: [4, 4, 4]
            writes = []
            h.file_priority = lambda index, value: writes.append((index, value))
            with self.assertRaises(engine.EngineError):
                app.set_file_priorities(rid, {0: 7, 3: 0})
            self.assertEqual(writes, [])
            app.set_file_priorities(rid, {0: 7, 2: 0})
            self.assertEqual(writes, [(0, 7), (2, 0)])

    def test_invalid_priority_never_mutates(self):
        with tempfile.TemporaryDirectory() as d:
            app = engine.TorrentEngine(Store(Path(d)))
            rid = app.add_magnet('magnet:?xt=urn:btih:99990000')
            with self.assertRaises(engine.EngineError):
                app.set_file_priorities(rid, {0: 8})
            with self.assertRaises(engine.EngineError):
                app.set_file_priority(rid, 0, 8)


class UIContracts(unittest.TestCase):
    def test_unchanged_lib_and_version(self):
        self.assertEqual(VERSION, '1.3.8')
        source = (ROOT/'app/engine.py').read_text(encoding='utf-8')
        self.assertIn('0.0.0.0:', source)
        self.assertIn('listen_port", 0', source)

    def test_ui_contains_real_controls_and_compiles(self):
        ui = (ROOT/'app/ui.py').read_text(encoding='utf-8')
        ast.parse(ui)
        for feature in ('library_stack', 'emptyPanel', 'schedule_enabled',
                        'tracker_filter', '_set_file_priorities_bulk', 'smart_capacity'):
            self.assertIn(feature, ui)
        theme = (ROOT/'app/cyber_theme.py').read_text(encoding='utf-8')
        self.assertIn('QLabel#emptyTitle', theme)


if __name__ == '__main__':
    unittest.main()
