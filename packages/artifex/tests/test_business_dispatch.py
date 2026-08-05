from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from artifex import business_dispatch


PLAN = Path(__file__).resolve().parents[3] / "plans" / "2026.08.03-ARTIFEX-SUPERVISOR"
G2 = "ef08406d7ca630d46e9e9e8bca0d10ea73b141d984615bded75f19d7eea13f09"


class BusinessDispatchTests(unittest.TestCase):
    def test_indexed_d105_is_read_only_and_g2_linked(self):
        path = PLAN / "artifacts/P5/trial-admissions/p5.2-slice-01-worktree-core.json"
        value = business_dispatch.load_indexed(PLAN, path, g2_digest=G2, g2b_digest="1" * 64)
        self.assertEqual(("business-trial", 0), (value["purpose"], value["usage"]["used_slices"]))

    def test_g2_substitution_or_unindexed_file_refuses(self):
        path = PLAN / "artifacts/P5/trial-admissions/p5.2-slice-01-worktree-core.json"
        with self.assertRaisesRegex(business_dispatch.BusinessRefusal, "G2_PREDECESSOR_MISMATCH"):
            business_dispatch.load_indexed(PLAN, path, g2_digest="0" * 64, g2b_digest="1" * 64)
        with tempfile.TemporaryDirectory() as directory:
            foreign = Path(directory) / "admission.json"; foreign.write_text(json.dumps({}), encoding="utf-8")
            with self.assertRaisesRegex(business_dispatch.BusinessRefusal, "ADMISSION_PATH_EXTERNAL"):
                business_dispatch.load_indexed(PLAN, foreign, g2_digest=G2, g2b_digest="1" * 64)


if __name__ == "__main__":
    unittest.main()
