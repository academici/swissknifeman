from __future__ import annotations
import unittest
from artifex import faults

class FaultMatrixTests(unittest.TestCase):
    def test_every_cut_uses_a_fresh_crashed_process(self):
        for cut in faults.CUT_POINTS:
            with self.subTest(cut=cut):
                result = faults.crash_at(cut)
                self.assertTrue(result.reached)
                self.assertEqual(97, result.exit_code)
    def test_unknown_cut_refuses(self):
        with self.assertRaises(faults.FaultRefusal): faults.crash_at("unknown")
