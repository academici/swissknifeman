"""Тесты чистой арифметики confidence: формула, decay/полураспад, тиры, границы."""
import math
import unittest

from analyst import confidence as C


class TestConfidence(unittest.TestCase):
    # ── beta_mean ────────────────────────────────────────────────────────────
    def test_beta_mean_neutral_prior(self):
        # S=N=0 → α/(α+β)=0.5 (нейтральный приор, а не 0/0)
        self.assertAlmostEqual(C.beta_mean(0, 0), 0.5)

    def test_beta_mean_success(self):
        # (9+1)/(10+2) = 10/12
        self.assertAlmostEqual(C.beta_mean(9, 10), 10 / 12)

    def test_beta_mean_clips_negative(self):
        self.assertAlmostEqual(C.beta_mean(-5, -5), 0.5)

    # ── volume_factor ────────────────────────────────────────────────────────
    def test_volume_zero(self):
        self.assertEqual(C.volume_factor(0), 0.0)

    def test_volume_at_k(self):
        self.assertAlmostEqual(C.volume_factor(C.VOLUME_K), 1 - math.exp(-1))

    def test_volume_saturates(self):
        self.assertGreater(C.volume_factor(1000), 0.99)

    # ── time_decay + полураспад ──────────────────────────────────────────────
    def test_decay_zero_days(self):
        self.assertEqual(C.time_decay(0), 1.0)

    def test_decay_half_life_14d(self):
        # λ=0.95: 0.95^14 ≈ 0.49 (полураспад ≈ 14 дней)
        self.assertAlmostEqual(C.time_decay(14), 0.95 ** 14)
        self.assertTrue(0.45 < C.time_decay(14) < 0.5)

    def test_decay_negative_clips_to_one(self):
        self.assertEqual(C.time_decay(-3), 1.0)

    def test_decay_monotonic(self):
        self.assertGreater(C.time_decay(1), C.time_decay(5))

    # ── confidence (композиция) ──────────────────────────────────────────────
    def test_confidence_no_volume_is_zero(self):
        # N=0 → volume=0 → confidence=0 независимо от S/decay
        self.assertEqual(C.confidence(0, 0, 0), 0.0)

    def test_confidence_composition(self):
        s, n, d = 48, 50, 3
        expected = C.beta_mean(s, n) * C.volume_factor(n) * C.time_decay(d)
        self.assertAlmostEqual(C.confidence(s, n, d), expected)

    def test_confidence_deterministic(self):
        self.assertEqual(C.confidence(30, 40, 5), C.confidence(30, 40, 5))

    def test_confidence_decays_over_time(self):
        fresh = C.confidence(45, 50, 0)
        stale = C.confidence(45, 50, 30)
        self.assertGreater(fresh, stale)

    def test_confidence_bounded(self):
        self.assertLess(C.confidence(10 ** 6, 10 ** 6, 0), 1.0)

    # ── тиры ─────────────────────────────────────────────────────────────────
    def test_tiers_thresholds(self):
        self.assertEqual(C.tier(0.95), "core")
        self.assertEqual(C.tier(0.90), "core")
        self.assertEqual(C.tier(0.70), "strong")
        self.assertEqual(C.tier(0.69), "moderate")
        self.assertEqual(C.tier(0.50), "moderate")
        self.assertEqual(C.tier(0.30), "tentative")
        self.assertEqual(C.tier(0.29), "none")
        self.assertEqual(C.tier(0.0), "none")


if __name__ == "__main__":
    unittest.main()
