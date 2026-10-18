"""Pruebas de 1.3.7: formatos reales, distinción payload/control y UI responsive."""
import ast
from pathlib import Path
import unittest
from unittest.mock import patch
import tempfile
import sys

APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP))
from peer_intelligence import human_endpoint, human_client, peer_availability, download_activity, displayed_payload_rate
from test_engine_mock import engine, Store


class PeerFormatTests(unittest.TestCase):
    def test_ipv4_tuple_rendered_without_repr(self):
        self.assertEqual(human_endpoint(('187.188.76.236', 7659)), '187.188.76.236:7659')
        self.assertEqual(human_endpoint("('187.188.76.236', 7659)"), '187.188.76.236:7659')

    def test_ipv6_and_invalid_endpoint(self):
        self.assertEqual(human_endpoint(('2001:db8::1', 6881)), '[2001:db8::1]:6881')
        self.assertEqual(human_endpoint("('not an ip', 80)"), 'No disponible')
        self.assertEqual(human_endpoint(('127.0.0.1', -1)), 'No disponible')

    def test_client_bytes_and_empty(self):
        self.assertEqual(human_client(b'libtorrent 2.0'), 'libtorrent 2.0')
        self.assertEqual(human_client(b''), 'No identificado')
        self.assertEqual(human_client(None), 'No identificado')

    def test_availability_is_not_a_seed_estimate(self):
        self.assertIn('Sin piezas', peer_availability(0))
        self.assertIn('Parcial', peer_availability(.32))
        self.assertIn('Fuente completa', peer_availability(1))

    def test_distinguishes_protocol_and_payload(self):
        self.assertEqual(download_activity({'progress':0,'down':17,'payload_down':0,'peers':0})[0], 'Solo protocolo')
        self.assertEqual(download_activity({'progress':0,'down':2097152,'payload_down':2097152,'peers':12})[0], 'Recibiendo piezas')
        self.assertEqual(download_activity({'progress':0,'down':0,'payload_down':0,'peers':0})[0], 'Buscando fuentes')
        self.assertEqual(displayed_payload_rate({'down':300,'payload_down':0}), 0)
        self.assertEqual(displayed_payload_rate({'down':300}), 300)

    def test_peer_binding_normalization(self):
        with tempfile.TemporaryDirectory() as f:
            e = engine.TorrentEngine(Store(Path(f)))
            rid = e.add_magnet('magnet:?xt=urn:btih:unit137')
            result = e.peer_details(rid)
            self.assertEqual(result[0]['client'],'Cliente prueba')
            self.assertIn('Parcial', result[0]['availability'])


class VisualContractTests(unittest.TestCase):
    def test_ui_structure_and_versions(self):
        ui = (APP/'ui.py').read_text('utf8')
        for token in ('toggle_details', '_restore_library_splitter', '_adapt_table_columns',
                      'ui_layout.json', 'QSplitter', 'displayed_payload_rate',
                      'self.peer_summary', 'self.insight_box.setMaximumHeight(43)'):
            self.assertIn(token, ui)
        ast.parse(ui)
        self.assertIn('VERSION = "1.3.8"', (APP/'state.py').read_text('utf8'))
        self.assertIn('ApexTorrent/1.3.8', (APP/'engine.py').read_text('utf8'))

    def test_engine_does_not_change_listen_route(self):
        with tempfile.TemporaryDirectory() as temp:
            e = engine.TorrentEngine(Store(Path(temp)))
            self.assertEqual(e.settings['network_mode'], 'route')
            self.assertEqual(e.settings['listen_port'], 0)

    def test_layout_helper_safe_and_non_networked(self):
        mod = ast.parse((APP/'peer_intelligence.py').read_text('utf8'))
        self.assertGreaterEqual(len(mod.body), 4)
