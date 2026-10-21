"""A successful log tail must not hide an earlier failed command in a correction."""
from pathlib import Path
import tempfile
import unittest

from orch.conductor import prompts


class CheckCorrectionTests(unittest.TestCase):
    def test_failure_before_successful_tail_remains_visible_with_exact_log_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "V90.log"
            log.write_text("[ok] preceding unit\n[fail] hub: golden.py check\nwrong launch list\n"
                           + "[ok] later unit\n" * 200)
            text = prompts.check_correction([{"id": "V90", "cmd": "affected", "exit": 1,
                                              "log": str(log), "tail": "[ok] later unit"}])
            self.assertIn(str(log), text)
            self.assertIn("[fail] hub: golden.py check\nwrong launch list", text)
            self.assertTrue(text.endswith("[ok] later unit"))
            self.assertIn("tail may omit", text)

    def test_excerpt_is_bounded_even_with_a_long_error_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "long.log"
            log.write_text("ERROR: " + "x" * 10000)
            excerpt = prompts._failure_excerpt(log)
            self.assertTrue(excerpt.startswith("ERROR:"))
            self.assertLessEqual(len(excerpt), 1600)

    def test_missing_log_keeps_path_and_tail_without_raising(self):
        text = prompts.check_correction([{"id": "V2", "cmd": "test", "exit": 1,
                                          "log": "/missing/check.log", "tail": "failed"}])
        self.assertIn("/missing/check.log", text)
        self.assertTrue(text.endswith("failed"))

    def test_legacy_row_without_log_preserves_the_existing_contract(self):
        text = prompts.check_correction([{"id": "V2", "procedure": "inspect", "verdict": "RED", "tail": "why"}])
        self.assertEqual(text, "These acceptance checks are red on your candidate:\n\nV2: `inspect` → RED\nwhy")


class ResumedContractTests(unittest.TestCase):
    def test_continuation_uses_latest_full_contract_after_an_input_rebuild(self):
        blocks = prompts.executor_resumed(item="P3.1", step="executor.2", correction="repair V1")
        continuation = next(block.text for block in blocks if block.kind == "resumed")
        self.assertIn("latest full prompt", continuation)
        self.assertNotIn("first prompt", continuation)
        self.assertTrue(any(block.kind == "result_contract" for block in blocks))
        self.assertTrue(any(block.kind == "correction" for block in blocks))
