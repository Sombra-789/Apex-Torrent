"""Fase 4: explicación de fallos y mejoras del motor sin tráfico real."""
import ast
import tempfile
import unittest
from pathlib import Path
from test_engine_mock import Store, engine
from diagnosis import diagnose, tracker_counts
from state import VERSION, initial_settings


class DownloadDiagnoses(unittest.TestCase):
    def setUp(self):
        self.row = dict(state='Esperando pares', peers=0, seeds=0, down=0, progress=0,
                        idle_seconds=300, paused=False, error='')

    def test_network_report_is_cautious(self):
        r = diagnose(self.row)
        self.assertEqual(r.code, 'no_seed_observed')
        self.assertIn('No demuestra', r.advice)

    def test_tracker_failures_and_dht_hint(self):
        r = diagnose(self.row, [{'url':'udp://a:123/a', 'state':'Error'}])
        self.assertEqual(r.code,'trackers_failed')
        self.assertIn('DHT',r.advice)

    def test_partial_trackers(self):
        r = diagnose(self.row, [{'url':'udp://a:123/a','state':'Error'},
                                {'url':'udp://b:123/a','state':'Anunciando'}])
        self.assertEqual(r.code,'tracker_partial')

    def test_tracking_success_not_dead(self):
        r = diagnose(self.row, [{'url':'https://a/announce','state':'Respondió'}])
        self.assertEqual(r.code,'no_seed_observed')

    def test_active_transfer_wins_over_trackers(self):
        r = diagnose({**self.row,'down':4000}, [{'url':'udp://a/announce','state':'Error'}])
        self.assertEqual(r.code,'transferring')

    def test_pause_and_schedule_take_precedence(self):
        self.assertEqual(diagnose({**self.row, 'state':'Pausado'}).code, 'paused')
        self.assertEqual(diagnose({**self.row, 'state':'Fuera de horario'}).code, 'scheduled')

    def test_disk_and_permissions_error(self):
        r = diagnose({**self.row, 'state':'Error', 'error':'Permission denied',
                      'error_hint':'Prueba otra carpeta'})
        self.assertEqual(r.code, 'motor_error')
        self.assertIn('Prueba otra carpeta',r.advice)

    def test_magnet_metadata(self):
        self.assertEqual(diagnose({**self.row,'state':'Metadatos'}).code,'metadata')

    def test_complete_status(self):
        self.assertEqual(diagnose({**self.row,'progress':1,'state':'Compartiendo'}).code,'complete')

    def test_listen_failure_only_when_observed(self):
        self.assertEqual(diagnose(self.row,listen_ok=False).code, 'listen')

    def test_no_overstatement_immediate_wait(self):
        r = diagnose({**self.row,'idle_seconds':4})
        self.assertEqual(r.code, 'waiting')

    def test_disabled_dht_no_confirmed_responses(self):
        r = diagnose({**self.row,'idle_seconds':10},dht_enabled=False)
        self.assertEqual(r.code,'discovery')

    def test_tracker_count_deduplicated(self):
        self.assertEqual(tracker_counts([{'url':'udp://a','state':'Error'},
                                        {'url':'udp://a','state':'Respondió'}])['total'],1)

    def test_evidence_no_names_ips_or_urls(self):
        r = diagnose(self.row,[{'url':'https://private.domain','state':'Error'}])
        self.assertNotIn('private.domain',r.report())


class EngineHardening(unittest.TestCase):
    def test_reannounce_cooldown(self):
        with tempfile.TemporaryDirectory() as d:
            app = engine.TorrentEngine(Store(Path(d)))
            rid = app.add_magnet('magnet:?xt=urn:btih:aaaaaabbbbb')
            handle=app.handles[rid]
            calls=[]
            handle.force_reannounce=lambda: calls.append(1)
            app.reannounce(rid)
            self.assertEqual(calls,[1])
            with self.assertRaises(engine.EngineError):
                app.reannounce(rid)
            self.assertEqual(calls,[1])

    def test_no_changes_to_port(self):
        with tempfile.TemporaryDirectory() as d:
            app=engine.TorrentEngine(Store(Path(d)))
            self.assertEqual(app._session_settings()['listen_interfaces'], engine.interface_settings('route',0,app._route)['listen_interfaces'])

    def test_unexpected_tracker_alerts_bounded(self):
        src=(Path(__file__).resolve().parents[1]/'app'/'engine.py').read_text(encoding='utf8')
        self.assertIn('len(bucket) >= 512',src)

    def test_window_diagnosis_tools_present(self):
        ui=(Path(__file__).resolve().parents[1]/'app'/'ui.py').read_text(encoding='utf8')
        ast.parse(ui)
        for token in ['¿Por qué no descarga?', 'copy_torrent_reason', '_notify_problem_rows',
                      'notify_problems', '_last_tracker_signature']:
            self.assertIn(token,ui)

    def test_opt_in_notification(self):
        self.assertFalse(initial_settings()['notify_problems'])
        self.assertEqual(VERSION,'1.4.0-alpha.1')

if __name__=='__main__':
    unittest.main()
