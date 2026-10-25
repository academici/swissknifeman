"""``bridge planner-orch launch``: class→model through planner mappings, scout parity with planner's own scout config."""
from __future__ import annotations

import json
import importlib.util
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from unittest import mock

import bridge_fixture
import partners

ORCH = partners.find_orch_root()
ROUTING = bridge_fixture.PLANNER / "configs" / "command-routing.json"


def launch(*args: str) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as tmp:
        return bridge_fixture.plan_py(tmp, "bridge", "planner-orch", "launch", *args)


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
                expected = [re.sub(r"\{(\w+)\}", lambda m, values=values: values[m[1]], arg) for arg in entry["argv"]]
                # The catalog adds --permission-prompts none to every headless claude-code role (PLAN4.P1.4); the
                # planner's legacy scout list predates it, so the pair is the only allowed difference.
                if provider == "claude-code":
                    expected[-1:-1] = ["--permission-prompts", "none"]
                if provider == "grok":
                    # P6.3 removes the implicit Grok home grant from every ro-run command.
                    expected[expected.index("--"):expected.index("--")] = ["--rw", "~/.grok"]
                self.assertEqual(out["argv"], expected)
                self.assertEqual(out["model"], entry["model"])
                self.assertEqual(out["timeout_s"], entry["timeout_s"])
                self.assertEqual(out["transport"], "text")

    def test_scout_literals(self):
        out = json.loads(launch("scout", "claude-code").stdout)
        self.assertEqual(out["argv"], ["claude", "-p", "--model", "haiku", "--effort", "low", "--tools",
                                       "Read,Grep,Glob", "--permission-prompts", "none",
                                       "--no-session-persistence"])
        self.assertEqual(json.loads(launch("scout", "codex").stdout)["model"], "gpt-6-luna")

    def test_class_resolves_by_role(self):
        out = json.loads(launch("executor", "claude-code", "--effort", "xhigh").stdout)
        self.assertEqual((out["model"], out["model_class"]), ("sonnet", "implementation"))
        self.assertEqual(out["argv"][out["argv"].index("--effort") + 1], "xhigh")
        self.assertEqual(json.loads(launch("bounded-implementer", "codex").stdout)["model"], "gpt-6-luna")

    def test_grok_writer_model_is_mapped_or_overridden_and_uses_jsonl(self):
        for role in ("executor", "bounded-implementer"):
            with self.subTest(role=role):
                done = launch(role, "grok", "--cwd", "/work")
                self.assertEqual(done.returncode, 0, done.stderr)
                out = json.loads(done.stdout)
                self.assertEqual(out["transport"], "jsonl")
                argv = out["argv"]
                self.assertTrue(argv[1].endswith("/scripts/ro-run.py"))
                self.assertEqual(argv[2:7], ["--rw", "/work", "--rw", "~/.grok", "--"])
                self.assertEqual(argv[argv.index("--model") + 1], out["model"])
                pinned = launch(role, "grok", "--model", "grok-x")
                self.assertEqual(pinned.returncode, 0, pinned.stderr)
                self.assertEqual(json.loads(pinned.stdout)["model"], "grok-x")

    def test_owner_selector_model_replaces_the_class_mapping(self):
        done = launch("reviewer", "grok", "--model", "grok-4.7", "--effort", "high", "--cwd", "/work")
        self.assertEqual(done.returncode, 0, done.stderr)
        out = json.loads(done.stdout)
        argv = out["argv"]
        self.assertEqual((out["model"], out["transport"]), ("grok-4.7", "jsonl"))
        self.assertEqual(argv[argv.index("--model") + 1], "grok-4.7")
        self.assertEqual(argv[argv.index("--effort") + 1], "high")
        self.assertEqual(argv[argv.index("--") - 4:argv.index("--")], ["--rw", "/work/vendor", "--rw", "~/.grok"])
        self.assertTrue(argv[1].endswith("/scripts/ro-run.py"))
        self.assertEqual(argv[2:4], ["--protect", "/work"])

    def test_unknown_model_set_takes_no_model_argument_with_synthetic_acp(self):
        spec = importlib.util.spec_from_file_location("launch_bridge", Path(__file__).resolve().parents[1] / "launch.py")
        bridge = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bridge)
        entry = {"model_class": "implementation", "effort": "high", "model_set": "unknown", "transport": "acp",
                 "argv": ["grok", "agent", "stdio"], "timeout_s": 3600}
        def orch(*args):
            if args[0] == "show":
                return entry
            self.assertEqual(args[0], "argv")
            self.assertNotIn("--model", args)
            return {key: entry[key] for key in ("argv", "transport", "timeout_s")}
        with mock.patch.object(bridge, "_orch", side_effect=orch):
            out = bridge.build("executor", "grok", effort=None, cwd="/work", routing=ROUTING)
            self.assertEqual(out["argv"], ["grok", "agent", "stdio"])
            self.assertEqual(out["transport"], "acp")
            with self.assertRaises(bridge.LaunchRefused) as raised:
                bridge.build("executor", "grok", model="grok-x", effort=None, cwd="/work", routing=ROUTING)
            self.assertTrue(str(raised.exception).startswith("LAUNCH_INVALID:"))

    def test_refusals(self):
        done = launch("registrar", "grok")
        self.assertEqual(done.returncode, 1)
        self.assertTrue(done.stderr.startswith("LAUNCH_REFUSED: registrar/grok:"), done.stderr)
        unknown = launch("janitor", "codex")
        self.assertEqual(unknown.returncode, 1)
        self.assertTrue(unknown.stderr.startswith("LAUNCH_UNKNOWN:"), unknown.stderr)

    def test_grok_scout_is_plain_text_and_protects_the_checkout(self):
        done = launch("scout", "grok", "--cwd", "/work")
        self.assertEqual(done.returncode, 0, done.stderr)
        out = json.loads(done.stdout)
        self.assertEqual((out["transport"], out["timeout_s"], out["model_class"]), ("text", 300, "economy"))
        argv = out["argv"]
        self.assertEqual(argv[:argv.index("--")], ["python3", str(ORCH / "scripts/ro-run.py"), "--protect", "/work",
                                                   "--rw", "~/.grok"])
        self.assertEqual(argv[argv.index("--output-format") + 1], "plain")
        self.assertEqual(argv[argv.index("--model") + 1], out["model"])
        self.assertIn("--disable-web-search", argv)

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
        with tempfile.TemporaryDirectory() as tmp:
            done = bridge_fixture.plan_py(tmp, "bridge", "list")
        self.assertIn("launch", done.stdout)


if __name__ == "__main__":
    unittest.main()
