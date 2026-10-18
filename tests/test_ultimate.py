"""Pruebas para módulos aislados de Ultimate (sin librerías gráficas)."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from ultimate import tracker_summary, inspect_names, disk_estimate, safe_download_path, file_sha256

class UltimateTests(unittest.TestCase):
    def test_tracker_summary_doesnt_mark_announce_as_success(self):
        result = tracker_summary([{'url': 'udp://a', 'state': 'Anunciando'},
                                  {'url': 'udp://b', 'state': 'Respondió'},
                                  {'url': 'udp://a', 'state': 'Error'},
                                  {'url': 'udp://c', 'state': 'Error'},
                                  {'url': '(ninguno)', 'state': 'Sin trackers'}])
        self.assertEqual(result, dict(total=3, respondieron=1, errores=1,
                                      anunciando=1, sin_respuesta=0))
    def test_risk_warning_is_not_antivirus(self):
        report = inspect_names([{'path': 'docs/manual.pdf'},
                                {'path': 'tools/launch.exe'},
                                {'path': 'package.zip'},
                                {'path': 'readme.pdf.exe'}])
        self.assertEqual(report['executable_count'], 2)
        self.assertEqual(report['archives'], 1)
    def test_path_escape_rejected(self):
        with TemporaryDirectory() as d:
            root = Path(d).resolve()
            (root/'ok.txt').write_text('apex')
            self.assertEqual(safe_download_path(d, 'ok.txt'), root/'ok.txt')
            with self.assertRaises(ValueError):
                safe_download_path(d, '../escape.txt')
    def test_checksum(self):
        with TemporaryDirectory() as d:
            p = Path(d) / 'empty'
            p.write_bytes(b'')
            self.assertEqual(file_sha256(p), 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855')
    def test_disk_estimate(self):
        with TemporaryDirectory() as d:
            result = disk_estimate(d, 10, 3)
            self.assertEqual(result['remaining'], 7)
            self.assertTrue(result['enough'])
