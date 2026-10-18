"""Apex Torrent 1.3.8: regression tests for recovery safeguards and UI contracts."""
from __future__ import annotations
import ast
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from test_engine_mock import engine, Store

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'app'


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name))
        self.e = engine.TorrentEngine(self.store)
        self.id = self.e.add_magnet('magnet:?xt=urn:btih:recovery-example-138')
        self.handle = self.e.handles[self.id]
        self.handle.force_reannounce = Mock()
        self.handle.force_dht_announce = Mock()
        self.handle.torrent_file = lambda: type('Info', (), {'priv': lambda s: False})()

    def test_real_retry_invokes_discovery_once_without_touching_files_or_settings(self):
        before = dict(self.e.settings)
        old_records = self.store.load_records()
        outcome = self.e.attempt_recovery(self.id)
        self.assertEqual(outcome['code'], 'requested')
        self.assertTrue(outcome['changed'])
        self.handle.force_reannounce.assert_called_once()
        self.handle.force_dht_announce.assert_called_once()
        self.assertEqual(self.e.settings, before)
        self.assertEqual(self.store.load_records(), old_records)

    def test_cooldown_rejects_multiple_requests_without_more_traffic(self):
        self.e.attempt_recovery(self.id)
        response = self.e.attempt_recovery(self.id)
        self.assertEqual(response['code'], 'cooldown')
        self.assertFalse(response['changed'])
        self.handle.force_reannounce.assert_called_once()
        self.handle.force_dht_announce.assert_called_once()

    def test_private_torrent_uses_tracker_but_never_forces_dht(self):
        self.handle.torrent_file = lambda: type('Info', (), {'priv': lambda s: True})()
        response = self.e.attempt_recovery(self.id)
        self.assertEqual(response['via'], ('trackers',))
        self.handle.force_dht_announce.assert_not_called()
        self.handle.force_reannounce.assert_called_once()

    def test_dht_disabled_is_honored(self):
        self.e.settings['dht'] = False
        outcome = self.e.attempt_recovery(self.id)
        self.assertTrue(outcome['changed'])
        self.handle.force_dht_announce.assert_not_called()
        self.handle.force_reannounce.assert_called_once()

    def test_manual_pause_preserved_without_network_calls(self):
        self.e.records[self.id]['paused'] = True
        outcome = self.e.attempt_recovery(self.id)
        self.assertEqual(outcome['code'], 'paused')
        self.handle.force_reannounce.assert_not_called()
        self.handle.force_dht_announce.assert_not_called()
        self.assertTrue(self.e.records[self.id]['paused'])

    def test_scheduler_pause_preserved_without_network_calls(self):
        self.e.records[self.id]['schedule_paused'] = True
        outcome = self.e.attempt_recovery(self.id)
        self.assertEqual(outcome['code'], 'paused')
        self.handle.force_reannounce.assert_not_called()

    def test_complete_torrent_no_retry(self):
        with patch.object(self.handle, 'status') as status:
            status.return_value = type('Status', (), {'progress': 1.0, 'is_seeding': True, 'errc': None})()
            outcome = self.e.attempt_recovery(self.id)
        self.assertEqual(outcome['code'], 'completed')
        self.handle.force_reannounce.assert_not_called()

    def test_engine_missing_dht_api_remains_compatible(self):
        del self.handle.force_dht_announce
        outcome = self.e.attempt_recovery(self.id)
        self.assertEqual(outcome['via'], ('trackers',))

    def test_reannounce_legacy_button_and_recovery_share_cooldown(self):
        self.e.attempt_recovery(self.id)
        with self.assertRaises(engine.EngineError):
            self.e.reannounce(self.id)
        self.handle.force_reannounce.assert_called_once()

    def test_missing_record_not_mutated(self):
        with self.assertRaises(engine.EngineError):
            self.e.attempt_recovery('unknown-identifier')
        self.handle.force_reannounce.assert_not_called()


class UiContracts(unittest.TestCase):
    def test_visual_polish_is_scrollable_and_elides_long_values(self):
        ui = (APP / 'ui.py').read_text(encoding='utf-8')
        ast.parse(ui)
        for token in ('class ElidedDetailValue', 'setFullText', 'ElideMiddle',
                      'overview_scroll.setWidget(overview)', 'overview.setMinimumHeight(205)',
                      'QScrollArea', 'DISPONIBILIDAD', 'self.recover_selected',
                      'QAbstractItemView.ScrollMode.ScrollPerPixel'):
            self.assertIn(token, ui)
        self.assertNotIn('ovl = QGridLayout(self.tabs)', ui)

    def test_network_repair_and_bridge_are_preserved(self):
        engine_src = (APP / 'engine.py').read_text(encoding='utf-8')
        ui = (APP / 'ui.py').read_text(encoding='utf-8')
        assert 'interface_settings(s.get("network_mode", "route")' in engine_src
        assert '"listen_port", 0' in engine_src
        assert 'self._bridge_launch' in ui
        assert 'self._setup_tray()' in ui
        self.assertIn('VERSION = "1.3.8"', (APP / 'state.py').read_text('utf-8'))
        self.assertIn('ApexTorrent/1.3.8', engine_src)


if __name__ == '__main__':
    unittest.main()
