"""Pruebas de integración sin red con doble de libtorrent."""
import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / 'app'
sys.path.insert(0, str(APP))
from state import Store


class FakeInfo:
    def __init__(self, source):
        self.source = source
    def info_hashes(self):
        return 'hash:' + str(self.source)


class FakeATP:
    def __init__(self, info_hashes=''):
        self.ti = None
        self.info_hashes = info_hashes
        self.save_path = ''


class FakeStatus:
    name = 'Torrent de prueba'
    total_wanted = 100
    total_wanted_done = 30
    download_rate = 10
    upload_rate = 5
    progress = .30
    is_seeding = False
    paused = False
    state = 2
    num_peers = 3
    num_seeds = 2
    all_time_upload = 50
    all_time_download = 100
    errc = None


class FakeHandle:
    def __init__(self, key):
        self.key = key
        self.paused = False
        self.down_limit = None
        self.up_limit = None
    def set_download_limit(self, value):
        self.down_limit = value
    def set_upload_limit(self, value):
        self.up_limit = value
    def get_peer_info(self):
        return [types.SimpleNamespace(ip="127.0.0.1:50500", client="Cliente prueba",
                down_speed=1000, up_speed=500, progress=0.7)]
    def info_hashes(self):
        return self.key
    def is_valid(self):
        return True
    def pause(self):
        self.paused = True
    def resume(self):
        self.paused = False
    def force_recheck(self):
        pass
    def save_resume_data(self):
        pass
    def status(self):
        status = FakeStatus()
        status.paused = self.paused
        return status
    def has_metadata(self):
        return True
    def get_file_priorities(self):
        return []
    def trackers(self):
        return []


class FakeSession:
    delete_files = 1
    def __init__(self, options):
        self.options = options
        self.handles = {}
        self.deleted = []
    def add_torrent(self, atp):
        key = str(atp.ti.info_hashes()) if atp.ti else str(atp.info_hashes)
        if key not in self.handles:
            self.handles[key] = FakeHandle(key)
        return self.handles[key]
    def remove_torrent(self, h, opts=None):
        self.deleted.append((h, opts))
        self.handles.pop(h.key, None)
    def pop_alerts(self):
        return []
    def apply_settings(self, options):
        self.options = options


lib = types.ModuleType('libtorrent')
lib.session = FakeSession
lib.torrent_info = FakeInfo
lib.add_torrent_params = FakeATP
lib.parse_magnet_uri = lambda source: FakeATP(source.split('xt=',1)[1].split('&',1)[0])
lib.read_resume_data = lambda data: FakeATP('resume')
lib.save_resume_data_alert = type('save_resume_data_alert',(object,),{})
lib.save_resume_data_failed_alert = type('save_resume_data_failed_alert',(object,),{})
lib.metadata_received_alert = type('metadata_received_alert',(object,),{})
lib.torrent_status = types.SimpleNamespace(checking_files=0,checking_resume_data=6)
lib.write_resume_data_buf = lambda params: b'resume'
sys.modules['libtorrent'] = lib
import engine


