"""Isolation invariants for Evolution Alpha; no Qt or network involved."""
import unittest
from pathlib import Path
from state import DATA_DIR, VERSION, initial_settings

ROOT = Path(__file__).resolve().parents[1]

class AlphaIsolationTests(unittest.TestCase):
    def test_version_and_local_state_isolated(self):
        self.assertEqual(VERSION, "1.4.0-alpha.1")
        self.assertEqual(DATA_DIR.name, "ApexTorrentAlpha")
        self.assertNotEqual(DATA_DIR.name, "ApexTorrent")

    def test_downloads_do_not_use_stable_default(self):
        settings = initial_settings()
        self.assertEqual(Path(settings["download_dir"]).name, "Apex Torrent Alpha")

    def test_app_windows_identity_separate(self):
        source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        self.assertIn("ApexSoftware.ApexTorrentAlpha.LocalOpen.v1", source)
        self.assertIn("ApexSoftware.ApexTorrent.Alpha", source)

    def test_installer_has_own_app_id_and_directory(self):
        alpha = (ROOT / "installer" / "ApexTorrentAlpha.iss").read_text(encoding="utf-8")
        stable = (ROOT / "installer" / "ApexTorrent.iss").read_text(encoding="utf-8")
        self.assertIn("ApexTorrentAlpha", alpha)
        self.assertIn("ApexTorrent_1.4.0_alpha1_Setup_x64", alpha)
        self.assertNotEqual(next(line for line in alpha.splitlines() if line.startswith("AppId=")),
                            next(line for line in stable.splitlines() if line.startswith("AppId=")))

    def test_swarm_ui_only_reads_peer_data_when_tab_active(self):
        source = (ROOT / "app" / "ui.py").read_text(encoding="utf-8")
        self.assertIn('self.tabs.addTab(radar_tab, "Swarm Radar")', source)
        self.assertIn('if tab == 7:', source)
        self.assertIn('snapshot = summarize_swarm(rec, peers)', source)

if __name__ == "__main__":
    unittest.main()
