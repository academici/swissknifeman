"""Public ``source prepare`` binds the loaded pack. The conductor projects skipped stages on its own path."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from orch import journal, policies
from orch.cli import main

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "configs" / "run-policies" / "solo" / "policy.json"
INPUT = ROOT / "fixtures" / "exec" / "v1" / "valid" / "execution-input" / "plan-bound.json"
MODEL_CATALOG = ROOT / "fixtures" / "model-catalog" / "test.json"
FAKE = ROOT / "tests" / "fixtures" / "work-source" / "fake"


def _with_side(found: dict, role: str) -> dict:
    stages = list(found.get("stages") or [])
    stages.append({"id": "side", "kind": "bounded", "role": role, "required": False,
                   "on_unavailable": "skip", "model_class": "economy"})
    return {**found, "stages": stages}


class PublicSourcePrepareTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.home, self.project = base / "home", base / "project"
        (self.project / ".git").mkdir(parents=True)
        config = self.home / "skm" / "config" / "config.toml"
        config.parent.mkdir(parents=True)
        config.write_text(
            "schema_version = 1\n\n[orch]\nwork_source = \"fake-source\"\n\n"
            "[aicore.plugins.fake-source]\n"
            f"manifest = {json.dumps(str(FAKE / 'extension.json'))}\ntrusted = true\n",
            encoding="utf-8")
        env = {"HOME": str(self.home), "SKM_HOME": str(self.home / "skm"), "SKM_AICORE_EVENTS__DELIVERY": "off",
               "FAKE_WS_MODE": "ok", "FAKE_WS_INPUT": str(INPUT), "FAKE_WS_MARKS": str(base / "marks.jsonl")}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        cwd = Path.cwd()
        os.chdir(self.project)
        self.addCleanup(os.chdir, cwd)

    def cli(self, *argv) -> tuple:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main([str(item) for item in argv])
        return code, out.getvalue(), err.getvalue()

    def prepare(self, role: str):
        code, out, err = self.cli("source", "claim", "--plan", "P", "--actor", "claude-code/claude-opus-5-5/high")
        self.assertEqual((code, err), (0, ""), out)
        run_id = json.loads(out)["run_id"]
        code, brief, err = self.cli("source", "brief", "--run", run_id)
        self.assertEqual((code, err), (0, ""), brief)
        real = policies.load

        def load(policy_id, *args, **kwargs):
            return _with_side(real(policy_id, *args, **kwargs), role)

        before = PACK.read_bytes()
        with mock.patch.object(policies, "load", load):
            code, out, err = self.cli("source", "prepare", "--run", run_id, "--provider", "claude-code",
                                      "--binding", "native", "--model-catalog", str(MODEL_CATALOG))
        self.assertEqual(PACK.read_bytes(), before)
        return run_id, code, out, err

    def test_an_available_optional_bounded_stage_stays_in_the_launch_plan(self):
        run_id, code, out, err = self.prepare("bounded-implementer")
        self.assertEqual((code, err), (0, ""), out)
        plan = json.loads(out)
        self.assertIn("bounded-implementer", [stage["role"] for stage in plan["stages"]])
        directory = journal.run_dir(run_id, project=self.project)
        self.assertEqual(journal.read_doc(directory, "launch-plan.json"), plan)
        self.assertEqual(journal.read_doc(directory, "run.json")["scenario"], "solo")

    def test_an_unknown_optional_role_is_role_unknown(self):
        run_id, code, out, err = self.prepare("plan9-uninstalled-side-role")
        self.assertEqual(code, 1, out)
        self.assertTrue(err.startswith("ROLE_UNKNOWN:"), err)
        self.assertIsNone(journal.read_doc(journal.run_dir(run_id, project=self.project), "launch-plan.json"))


if __name__ == "__main__":
    unittest.main()