class EngineTests(unittest.TestCase):
    def test_profile_updates_engine_and_keeps_auto_port(self):
        with tempfile.TemporaryDirectory() as folder:
            app = engine.TorrentEngine(Store(Path(folder)))
            app.apply_profile('Máximo rendimiento')
            self.assertEqual(app.settings['connections_limit'], 350)
            self.assertEqual(app.settings['listen_port'], 0)
            self.assertEqual(app.session.options['connections_limit'], 350)
            self.assertEqual(Store(Path(folder)).load_settings()['profile'], 'Máximo rendimiento')
            app.apply_profile('Red limitada')
            self.assertEqual(app.session.options['download_rate_limit'], 2048 * 1024)
            self.assertEqual(app.session.options['upload_rate_limit'], 256 * 1024)
            self.assertEqual(app.session.options['connections_limit'], 80)

    def test_reject_unknown_profile_without_mutation(self):
        with tempfile.TemporaryDirectory() as folder:
            app = engine.TorrentEngine(Store(Path(folder)))
            before = dict(app.settings)
            with self.assertRaises(engine.EngineError):
                app.apply_profile('Turbo ilimitado mágico')
            self.assertEqual(app.settings, before)

    def test_individual_limits_are_persisted_and_restored(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder))
            app = engine.TorrentEngine(store)
            rid = app.add_magnet('magnet:?xt=urn:btih:abc123')
            app.set_torrent_limits(rid, 5120, 256)
            self.assertEqual(app.handles[rid].down_limit, 5120 * 1024)
            self.assertEqual(app.handles[rid].up_limit, 256 * 1024)
            self.assertEqual(store.load_records()[0]['download_limit_kib'], 5120)
            again = engine.TorrentEngine(store)
            self.assertEqual(again.handles[rid].down_limit, 5120 * 1024)
            self.assertEqual(again.handles[rid].up_limit, 256 * 1024)

    def test_peer_info_and_network_summary(self):
        with tempfile.TemporaryDirectory() as folder:
            app = engine.TorrentEngine(Store(Path(folder)))
            rid = app.add_magnet('magnet:?xt=urn:btih:abc123')
            result = app.peer_details(rid)
            self.assertEqual(result[0]['down'], 1000)
            self.assertEqual(result[0]['progress'], 0.7)
            overview = app.network_overview()
            self.assertIn('profile', overview)
            self.assertEqual(overview['requested_interfaces'], engine.interface_settings('route',0,app._route)['listen_interfaces'] or '(red detenida: sin ruta)')

    def test_default_listen_port_is_automatic_and_not_6881(self):
        with tempfile.TemporaryDirectory() as d:
            app = engine.TorrentEngine(Store(Path(d)))
            self.assertEqual(app.settings['listen_port'], 0)
            self.assertEqual(app.session.options['listen_interfaces'], engine.interface_settings('route',0,app._route)['listen_interfaces'])

    def test_manual_listen_port_applies_to_ipv4_and_ipv6(self):
        with tempfile.TemporaryDirectory() as d:
            app = engine.TorrentEngine(Store(Path(d)))
            app.apply_settings({'listen_port': 55013})
            self.assertEqual(app.session.options['listen_interfaces'], engine.interface_settings('route',55013,app._route)['listen_interfaces'])
            self.assertEqual(Store(Path(d)).load_settings()['listen_port'], 55013)
            self.assertIn('listen_interfaces', app._session_settings())

    def test_old_settings_without_port_get_automatic_port(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d))
            store.save_json('settings.json', {'dht': True, 'connections_limit': 120})
            app = engine.TorrentEngine(store)
            self.assertEqual(app._session_settings()['listen_interfaces'], engine.interface_settings('route',0,app._route)['listen_interfaces'])
            self.assertEqual(app.settings['connections_limit'], 120)

    def test_invalid_listen_port_is_rejected_without_saving(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d))
            app = engine.TorrentEngine(store)
            with self.assertRaises(engine.EngineError):
                app.apply_settings({'listen_port': 10})
            self.assertEqual(app.settings['listen_port'], 0)
            self.assertEqual(store.load_settings()['listen_port'], 0)

    def test_magnet_validation(self):
        self.assertTrue(engine.validate_magnet('  magnet:?xt=urn:btih:abcdef  ').startswith('magnet:?'))
        with self.assertRaises(engine.EngineError):
            engine.validate_magnet('https://example.com')
        with self.assertRaises(engine.EngineError):
            engine.validate_magnet('magnet:?dn=without-hash')

    def test_add_duplicate_pause_resume_restore(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d))
            app = engine.TorrentEngine(store)
            url = 'magnet:?xt=urn:btih:ABCDEF&dn=free-distro'
            rid = app.add_magnet(url, d)
            self.assertEqual(len(app.rows()), 1)
            self.assertEqual(app.rows()[0]['progress'], .3)
            with self.assertRaises(engine.EngineError):
                app.add_magnet(url)
            app.pause(rid)
            self.assertTrue(store.load_records()[0]['paused'])
            app2 = engine.TorrentEngine(store)
            self.assertTrue(app2.handles[rid].paused)
            app2.resume(rid)
            self.assertFalse(app2.handles[rid].paused)
            app2.remove(rid, delete_data=False)
            self.assertEqual(store.load_records(), [])
            self.assertEqual(len(app2.rows()), 0)

    def test_real_error_message_is_exposed(self):
        class FakeError:
            def __bool__(self):
                return True
            def message(self):
                return 'There is not enough space on the disk.'
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d))
            app = engine.TorrentEngine(store)
            rid = app.add_magnet('magnet:?xt=urn:btih:ABCD1000', d)
            original = FakeStatus.errc
            try:
                FakeStatus.errc = FakeError()
                row = app.rows()[0]
                self.assertEqual(row['id'], rid)
                self.assertEqual(row['state'], 'Error')
                self.assertIn('not enough space', row['error'])
                self.assertIn('espacio', row['error_hint'])
                self.assertEqual(row['save_path'], str(Path(d).resolve()))
            finally:
                FakeStatus.errc = original

    def test_error_hints_are_conservative(self):
        self.assertIn('permisos', engine.explain_error('Access is denied'))
        self.assertIn('ruta', engine.explain_error('The system cannot find the path specified'))
        self.assertIn('mensaje', engine.explain_error('unknown engine error'))


    def test_error_code_category_fallback_if_message_raises(self):
        """La salida nunca debe incluir '<libtorrent.error_code object at 0x...>'."""
        class Category:
            def name(self):
                return 'system'
            def message(self, code):
                self.seen = code
                return 'Access is denied'
        category = Category()
        class BrokenError:
            def __bool__(self):
                return True
            def value(self):
                return 5
            def category(self):
                return category
            def message(self):
                raise RuntimeError('native method failed')
            def __str__(self):
                return '<libtorrent.error_code object at 0x987654321>'
        result = engine.describe_libtorrent_error(BrokenError())
        self.assertEqual(result['error'], 'Access is denied')
        self.assertEqual(result['error_code'], 5)
        self.assertEqual(result['error_category'], 'system')
        self.assertEqual(category.seen, 5)
        self.assertIn('RuntimeError', result['error_exception'])
        self.assertNotIn('object at', result['error'])

    def test_error_with_unreadable_binding_is_not_a_pointer(self):
        class BrokenError:
            def __bool__(self):
                return True
            def __str__(self):
                return '<libtorrent.error_code object at 0x12345>'
        result = engine.describe_libtorrent_error(BrokenError())
        self.assertIn('mensaje no disponible', result['error'])
        self.assertNotIn('0x12345', result['error'])
        self.assertIn('AttributeError', result['error_exception'])

    def test_zero_error_code_is_not_fatal(self):
        class SuccessCode:
            def __bool__(self):
                return True
            def value(self):
                return 0
            def message(self):
                return 'Success'
        result = engine.describe_libtorrent_error(SuccessCode())
        self.assertFalse(result['error'])
        self.assertEqual(result['error_code'], 0)

    def test_error_file_index(self):
        class Status:
            error_file = 2
        class Files:
            def num_files(self):
                return 3
            def file_path(self, idx):
                return f'data/file{idx}.iso'
        class Handle:
            def has_metadata(self):
                return True
            def torrent_file(self):
                return types.SimpleNamespace(files=lambda: Files())
        self.assertEqual(engine.describe_error_file(Status(), Handle()), 'data/file2.iso')
        Status.error_file = -4
        self.assertEqual(engine.describe_error_file(Status(), Handle()), 'Metadatos')

    def test_remove_data_flag_and_settings(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d))
            app = engine.TorrentEngine(store)
            src = Path(d) / 'linux.torrent'
            src.write_bytes(b'fake')
            rid = app.add_torrent_file(str(src), d)
            self.assertTrue((Path(d) / 'torrents' / (rid + '.torrent')).exists())
            app.apply_settings({'download_limit_kib': 300})
            self.assertEqual(app.session.options['download_rate_limit'], 300*1024)
            app.remove(rid, delete_data=True)
            self.assertEqual(app.session.deleted[-1][1], 1)
            self.assertFalse((Path(d) / 'torrents' / (rid + '.torrent')).exists())


    def test_tracker_panel_always_reports_status_instead_of_empty(self):
        with tempfile.TemporaryDirectory() as d:
            app = engine.TorrentEngine(Store(Path(d)))
            rid = app.add_magnet('magnet:?xt=urn:btih:01122000', d)
            report = app.tracker_details(rid)
            self.assertEqual(report[0]['state'], 'Sin trackers')
            self.assertTrue(report[0]['message'])

    def test_announce_and_network_report_without_error(self):
        with tempfile.TemporaryDirectory() as d:
            app = engine.TorrentEngine(Store(Path(d)))
            rid = app.add_magnet('magnet:?xt=urn:btih:01122001', d)
            h = app.handles[rid]
            h.force_reannounce = lambda: setattr(h, 'announced', True)
            h.trackers = lambda: [types.SimpleNamespace(url='udp://tracker.test:1337/announce')]
            app.reannounce(rid)
            self.assertTrue(h.announced)
            self.assertIn('tracker.test', app.tracker_details(rid)[0]['url'])
            report = app.network_diagnostic(rid)
            self.assertIn('TRACKERS', report)
            self.assertIn('Pares conectados:', report)
            self.assertIn('udp://tracker.test:1337/announce', report)
            self.assertIn('Ninguno registrado', report)

    def test_tracker_reply_alert_and_error_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            app = engine.TorrentEngine(Store(Path(d)))
            rid = app.add_magnet('magnet:?xt=urn:btih:01122002', d)
            handle = app.handles[rid]
            handle.trackers = lambda: [types.SimpleNamespace(url='https://tracker.test/announce')]
            reply_type = type('tracker_reply_alert', (), {})
            reply = reply_type()
            reply.handle = handle
            reply.url = 'https://tracker.test/announce'
            reply.num_peers = 12
            reply.message = lambda: 'ok'
            app.session.pop_alerts = lambda: [reply]
            app.process_alerts()
            info = app.tracker_details(rid)[0]
            self.assertEqual(info['state'], 'Respondió')
            self.assertIn('12 pares', info['message'])
            error_type = type('tracker_error_alert', (), {})
            error = error_type()
            error.handle = handle
            error.url = 'https://tracker.test/announce'
            error.message = lambda: 'connection refused'
            error.failure_reason = lambda: ''
            app.session.pop_alerts = lambda: [error]
            app.process_alerts()
            info = app.tracker_details(rid)[0]
            self.assertEqual(info['state'], 'Error')
            self.assertIn('connection refused', info['message'])

    def test_trackers_fallback_when_active_list_fails(self):
        with tempfile.TemporaryDirectory() as d:
            app = engine.TorrentEngine(Store(Path(d)))
            rid = app.add_magnet('magnet:?xt=urn:btih:01122003', d)
            h = app.handles[rid]
            def failed_trackers():
                raise RuntimeError('binding tracker failed')
            h.trackers = failed_trackers
            h.torrent_file = lambda: types.SimpleNamespace(trackers=lambda: [
                types.SimpleNamespace(url='https://torrent.ubuntu.com/announce')])
            info = app.tracker_details(rid)
            self.assertEqual(info[0]['url'], 'https://torrent.ubuntu.com/announce')
            self.assertIn('lectura parcial', info[-1]['url'])

    def test_hash_wrapper_formatted_and_duplicate_detected(self):
        class Hashes:
            def __init__(self):
                self.v1 = bytes([0xA1] * 20)
            def has_v1(self):
                return True
            def has_v2(self):
                return False
            def __str__(self):
                return '<libtorrent.info_hash_t object at 0xdeadbeef>'
        with tempfile.TemporaryDirectory() as d:
            app = engine.TorrentEngine(Store(Path(d)))
            rid = app.add_magnet('magnet:?xt=urn:btih:01122004', d)
            h = app.handles[rid]
            h.info_hashes = Hashes
            value = app._torrent_key(h)
            self.assertEqual(value, 'v1: ' + 'a1' * 20)
            new = types.SimpleNamespace(info_hashes=Hashes(), ti=None)
            with self.assertRaises(engine.EngineError):
                app._assert_not_duplicate(new)


if __name__ == '__main__':
    unittest.main()
