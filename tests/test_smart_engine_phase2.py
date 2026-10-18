"""Fase 2: matemáticas del motor, privacidad, persistencia y regresión sin Qt/red."""
import ast
from contextlib import closing
import sqlite3
import tempfile
import unittest
from pathlib import Path

from test_engine_mock import Store, engine
from smart_engine import (effective_upload_limit_kib, smart_upload_report,
                          tracker_diagnosis, classify_tracker_error, swarm_hint)
from monitor import PerformanceJournal, ProcessSampler

ROOT = Path(__file__).resolve().parents[1]


class SmartEngineTests(unittest.TestCase):
    def test_disabled_never_changes_manual_limit(self):
        self.assertEqual(effective_upload_limit_kib({'upload_limit_kib': 125,
            'smart_engine_enabled': False, 'upload_capacity_mbps': 10}), 125)
        self.assertEqual(effective_upload_limit_kib({'smart_engine_enabled': False}), 0)

    def test_opt_in_reserves_capacity_in_bytes_not_bits(self):
        settings = {'smart_engine_enabled': True, 'upload_capacity_mbps': 20,
                    'smart_upload_percent': 80, 'upload_limit_kib': 0}
        self.assertEqual(effective_upload_limit_kib(settings), round(20_000_000 / 8 / 1024 * .8))
        self.assertIn('80%', smart_upload_report(settings))

    def test_smart_never_overrides_stricter_manual_limit(self):
        settings = {'smart_engine_enabled': True, 'upload_capacity_mbps': 100,
                    'smart_upload_percent': 80, 'upload_limit_kib': 75}
        self.assertEqual(effective_upload_limit_kib(settings), 75)

    def test_smart_rejects_unknown_capacity(self):
        with self.assertRaises(ValueError):
            effective_upload_limit_kib({'smart_engine_enabled': True, 'upload_capacity_mbps': 0})

    def test_engine_opt_in_and_fallback_are_persisted(self):
        with tempfile.TemporaryDirectory() as folder:
            eng = engine.TorrentEngine(Store(Path(folder)))
            self.assertEqual(eng.session.options['upload_rate_limit'], 0)
            eng.apply_settings({'smart_engine_enabled': True, 'upload_capacity_mbps': 20,
                                'smart_upload_percent': 80})
            self.assertEqual(eng.session.options['upload_rate_limit'],
                             effective_upload_limit_kib(eng.settings) * 1024)
            self.assertEqual(eng.session.options['listen_interfaces'], engine.interface_settings('route',0,eng._route)['listen_interfaces'])
            self.assertTrue(eng.store.load_settings()['smart_engine_enabled'])
            eng.apply_settings({'smart_engine_enabled': False})
            self.assertEqual(eng.session.options['upload_rate_limit'], 0)

    def test_no_changes_after_invalid_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            eng = engine.TorrentEngine(Store(Path(folder)))
            with self.assertRaises(engine.EngineError):
                eng.apply_settings({'smart_engine_enabled': True, 'upload_capacity_mbps': 0})
            self.assertFalse(eng.settings['smart_engine_enabled'])
            self.assertFalse(eng.store.load_settings()['smart_engine_enabled'])

    def test_tracker_counts_pending_separately(self):
        entries = [
            {'url':'udp://one/announce','state':'Error','message':'timed out'},
            {'url':'udp://two/announce','state':'Error','message':'Host desconocido'},
            {'url':'https://three/announce','state':'Anunciando','message':'sending announce'},
            {'url':'https://four/announce','state':'Respondió','message':'3 pares'},
        ]
        data = tracker_diagnosis(entries)
        self.assertEqual(data['counts']['errores'], 2)
        self.assertEqual(data['counts']['respondieron'], 1)
        self.assertEqual(data['counts']['anunciando'], 1)
        self.assertIn(('Tiempo de espera', 1), data['causes'])

    def test_tracker_interface_problem(self):
        self.assertEqual(classify_tracker_error('[::1] skipping tracker announce (unreachable)'),
                         'Interfaz / red no accesible')
        self.assertEqual(classify_tracker_error('Se ha intentado una operación de socket en una red no accesible'),
                         'Interfaz / red no accesible')

    def test_swarm_hint_is_cautious_about_seed_count(self):
        hint = swarm_hint({'progress': 0, 'seeds': 0, 'peers': 3, 'down': 0})
        self.assertIn('Podría', hint)
        self.assertNotIn('muerto', hint)


class MonitorTests(unittest.TestCase):
    def test_local_history_and_24hour_summary(self):
        with tempfile.TemporaryDirectory() as folder:
            hist = PerformanceJournal(Path(folder))
            hist.append(1024, 4096, 4, 2.4, 123456, timestamp=1000000)
            hist.append(3072, 2048, 7, 4.2, 456789, timestamp=1000015)
            self.assertEqual(hist.summary(24, 1000020),
                             {'count':2,'peak_down':3072,'peak_up':4096,
                              'average_down':2048,'average_up':3072})
            self.assertEqual(PerformanceJournal(Path(folder)).summary(24, 1000020)['count'], 2)

    def test_no_personal_identifiers_stored(self):
        with tempfile.TemporaryDirectory() as folder:
            journal = PerformanceJournal(Path(folder))
            with closing(sqlite3.connect(journal.path)) as conn:
                columns = [r[1] for r in conn.execute('PRAGMA table_info(samples)')]
            for sensitive in ('torrent', 'magnet', 'ip', 'tracker', 'file', 'url'):
                self.assertNotIn(sensitive, columns)

    def test_old_samples_get_removed(self):
        with tempfile.TemporaryDirectory() as folder:
            journal = PerformanceJournal(Path(folder))
            journal.append(99, 0, 0, None, None, timestamp=100)
            journal.append(20, 0, 0, None, None, timestamp=1_000_000)
            # la primera escritura purga; otras lo hacen periódicamente.
            # Aumentar hasta alcanzar ciclo 240 de poda.
            for i in range(239):
                journal.append(21, 0, 0, None, None, timestamp=1_000_015 + i * 15)
            with closing(sqlite3.connect(journal.path)) as conn:
                oldest = conn.execute('SELECT min(timestamp) FROM samples').fetchone()[0]
            self.assertGreaterEqual(oldest, 1_000_000)

    def test_invalid_hours_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            journal = PerformanceJournal(Path(folder))
            with self.assertRaises(ValueError): journal.summary(0)
            with self.assertRaises(ValueError): journal.summary(169)

    def test_negative_rates_cannot_be_saved(self):
        with tempfile.TemporaryDirectory() as folder:
            journal = PerformanceJournal(Path(folder))
            journal.append(-1, -100, -2, -9, -500, timestamp=200)
            with closing(sqlite3.connect(journal.path)) as conn:
                got = conn.execute('SELECT download_bps, upload_bps, peers, cpu_pct, rss_bytes FROM samples').fetchone()
            self.assertEqual(got, (0, 0, 0, 0.0, 0))

    def test_monitor_does_not_require_optional_psutil(self):
        data = ProcessSampler().read()
        self.assertIn('cpu_percent', data)
        self.assertIn('rss_bytes', data)

    def test_ui_has_real_metrics_and_no_artificial_downloads(self):
        code = (ROOT/'app/ui.py').read_text('utf-8')
        ast.parse(code)
        self.assertIn('self._sample_monitor(down, up', code)
        self.assertIn('self.engine.apply_settings(config)', code)
        self.assertIn('self.tracker_insight', code)
        self.assertIn('self._journal.append(down, up, peers, cpu, rss)', code)


if __name__ == '__main__':
    unittest.main()
