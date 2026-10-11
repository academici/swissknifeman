"""``orch.py prepare`` chooses the engine from the configuration; ``orch.py explain`` reads a launch-plan."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from orch.cli import main

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "fixtures" / "exec" / "v1" / "valid" / "execution-input" / "plan-bound.json"
POLICY = ROOT / "configs" / "run-policies" / "solo" / "policy.json"
MODEL_CATALOG = ROOT / "fixtures" / "model-catalog" / "test.json"
SKILL = {"name": "code-review", "digest": "sha256:" + "cd" * 32}


class CliCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        home = self.root / "home"
        (home / "skm").mkdir(parents=True)
        patcher = mock.patch.dict(os.environ, {"HOME": str(home), "SKM_HOME": str(home / "skm")})
        patcher.start()
        self.addCleanup(patcher.stop)
        cwd = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, cwd)

    def run_cli(self, *argv: str) -> tuple:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main([str(item) for item in argv])
        return code, out.getvalue(), err.getvalue()

    def config(self, text: str) -> Path:
        path = self.root / "invocation.toml"
        path.write_text("schema_version = 1\n" + text, encoding="utf-8")
        return path

    def prepare(self, *extra, provider="claude-code", config=None) -> tuple:
        head = ["--config", config] if config else []
        return self.run_cli(*head, "prepare", "--provider", provider, "--input", INPUT, "--policy", POLICY,
                            "--out", self.root / "out", "--dry-run", "--model-catalog", MODEL_CATALOG, *extra)

    def plan(self, *extra, **kwargs) -> dict:
        code, out, err = self.prepare(*extra, **kwargs)
        self.assertEqual((code, err), (0, ""), out)
        return json.loads(out)

    def binding_decision(self, plan: dict) -> dict:
        return next(item for item in plan["decisions"] if item["kind"] == "binding")


class PrepareEngine(CliCase):
    def test_the_configuration_chooses_the_engine_without_a_flag(self):
        plan = self.plan()
        self.assertEqual(plan["binding"], "native")
        self.assertEqual(self.binding_decision(plan)["considered"][0]["reason_codes"], ["ENGINE_FROM_CONFIG"])
        self.assertEqual(self.plan(config=self.config('[orch]\nengine = "claude-only"\n'))["binding"], "claude-only")

    def test_engine_by_role_uses_the_primary_role(self):
        plan = self.plan(config=self.config('[orch]\nengine = "native"\n[orch.engine_by_role]\nexecutor = "claude-only"\n'))
        decision = self.binding_decision(plan)
        self.assertEqual(plan["binding"], "claude-only")
        self.assertEqual([(c["candidate"], c["accepted"], c["reason_codes"]) for c in decision["considered"]],
                         [("claude-only", True, ["ENGINE_FROM_ROLE"]), ("native", False, ["ENGINE_OVERRIDDEN"])])

    def test_the_flag_wins(self):
        plan = self.plan("--binding", "native", config=self.config('[orch]\nengine = "claude-only"\n'))
        self.assertEqual(plan["binding"], "native")
        self.assertEqual(self.binding_decision(plan)["considered"][0]["reason_codes"], ["ENGINE_FROM_FLAG"])

    def test_the_configuration_is_recorded_once_in_the_plan(self):
        plan = self.plan(config=self.config('[orch]\nengine = "claude-only"\n'))
        self.assertEqual(plan["config"]["values"]["engine"], "claude-only")
        self.assertNotEqual(plan["config"]["digest"], self.plan()["config"]["digest"])

    def test_a_missing_capability_is_a_refusal_not_another_engine(self):
        # claude-only has no capability record for codex; native has one, but it is never substituted.
        code, out, err = self.prepare(provider="codex", config=self.config('[orch]\nengine = "claude-only"\n'))
        self.assertEqual(code, 1)
        self.assertTrue(err.startswith("CAPABILITY_UNSUPPORTED"), err)
        refused = json.loads(out)
        self.assertEqual((refused["binding"], refused["stages"]), ("claude-only", []))
        self.assertEqual(refused["policy_decision"]["decision"], "refuse")
        self.assertEqual([item["reason_code"] for item in refused["refusals"]], ["CAP_RECORD_MISSING"])
        self.assertEqual(self.binding_decision(refused)["chosen"], "claude-only")

    def test_an_invalid_configuration_is_reported(self):
        code, out, err = self.prepare(config=self.config('[orch]\nengine = "nope"\n'))
        self.assertEqual((code, out), (1, ""))
        self.assertTrue(err.startswith("CONFIG_INVALID"), err)

    def test_prepare_still_needs_dry_run(self):
        code, _, err = self.run_cli("prepare", "--input", INPUT, "--policy", POLICY, "--out", self.root / "out")
        self.assertEqual(code, 1)
        self.assertTrue(err.startswith("NOT_IMPLEMENTED"), err)
        self.assertFalse((self.root / "out").exists())


class PrepareOptions(CliCase):
    def test_submission_id(self):
        self.assertEqual(self.plan("--submission-id", "sub-1")["submission_id"], "sub-1")
        self.assertNotIn("submission_id", self.plan())

    def test_submission_id_equal_to_the_run_id_is_refused(self):
        run_id = "dry-" + json.loads(INPUT.read_text(encoding="utf-8"))["digest"][:12]
        code, out, err = self.prepare("--submission-id", run_id)
        self.assertEqual((code, out), (1, ""))
        self.assertIn("KEY_REUSED", err)

    def test_skills_file_reaches_the_delivery(self):
        path = self.root / "skills.json"
        path.write_text(json.dumps({"executor": [SKILL]}), encoding="utf-8")
        (stage,) = self.plan("--skills", path)["stages"]
        self.assertEqual(stage["delivery"]["skills"], [SKILL])

    def test_skills_file_must_map_roles_to_lists(self):
        path = self.root / "skills.json"
        path.write_text(json.dumps({"executor": SKILL}), encoding="utf-8")
        code, out, err = self.prepare("--skills", path)
        self.assertEqual((code, out), (1, ""))
        self.assertTrue(err.startswith("INPUT_INVALID"), err)
        for text in ("[]", '{"executor": [1]}', '"x"', '{"executor": {"name": "a"}}'):
            path.write_text(text, encoding="utf-8")
            with self.subTest(skills=text):
                code, out, err = self.prepare("--skills", path)
                self.assertEqual((code, out), (1, ""))
                self.assertTrue(err.startswith("INPUT_INVALID"), err)
        code, _, err = self.prepare("--skills", self.root / "absent.json")
        self.assertEqual(code, 1)
        self.assertTrue(err.startswith("INPUT_INVALID"), err)

    def test_model_catalog_digest_follows_the_file(self):
        other = json.loads(MODEL_CATALOG.read_text(encoding="utf-8"))
        other["catalog_version"] = "2.0.0"
        path = self.root / "models.json"
        path.write_text(json.dumps(other), encoding="utf-8")
        before = self.plan()["digests"]
        after = self.plan("--model-catalog", path)["digests"]
        self.assertEqual([key for key in before if before[key] != after[key]], ["model_catalog"])


class Explain(CliCase):
    def write_plan(self, *extra, **kwargs) -> Path:
        path = self.root / "launch-plan.json"
        path.write_text(json.dumps(self.plan(*extra, **kwargs)), encoding="utf-8")
        return path

    def test_json_has_the_documented_keys(self):
        path = self.write_plan()
        code, out, err = self.run_cli("explain", path, "--json")
        self.assertEqual((code, err), (0, ""))
        found = json.loads(out)
        self.assertEqual(list(found), ["binding", "decisions", "stages", "refusals", "digests", "config",
                                       "policy_decision", "warnings"])
        self.assertEqual(found["binding"], "native")
        self.assertEqual(found["policy_decision"]["decision"], "allow")
        self.assertEqual(found["digests"], json.loads(path.read_text(encoding="utf-8"))["digests"])
        self.assertTrue(found["decisions"] and found["config"]["values"]["engine"] == "native")

    def test_text_says_engine_route_digests_and_decision(self):
        path = self.write_plan(config=self.config('[orch]\nengine = "native"\n[orch.engine_by_role]\nexecutor = "native"\n'))
        code, out, err = self.run_cli("explain", path)
        self.assertEqual((code, err), (0, ""))
        for text in ("engine: native (ENGINE_FROM_ROLE)", "primary: role executor, claude-code, m-mid, high",
                     "primary: chosen claude-code/m-mid (tie-break policy-order)", "claude-code: accepted",
                     "  input: ", "  model_catalog: ", "engine = \"native\"", "policy decision: allow",
                     "warnings:\n  (none)"):
            self.assertIn(text, out)

    def test_text_lists_refusals_with_their_chain(self):
        code, out, _ = self.prepare(provider="codex", config=self.config('[orch]\nengine = "claude-only"\n'))
        self.assertEqual(code, 1)
        refused = json.loads(out)
        refused["refusals"][0]["chain"].append({"capability": "stream", "reason": "stream is unsupported"})
        path = self.root / "refused.json"
        path.write_text(json.dumps(refused), encoding="utf-8")
        code, text, err = self.run_cli("explain", path)
        self.assertEqual((code, err), (0, ""))
        self.assertIn("primary: model.set: ", text)
        self.assertIn("[CAP_RECORD_MISSING]", text)
        self.assertIn("    because stream: stream is unsupported", text)
        self.assertIn("codex: refused (CAP_RECORD_MISSING)", text)
        self.assertIn("policy decision: refuse (CAP_RECORD_MISSING)", text)

    def test_text_shows_warnings(self):
        plan = self.plan()
        plan["proof"]["warnings"].append({"code": "CAPABILITY_STALE", "message": "record is old"})
        path = self.root / "warned.json"
        path.write_text(json.dumps(plan), encoding="utf-8")
        self.assertIn("  CAPABILITY_STALE: record is old", self.run_cli("explain", path)[1])

    def test_explain_writes_nothing(self):
        path = self.write_plan()
        before = sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob("*"))
        self.run_cli("explain", path)
        self.run_cli("explain", path, "--json")
        self.assertEqual(sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob("*")), before)

    def test_an_invalid_launch_plan_is_refused(self):
        path = self.root / "bad.json"
        path.write_text(json.dumps({"binding": "native"}), encoding="utf-8")
        code, out, err = self.run_cli("explain", path)
        self.assertEqual((code, out), (1, ""))
        self.assertIn("CONTRACT_VERSION", err)

    def test_an_unreadable_launch_plan_is_refused(self):
        code, out, err = self.run_cli("explain", self.root / "absent.json")
        self.assertEqual((code, out), (1, ""))
        self.assertTrue(err.startswith("INPUT_INVALID"), err)

    def test_a_plan_without_the_new_sections_still_explains(self):
        plan = self.plan()
        for key in ("digests", "config", "modules", "decisions", "policy_decision", "proof", "digest"):
            plan.pop(key)
        path = self.root / "old.json"
        path.write_text(json.dumps(plan), encoding="utf-8")
        code, out, err = self.run_cli("explain", path, "--json")
        self.assertEqual((code, err), (0, ""))
        found = json.loads(out)
        self.assertEqual((found["decisions"], found["digests"], found["policy_decision"]), ([], {}, None))
        self.assertEqual(self.run_cli("explain", path)[0], 0)


if __name__ == "__main__":
    unittest.main()
