from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from artifex import cli, store


PLAN_SOURCE = Path(__file__).resolve().parents[3] / "plans" / "2026.08.03-ARTIFEX-SUPERVISOR" / "artifacts/P1/supervisor-run-cases-v1.json"
PLAN = Path(__file__).resolve().parents[3] / "plans" / "2026.08.03-ARTIFEX-SUPERVISOR"
G2 = "ef08406d7ca630d46e9e9e8bca0d10ea73b141d984615bded75f19d7eea13f09"
G2B = "1" * 64


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name) / "repo"; self.repo.mkdir()
        self.plan = self.repo / "plan"; (self.plan / "artifacts/P1").mkdir(parents=True)
        (self.plan / "plan.md").write_text("# plan\n", encoding="utf-8")
        (self.plan / "artifacts/P1/supervisor-run-cases-v1.json").write_bytes(PLAN_SOURCE.read_bytes())
        self.runs = self.plan / "runs"; self.mandate = self.plan / "mandate.json"; self.mandate.write_text("{}", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def call(self, *tail):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = cli.main(["--repo-root", str(self.repo), "--plan-dir", "plan", "--runs-root", "plan/runs", *tail])
        return code, json.loads(stream.getvalue())

    def start(self, run_id="run-1"):
        manifest = {"content_hash": "a" * 64, "source_hashes": {"base_commit": "b" * 64, "plan": "c" * 64}, "plan_id": "plan", "scope": {"validation": ["check"]}}
        with mock.patch("artifex.cli.compiler.compile_slice", return_value=manifest):
            return self.call("start", "--run-id", run_id, "--phase", "P2", "--item", "P2.5", "--mandate", "plan/mandate.json")

    def test_start_status_report_and_idempotent_stop_are_bounded_json(self):
        code, result = self.start()
        self.assertEqual((0, "READY"), (code, result["state"]))
        code, result = self.call("status", "--run-id", "run-1")
        self.assertEqual((0, "READY"), (code, result["state"]))
        code, result = self.call("report", "--run-id", "run-1")
        self.assertEqual((0, True), (code, result["redacted"]))
        code, result = self.call("stop", "--run-id", "run-1")
        self.assertEqual((0, "ABORTED"), (code, result["state"]))
        code, result = self.call("stop", "--run-id", "run-1")
        self.assertEqual((0, True), (code, result["idempotent"]))

    def test_not_found_and_path_escape_refuse_without_writing(self):
        code, result = self.call("status", "--run-id", "missing")
        self.assertEqual((3, "RUN_NOT_FOUND"), (code, result["reason"]))
        code, result = self.call("start", "--run-id", "../escape", "--phase", "P2", "--item", "P2.5", "--mandate", "plan/mandate.json")
        self.assertEqual((2, "RUN_IDENTITY_MISMATCH"), (code, result["reason"]))
        self.assertFalse((self.repo.parent / "escape").exists())

    def test_reconcile_requires_a_durable_intent(self):
        self.start()
        code, result = self.call("reconcile", "--run-id", "run-1", "--observed", "third")
        self.assertEqual((2, "UNRESOLVED_INTENT_MISSING"), (code, result["reason"]))

    def test_dispatch_requires_an_indexed_matching_ready_run(self):
        source_plan = Path(__file__).resolve().parents[3] / "plans" / "2026.08.03-ARTIFEX-SUPERVISOR"
        target = self.repo / "plan"
        import shutil
        shutil.rmtree(target); shutil.copytree(source_plan, target)
        admission = json.loads((target / "artifacts/P2/p3-smoke-admissions/codex.json").read_text(encoding="utf-8"))
        run_id = admission["dispatch"]["run_id"]
        rules, states, events = cli._rules(target)
        self.runs.mkdir()
        run = store.RunStore.create(self.runs, run_id, {
            "schema_version": "supervisor-run-v1", "contract_version": "1.0.0", "run_id": run_id,
            "repository_root_hash": "a" * 64, "base_commit": "b" * 64, "plan_id": "plan",
            "plan_hash": "c" * 64, "mandate_hash": "d" * 64, "acceptance_hash": "e" * 64,
            "created_at": "2026-08-04T00:00:00Z", "redaction_policy_hash": "f" * 64,
        }, rules=rules, states=states, events=events)
        with run.acquire_writer():
            run.append_event(cli._payload(run, "freeze_run"))
        code, result = self.call("dispatch", "--run-id", run_id, "--provider", "claude-code",
                                 "--admission", "plan/artifacts/P2/p3-smoke-admissions/codex.json")
        self.assertEqual((2, "PROVIDER_MISMATCH"), (code, result["reason"]))
        code, result = self.call("dispatch", "--run-id", run_id, "--admission", "plan/artifacts/P2/p3-smoke-admissions/codex.json")
        self.assertEqual((0, "provider_unavailable", 0), (code, result["status"], result["process_count"]))
        code, result = self.call("dispatch", "--run-id", run_id, "--admission", "plan/artifacts/P1/p3-smoke-dispatch-grants-v1.json")
        self.assertEqual((2, "UNKNOWN_SCHEMA_VERSION"), (code, result["reason"]))

    def test_explicit_provider_uses_activity_port_not_default_refusal_port(self):
        source_plan = Path(__file__).resolve().parents[3] / "plans" / "2026.08.03-ARTIFEX-SUPERVISOR"
        target = self.repo / "plan"
        import shutil
        shutil.rmtree(target); shutil.copytree(source_plan, target)
        admission = json.loads((target / "artifacts/P2/p3-smoke-admissions/codex.json").read_text(encoding="utf-8"))
        run_id = admission["dispatch"]["run_id"]
        rules, states, events = cli._rules(target)
        self.runs.mkdir()
        run = store.RunStore.create(self.runs, run_id, {"schema_version": "supervisor-run-v1", "contract_version": "1.0.0", "run_id": run_id,
            "repository_root_hash": "a" * 64, "base_commit": "b" * 64, "plan_id": "plan", "plan_hash": "c" * 64,
            "mandate_hash": "d" * 64, "acceptance_hash": "e" * 64, "created_at": "2026-08-04T00:00:00Z", "redaction_policy_hash": "f" * 64}, rules=rules, states=states, events=events)
        with run.acquire_writer():
            run.append_event(cli._payload(run, "freeze_run"))
        with mock.patch("artifex.cli.scheduler.DefaultActivityPort", side_effect=AssertionError("fallback")):
            code, result = self.call("dispatch", "--run-id", run_id, "--provider", "codex", "--admission", "plan/artifacts/P2/p3-smoke-admissions/codex.json")
        self.assertEqual((0, "provider_unavailable", 0), (code, result["status"], result["process_count"]))


class BusinessDispatchIntentCliTests(unittest.TestCase):
    """D118 CLI wiring: dispatch-business stays validate-only; the new seam runs only on demand."""

    def setUp(self):
        import shutil
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name) / "repo"
        shutil.copytree(PLAN, self.repo / "plan")

    def tearDown(self):
        self.temp.cleanup()

    def call(self, *tail):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = cli.main(["--repo-root", str(self.repo), "--plan-dir", "plan", "--runs-root", "plan/runs", *tail])
        return code, json.loads(stream.getvalue())

    def test_dispatch_business_stays_validate_only_and_never_touches_the_seam(self):
        admission = "plan/artifacts/P5/trial-admissions/p5.2-slice-01-worktree-core.json"
        with mock.patch("artifex.cli.activity.BusinessProviderActivityPort", side_effect=AssertionError("seam touched")):
            code, result = self.call("dispatch-business", "--admission", admission,
                                     "--g2-predecessor", G2, "--g2b-successor", G2B)
        self.assertEqual((0, False), (code, result["intent_written"]))

    def test_dispatch_business_intent_runs_the_seam_and_shapes_the_result(self):
        admission = "plan/artifacts/P5/trial-admissions/p5.2-slice-01-worktree-core.json"
        cwd = self.repo / "worktree"; cwd.mkdir()
        fake_port = mock.Mock()
        fake_port.run.return_value = {"kind": "success", "reason_code": "OK", "process_count": 1}
        with mock.patch("artifex.cli.activity.BusinessProviderActivityPort", return_value=fake_port) as ctor:
            code, result = self.call("dispatch-business-intent", "--admission", admission,
                                     "--g2-predecessor", G2, "--g2b-successor", G2B, "--cwd", str(cwd))
        self.assertEqual((0, True), (code, result["intent_written"]))
        self.assertEqual("p5.2-slice-01-worktree-core", result["trial_id"])
        fake_port.run.assert_called_once_with(cwd=cwd.resolve(), binary=None)
        ctor.assert_called_once()

    def test_dispatch_business_intent_refuses_pin_mismatch_before_touching_the_seam(self):
        admission = "plan/artifacts/P5/trial-admissions/p5.2-slice-01-worktree-core.json"
        cwd = self.repo / "worktree"; cwd.mkdir()
        with mock.patch("artifex.cli.activity.BusinessProviderActivityPort", side_effect=AssertionError("seam touched")):
            code, result = self.call("dispatch-business-intent", "--admission", admission,
                                     "--g2-predecessor", "0" * 64, "--g2b-successor", G2B, "--cwd", str(cwd))
        self.assertEqual((2, "G2_PREDECESSOR_MISMATCH"), (code, result["reason"]))
