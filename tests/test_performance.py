"""Pruebas sin interfaz ni red para estadísticas y perfiles."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"app"))
from performance import TransferHistory, network_insight, profile_settings

class PerformanceTests(unittest.TestCase):
    def test_history_has_fixed_capacity_and_clamps_negative_samples(self):
        hist = TransferHistory(3)
        for i in range(4):
            hist.append(i * 100, -2)
        self.assertEqual(list(hist.downloads), [100,200,300])
        self.assertEqual(list(hist.uploads), [0,0,0])
        self.assertEqual(hist.peak(),300)

    def test_profiles_are_distinct_and_new_dicts(self):
        a = profile_settings('Equilibrado')
        b = profile_settings('Máximo rendimiento')
        self.assertNotEqual(a['connections_limit'], b['connections_limit'])
        a['connections_limit'] = 99
        self.assertEqual(profile_settings('Equilibrado')['connections_limit'],200)

    def test_no_seeds_is_only_a_warning_not_a_definitive_claim(self):
        desc = network_insight({'seeds':0, 'down':0, 'progress':0, 'paused':False},
                               [{'state':'Error'},{'state':'Anunciando'}])
        self.assertIn('no demuestra', desc)
        self.assertIn('1 trackers', desc)

    def test_completed_shows_seeding(self):
        self.assertIn('completa', network_insight({'progress':1}, []))
