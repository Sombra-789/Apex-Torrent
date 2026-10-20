"""Pruebas de Apex Swarm Radar sin Qt, libtorrent o internet."""
import unittest
from swarm_radar import summarize_swarm, radar_text

class SwarmRadarTests(unittest.TestCase):
    def test_no_sources_not_declared_dead(self):
        snap = summarize_swarm({"peers": 0, "seeds": 0, "payload_down": 0, "state": "Esperando pares"})
        self.assertEqual(snap.label, "Sin fuentes conectadas")
        self.assertIn("NO significa", snap.detail)
    def test_payload_means_useful_transfer(self):
        snap = summarize_swarm({"peers": 5, "seeds": 2, "payload_down": 2048}, [{"progress": .7}])
        self.assertEqual(snap.label, "Transfiriendo piezas")
        self.assertEqual(snap.observed_max_progress, .7)
    def test_protocol_only_not_payload(self):
        self.assertEqual(summarize_swarm({"peers": 1, "seeds": 0, "down": 999}).payload_bps, 0)
    def test_seed_count_capped_by_connected(self):
        s = summarize_swarm({"peers": 2, "seeds": 100, "payload_down": 0})
        self.assertEqual(s.seeds, 2)
    def test_paused_status_has_priority(self):
        self.assertEqual(summarize_swarm({"state": "Pausado", "peers": 4, "seeds": 2}).label, "En pausa")
    def test_unknown_progress_excluded(self):
        s = summarize_swarm({"peers": 2}, [{"progress": -1}, {"progress": float("nan")}, {"progress": .4}])
        self.assertEqual(s.observed_max_progress, .4)
    def test_percent_is_not_swarm_coverage(self):
        s = summarize_swarm({"peers": 1}, [{"progress": 1}])
        self.assertIn("no cobertura total", radar_text(s))
    def test_complete(self):
        self.assertEqual(summarize_swarm({"progress": 1, "peers": 0}).label, "Completado")
    def test_invalid_data_safe(self):
        s = summarize_swarm({"peers": "x", "seeds": None, "payload_down": "bad"})
        self.assertEqual((s.peers, s.seeds, s.payload_bps), (0, 0, 0))
if __name__ == "__main__":
    unittest.main()
