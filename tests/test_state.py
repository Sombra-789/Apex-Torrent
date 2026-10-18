import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from state import Store, readable_size, readable_speed, readable_eta

class StateTests(unittest.TestCase):
    def test_units(self):
        self.assertEqual(readable_size(1024), '1.0 KiB')
        self.assertEqual(readable_speed(1024), '1.0 KiB/s')
        self.assertEqual(readable_eta(3661), '1 h 1 min')
        self.assertEqual(readable_eta(-1), '—')

    def test_atomic_data_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            store.save_json('settings.json', {'download_limit_kib': 77})
            self.assertEqual(store.load_settings()['download_limit_kib'], 77)
            self.assertTrue(store.load_settings()['download_dir'])
            self.assertEqual(store.load_records(), [])
            rec = {'x': {'id': 'x', 'source': 'magnet:?xt=urn:btih:123', 'save_path': tmp, 'kind': 'magnet'}}
            store.save_records(rec)
            self.assertEqual(store.load_records()[0]['id'], 'x')

    def test_invalid_json_recovers(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            (Path(tmp) / 'downloads.json').write_text('{bad json', encoding='utf-8')
            self.assertEqual(store.load_records(), [])

if __name__ == '__main__':
    unittest.main()
