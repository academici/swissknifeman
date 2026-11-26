"""scripts/estimate.py: the expected time of a piece from the history of runs."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("estimate", ROOT / "scripts" / "estimate.py")
estimate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(estimate)


class EstimateTests(unittest.TestCase):
    def test_medians_of_the_history_and_measured_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for number, (executor, review, green) in enumerate(((300, 900, True), (500, 1100, False))):
                state = {"items": {"P1.1": {"steps": {
                    "scout": {"status": "done", "role": "context-scout", "route": "claude-code/haiku/low", "duration_s": 30},
                    "executor.1": {"status": "done", "role": "executor", "route": "claude-code/sonnet/medium", "duration_s": executor},
                    "review.1": {"status": "done", "role": "reviewer", "route": "grok/grok-4.7/high", "duration_s": review},
                    "checks.1": {"status": "done", "role": "deterministic", "duration_s": 120,
                                 "result": [{"id": "V1", "cmd": "bash t.sh", "seconds": 120, "green": green}]}}}}}
                (root / f"cnd-{number}").mkdir()
                (root / f"cnd-{number}" / "state.json").write_text(json.dumps(state), encoding="utf-8")
            found = estimate.estimate(root, ["bash t.sh", "bash new.sh"], "medium", True, None)
            self.assertEqual(found["parts_s"]["executor"], 400)
            self.assertEqual(found["parts_s"]["review"], 1000)
            self.assertEqual(found["checks_known_s"], {"bash t.sh": 120})
            self.assertEqual(found["checks_unknown"], ["bash new.sh"])
            self.assertEqual(found["p_red"], 0.5)
            self.assertGreater(found["total_s"], 400 + 1000)

    def test_unfinished_steps_do_not_contribute_time_or_check_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            directory = root / "cnd-interrupted"
            directory.mkdir()
            steps = {"executor.1": {"status": "started", "role": "executor", "duration_s": 100},
                     "checks.1": {"status": "stopped", "result": [{"cmd": "false", "seconds": 100, "green": False}]}}
            (directory / "state.json").write_text(json.dumps({"items": {"W1": {"steps": steps}}}), encoding="utf-8")
            roles, checks, first, red = estimate.history(root)
            self.assertEqual((dict(roles), dict(checks), first, red), ({}, {}, 0, 0))


if __name__ == "__main__":
    unittest.main()
