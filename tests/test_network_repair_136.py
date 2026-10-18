"""Pruebas independientes de IP/rútas y regresiones sin conexiones reales."""
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
import sys

APP = Path(__file__).resolve().parents[1] / 'app'
sys.path.insert(0, str(APP))
from network_routes import (RouteSnapshot, detect_default_route, interface_settings,
                            readable_route, RouteError)
from test_engine_mock import engine, Store


class FakeSocket:
    def __init__(self, family, typ, *, ipv4='192.168.100.4', ipv6=None, fail=False):
        self.family = family
        self.ipv4 = ipv4
        self.ipv6 = ipv6
        self.fail = fail
        self.closed = False
    def connect(self, target):
        if self.fail or (self.family != 2 and self.ipv6 is None):
            raise OSError('Sin ruta')
    def getsockname(self):
        return (self.ipv4 if self.family == 2 else self.ipv6, 48888)
    def close(self):
        self.closed = True


class RouteTests(TestCase):
    def test_local_195_network_not_included(self):
        route = detect_default_route(lambda family,typ:FakeSocket(family,typ))
        self.assertEqual(route.ipv4, '192.168.100.4')
        conf = interface_settings('route', 0, route)
        self.assertEqual(conf['listen_interfaces'], '192.168.100.4:0')
        self.assertEqual(conf['outgoing_interfaces'], '192.168.100.4')
        self.assertNotIn('192.168.56.1', str(conf))
        self.assertNotIn('127.0.0.1', str(conf))
        self.assertNotIn('0.0.0.0', str(conf))

    def test_route_v6_and_v4(self):
        route = detect_default_route(lambda family,typ:FakeSocket(family,typ,ipv6='2001:4860:1234::2'))
        conf = interface_settings('route', 55013, route)
        self.assertEqual(conf['listen_interfaces'], '192.168.100.4:55013,[2001:4860:1234::2]:55013')
        self.assertEqual(conf['outgoing_interfaces'], '192.168.100.4,2001:4860:1234::2')

    def test_no_route_is_fail_closed(self):
        route = detect_default_route(lambda family,typ:FakeSocket(family,typ,fail=True))
        self.assertFalse(route.ready)
        self.assertEqual(interface_settings('route', 0, route),
                         {'listen_interfaces':'','outgoing_interfaces':'127.0.0.1'})
        self.assertIn('detenidas',readable_route('route',route))

    def test_loopback_and_virtual_source_only_from_windows_route(self):
        route = detect_default_route(lambda fam, typ:FakeSocket(fam, typ, ipv4='127.0.0.1'))
        self.assertFalse(route.ready)

    def test_legacy_reversible(self):
        self.assertEqual(interface_settings('compatibility',0,RouteSnapshot()),
                         {'listen_interfaces':'0.0.0.0:0,[::]:0','outgoing_interfaces':''})

    def test_validation(self):
        for mode, port in [('route', 23),('route',65536),('bad',0)]:
            with self.assertRaises(RouteError):
                interface_settings(mode,port,RouteSnapshot('192.168.100.4'))

    def test_route_updates_without_changes_to_downloads(self):
        with tempfile.TemporaryDirectory() as temp:
            eng = engine.TorrentEngine(Store(Path(temp)))
            eng.apply_settings({'network_mode':'route'})
            rid=eng.add_magnet('magnet:?xt=urn:btih:0123456789ABCDEF')
            records=dict(eng.records)
            eng._route=RouteSnapshot('192.168.56.1')
            with patch.object(engine, 'detect_default_route',return_value=RouteSnapshot('192.168.100.4')):
                self.assertTrue(eng.refresh_network_route(force=True))
            self.assertEqual(eng.session.options['listen_interfaces'],'192.168.100.4:0')
            self.assertEqual(eng.session.options['outgoing_interfaces'],'192.168.100.4')
            self.assertEqual(records,eng.records)
            self.assertIn(rid,eng.handles)
            self.assertFalse(eng.refresh_network_route(force=False))

    def test_route_loss_blocks_not_falls_back(self):
        with tempfile.TemporaryDirectory() as temp:
            eng=engine.TorrentEngine(Store(Path(temp)))
            eng._route=RouteSnapshot('192.168.100.4')
            with patch.object(engine,'detect_default_route',return_value=RouteSnapshot()):
                eng.refresh_network_route(force=True)
            self.assertEqual(eng.session.options['listen_interfaces'],'')
            self.assertEqual(eng.session.options['outgoing_interfaces'],'127.0.0.1')

    def test_invalid_setting_never_persists(self):
        with tempfile.TemporaryDirectory() as temp:
            eng=engine.TorrentEngine(Store(Path(temp)))
            with self.assertRaises(engine.EngineError):
                eng.apply_settings({'network_mode':'unsafe_magic'})
            self.assertEqual(eng.settings['network_mode'],'route')

    def test_ui_exposes_mode_and_route_button(self):
        ui=(APP/'ui.py').read_text('utf8')
        self.assertIn('self.network_mode',ui)
        self.assertIn('def redetect_network_route(',ui)
        self.assertIn('self.engine.refresh_network_route()',ui)
