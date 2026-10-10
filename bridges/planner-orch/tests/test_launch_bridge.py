"""``bridge planner-orch launch``: class→model through planner mappings, scout parity with planner's own scout config."""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

import bridge_fixture
import partners

ORCH = partners.find_orch_root()
ROUTING = bridge_fixture.PLANNER / "configs" / "command-routing.json"


def launch(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(bridge_fixture.PLAN_PY), "bridge", "planner-orch", "launch", *args],
                          capture_output=True, text=True, encoding="utf-8", check=False)


@unittest.skipUnless(ORCH, "orch partner not found")
class LaunchBridge(unittest.TestCase):
    def test_scout_argv_equals_task_scout_config(self):
        legacy = json.loads(ROUTING.read_text(encoding="utf-8"))["orchestration"]["scout"]
        for provider, entry in legacy.items():
            with self.subTest(provider=provider):
                done = launch("scout", provider, "--cwd", "/work")
                self.assertEqual(done.returncode, 0, done.stderr)
                out = json.loads(done.stdout)
                values = {"model": entry["model"], "effort": entry["effort"], "cwd": "/work"}
                expected = [re.sub(r"\{(\w+)\}", lambda m: values[m[1]], arg) for arg in entry["argv"]]
                self.assertEqual(out["argv"], expected)
                self.assertEqual(out["model"], entry["model"])
                self.assertEqual(out["timeout_s"], entry["timeout_s"])
                self.assertEqual(out["transport"], "text")

    def test_scout_literals(self):
        out = json.loads(launch("scout", "claude-code").stdout)
        self.assertEqual(out["argv"], ["claude", "-p", "--model", "haiku", "--effort", "low", "--tools", "",
                                       "--no-session-persistence"])
        self.assertEqual(json.loads(launch("scout", "codex").stdout)["model"], "gpt-5.6-luna")

    def test_class_resolves_by_role(self):
        out = json.loads(launch("executor", "claude-code", "--effort", "xhigh").stdout)
        self.assertEqual((out["model"], out["model_class"]), ("sonnet", "implementation"))
        self.assertEqual(out["argv"][out["argv"].index("--effort") + 1], "xhigh")
        self.assertEqual(json.loads(launch("bounded-implementer", "codex").stdout)["model"], "gpt-5.6-luna")

    def test_unknown_model_set_takes_no_model_argument(self):
        out = json.loads(launch("executor", "grok").stdout)
        self.assertEqual(out["argv"], ["grok", "agent", "stdio"])
        refused = launch("executor", "grok", "--model", "grok-x")
        self.assertEqual(refused.returncode, 1)
        self.assertTrue(refused.stderr.startswith("LAUNCH_INVALID:"), refused.stderr)

    def test_owner_selector_model_replaces_the_class_mapping(self):
        done = launch("reviewer", "grok", "--model", "grok-4.7", "--effort", "high", "--cwd", "/work")
        self.assertEqual(done.returncode, 0, done.stderr)
        out = json.loads(done.stdout)
        argv = out["argv"]
        self.assertEqual((out["model"], out["transport"]), ("grok-4.7", "jsonl"))
        self.assertEqual(argv[argv.index("--model") + 1], "grok-4.7")
        self.assertEqual(argv[argv.index("--effort") + 1], "high")
        self.assertEqual(argv[argv.index("--") - 2:argv.index("--")], ["--rw", "/work/vendor"])
        self.assertTrue(argv[1].endswith("/scripts/ro-run.py"))

    def test_refusals(self):
        done = launch("scout", "grok")
        self.assertEqual(done.returncode, 1)
        self.assertTrue(done.stderr.startswith("LAUNCH_UNKNOWN:"), done.stderr)
        self.assertEqual(launch("janitor", "codex").returncode, 1)

    def test_provider_without_model_for_class_is_refused(self):
        routing = json.loads(ROUTING.read_text(encoding="utf-8"))
        del routing["mappings"]["codex"]["class_selectors"]["economy"]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "routing.json"
            path.write_text(json.dumps(routing), encoding="utf-8")
            done = launch("scout", "codex", "--routing", str(path))
        self.assertEqual(done.returncode, 1)
        self.assertTrue(done.stderr.startswith("LAUNCH_MODEL_UNRESOLVED:"), done.stderr)

    def test_dispatcher_lists_launch(self):
        done = subprocess.run([sys.executable, str(bridge_fixture.PLAN_PY), "bridge", "list"], capture_output=True,
                              text=True, encoding="utf-8", check=False)
        self.assertIn("launch", done.stdout)


if __name__ == "__main__":
    unittest.main()
