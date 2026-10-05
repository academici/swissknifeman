"""Negative acceptance cases from the 2026-10-04 roadmap audit."""
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

try:
    from .fixtures import item_spec_md, write_valid_plan
except ImportError:
    from fixtures import item_spec_md, write_valid_plan

from task import (command_render, evidence_runner, journal, plan_completion,
                  plan_delivery, plan_item_state, plan_lint, plan_reconcile, plan_status,
                  plan_work, review_packet, review_sources, terminal_policy, file_manifest)


class RoadmapFollowupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.plan = write_valid_plan(self.root, "FOLLOWUP")
        rows = journal.read_authoritative_entries(self.plan)
        for row in rows:
            if row["item_id"] == "P1.1" and row["result"] == "closed-green":
                row["decision"] = terminal_policy.build_decision(self.plan, "P1.1", result="closed-green",
                    validation=[{"carrier": "tests", "status": "green", "evidence_ids": ["test:green"]}])
        (self.plan / "journal.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
        for argv in (("init", "-q"), ("add", "."),
                     ("-c", "user.name=Test", "-c", "user.email=test@example.test", "commit", "-qm", "baseline")):
            subprocess.run(["git", "-C", str(self.root), *argv], check=True, capture_output=True)

    def test_whole_plan_close_is_idempotent_and_leaves_phase_history_unchanged(self):
        before = journal.read_authoritative_entries(self.plan)
        result = plan_completion.close(self.plan, actor="implementation/high", session_id="owner-session")
        first = (self.plan / "journal.jsonl").read_bytes()
        repeated = plan_completion.close(self.plan, actor="implementation/high", session_id="owner-session")
        self.assertEqual(first, (self.plan / "journal.jsonl").read_bytes())
        self.assertEqual(result["candidate_sha256"], repeated["candidate_sha256"])
        self.assertEqual(result["receipt"]["subject"], "plan")
        self.assertEqual(result["receipt"]["next_exact"], "terminal: plan closed")
        self.assertEqual([row for row in journal.read_authoritative_entries(self.plan) if row["item_id"] != "plan"], before)
        self.assertFalse((self.plan / "phases/P1/P1.closed.md").exists())
        plan_delivery.verify_receipt(self.plan, result["receipt"])

    def test_unfinished_plan_cannot_close_and_phase_targets_are_rejected(self):
        (self.plan / "phases/P1/P1.2.md").write_text(item_spec_md("P1.2"))
        plan_item_state.build_states(self.plan, item_id="P1.2", materialize_successor=False)
        before = (self.plan / "journal.jsonl").read_bytes()
        with self.assertRaises(ValueError):
            plan_completion.close(self.plan, actor="implementation/high", session_id="owner-session")
        self.assertEqual((self.plan / "journal.jsonl").read_bytes(), before)
        self.assertEqual(plan_completion.successor(self.plan), "run-items: task:plan-run FOLLOWUP P1.2")
        for target in ("P1", "P1.1"):
            with self.assertRaisesRegex(ValueError, "PLAN_CLOSE_WHOLE_PLAN_ONLY"):
                command_render.parse_next_carrier("close: task:plan-close FOLLOWUP " + target)

    def test_missing_red_stale_phase_validation_blocks_without_new_phase_lifecycle(self):
        phase = self.plan / "phases/P1/P1.md"
        phase.write_text(phase.read_text() + "\n## Validation\n\n- external CI approval O-3-CI\n")
        evidence = self.plan / "artifacts/ci.log"
        evidence.parent.mkdir(exist_ok=True)
        evidence.write_text("authorized CI, exit 0\n")
        fingerprint = plan_completion.phase_acceptance
        with self.assertRaisesRegex(ValueError, "PLAN_ACCEPTANCE_REQUIRED"):
            fingerprint(self.plan, "P1")
        from task import plan_gates
        candidate = plan_gates.phase_candidate_fingerprint(self.plan, "P1")
        value = {"schema_version": "plan-acceptance/v1", "plan_id": self.plan.name, "subject": "P1",
                 "candidate_sha256": candidate["fingerprint"],
                 "validation_sha256": hashlib.sha256(b"- external CI approval O-3-CI").hexdigest(),
                 "checks": [{"requirement": "external CI approval O-3-CI", "status": "green",
                             "path": "artifacts/ci.log", "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest()}]}
        target = self.plan / "acceptance/P1.json"
        target.parent.mkdir()
        target.write_text(json.dumps(value))
        fingerprint(self.plan, "P1")
        evidence.write_text("changed evidence\n")
        with self.assertRaisesRegex(ValueError, "PLAN_ACCEPTANCE_REQUIRED"):
            fingerprint(self.plan, "P1")
        evidence.write_text("authorized CI, exit 0\n")
        value["checks"][0]["status"] = "red"
        target.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "PLAN_ACCEPTANCE_REQUIRED"):
            fingerprint(self.plan, "P1")
        self.assertFalse((self.plan / "phases/P1/P1.closed.md").exists())

    def test_scoped_lint_keeps_future_budget_visible_and_current_producer_gating(self):
        diag = plan_lint.Diagnostics(selected_items={"P4.2", "P4.3"})
        diag.error(self.plan / "plan.md", None, "read-budget-v1: item P4.5: weight 101871 > threshold 100000 evaluation tokens")
        diag.error(self.plan / "bundles/P4.6.json", None, "bundle-v1: stale bundle")
        self.assertTrue(diag.ok)
        self.assertEqual(len(diag.warnings), 2)
        diag.error(self.plan / "bundles/P4.2.json", None, "bundle-v1: stale producer")
        diag.error(self.plan / "plan.md", None, "read-budget-v1: missing calibration")
        self.assertEqual(len(diag.errors), 2)
        fleet = plan_lint.Diagnostics()
        fleet.error(self.plan / "plan.md", None, "read-budget-v1: item P4.5: weight 101871 > threshold 100000 evaluation tokens")
        self.assertFalse(fleet.ok)

    def test_evidence_runner_orders_dependencies_binds_candidate_and_preserves_attempts(self):
        product = self.root / "product.py"
        product.write_text("value = 1\n")
        directory = self.root / "validation-output"
        checks = [{"id": "generate", "argv": [sys.executable, "-c", "print('generator finished')"], "depends_on": []},
                  {"id": "lint", "argv": [sys.executable, "-c", "print('lint finished')"], "depends_on": ["generate"]}]
        result = evidence_runner.run(self.root, directory, paths=["product.py"], checks=checks, attempt_id="first")
        self.assertTrue(result["complete"])
        receipt = Path(result["receipt"])
        before = receipt.read_bytes()
        with self.assertRaisesRegex(ValueError, "EVIDENCE_ATTEMPT_EXISTS"):
            evidence_runner.run(self.root, directory, paths=["product.py"], checks=checks, attempt_id="first")
        self.assertEqual(receipt.read_bytes(), before)
        digest = result["candidate_sha256"]
        busy = directory / digest / "busy"
        busy.mkdir()
        with (busy / ".lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            with self.assertRaisesRegex(ValueError, "EVIDENCE_WRITER_BUSY"):
                evidence_runner.run(self.root, directory, paths=["product.py"], checks=checks, attempt_id="busy")
        checks[0]["argv"] = [sys.executable, "-c", "raise SystemExit(1)"]
        result = evidence_runner.run(self.root, directory, paths=["product.py"], checks=checks, attempt_id="failed")
        self.assertFalse(result["complete"])
        self.assertEqual(result["results"]["lint"]["status"], "dependency-failed")

    def test_evidence_runner_never_publishes_old_candidate_as_new_green(self):
        product = self.root / "product.py"
        product.write_text("value = 1\n")
        result = evidence_runner.run(self.root, self.root / "output", paths=["product.py"], attempt_id="changed",
            checks=[{"id": "tests", "argv": [sys.executable, "-c",
                "from pathlib import Path; Path('product.py').write_text('value = 2\\n')"], "depends_on": []}])
        self.assertFalse(result["complete"])
        self.assertFalse(json.loads(Path(result["receipt"]).read_text())["candidate_fresh"])

    def test_plan_close_resumes_interrupted_terminal_append_without_duplicate_start(self):
        original = journal._append_locked
        def interrupt(root, event, rows, **kwargs):
            if event["result"] == "closed-green":
                raise OSError("simulated interrupted terminal append")
            return original(root, event, rows, **kwargs)
        with patch.object(journal, "_append_locked", side_effect=interrupt), self.assertRaises(OSError):
            plan_completion.close(self.plan, actor="implementation/high", session_id="owner-session")
        plan_completion.close(self.plan, actor="implementation/high", session_id="owner-session")
        rows = [row for row in journal.read_authoritative_entries(self.plan) if row["item_id"] == "plan"]
        self.assertEqual([row["result"] for row in rows], ["in-progress", "closed-green"])
        self.assertEqual(rows[0]["run_id"], rows[1]["run_id"])

    def test_whole_plan_requires_all_declared_phases_and_no_unresolved_blocked_work(self):
        core = self.plan / "plan.md"
        original = core.read_text()
        core.write_text(original + "\n| P2 | missing phase | 0/1 | ⬜ Not started |\n")
        with self.assertRaisesRegex(ValueError, "PLAN_NOT_COMPLETE"):
            plan_completion.candidate(self.plan)
        core.write_text(original)
        journal.append(self.plan, journal.new_entry(plan_id=self.plan.name, item_id="P1.1", command="plan-run",
            actor="test/high", result="blocked", note="unresolved external authority",
            decision={"signal_class": "authority", "scope_class": "item", "action": "terminal-block",
                      "recovered": False, "terminal": True, "reason_code": "external-authority",
                      "evidence_ids": ["owner:permission-missing"]}))
        plan_item_state.build_states(self.plan, item_id="P1.1", materialize_successor=False)
        with self.assertRaises(ValueError):
            plan_completion.candidate(self.plan)

    def test_single_complete_operation_resumes_views_without_duplicate_terminal(self):
        journal.append(self.plan, journal.new_entry(plan_id=self.plan.name, item_id="P1.1", command="plan-run",
            actor="test/high", result="in-progress", session_id="s", run_id="run-complete", attempt=2))
        decision = terminal_policy.build_decision(self.plan, "P1.1", result="closed-green",
            validation=[{"carrier": "tests", "status": "green", "evidence_ids": ["test:green"]}])
        event = journal.new_entry(plan_id=self.plan.name, item_id="P1.1", command="plan-run",
            actor="test/high", result="closed-green", session_id="s", run_id="run-complete", attempt=2, decision=decision)
        with patch.object(plan_reconcile.plan_status, "build_status", side_effect=OSError("interrupted")):
            with self.assertRaises(plan_reconcile.ReconciliationError):
                plan_work.complete(self.plan, "P1.1", event)
        history = (self.plan / "journal.jsonl").read_bytes()
        result = plan_work.complete(self.plan, "P1.1", event)
        self.assertEqual(history, (self.plan / "journal.jsonl").read_bytes())
        self.assertEqual(result["receipt"]["next_exact"], "close: task:plan-close FOLLOWUP")
        self.assertTrue((self.plan / ".plan-cache/P1.1-terminal-delivery-receipt.json").is_file())
        self.assertFalse((self.plan / "phases/P1/P1.closed.md").exists())

    def test_recursive_tombstones_and_glob_candidate_members_are_not_omitted(self):
        self.assertTrue(file_manifest._matches("tests/root.py", "tests/**/*.py"))
        self.assertTrue(file_manifest._matches("tests/deep/nested/test.py", "tests/**/*.py"))
        self.assertFalse(file_manifest._matches("tests/deep/test.py", "tests/*.py"))
        product = self.root / "products/new.py"
        product.parent.mkdir()
        product.write_text("new = True\n")
        result = evidence_runner.run(self.root, self.root / "checks", paths=["products/*.py"], attempt_id="glob",
            checks=[{"id": "check", "argv": [sys.executable, "-c", "print('green')"], "depends_on": []}])
        self.assertTrue(result["complete"])
        payload = json.loads(Path(result["receipt"]).read_text())
        self.assertEqual([row["path"] for row in payload["candidate"]], ["products/new.py"])

    def test_native_read_ledger_ignores_discovery_and_refuses_mutated_consulted_bytes(self):
        dependency = self.root / "dependency.py"
        dependency.write_text("value = 1\n")
        ledger = review_sources.ReadLedger(self.root)
        ledger.observe({"sessionUpdate": "tool_call", "title": "grep", "rawInput": {"path": str(self.root)}})
        self.assertFalse(ledger.result()["reads"])
        ledger.observe({"sessionUpdate": "tool_call", "title": "read_file", "toolCallId": "read-1",
                        "rawInput": {"target_file": str(dependency)}})
        ledger.verify()
        dependency.write_text("value = 2\n")
        with self.assertRaisesRegex(ValueError, "REVIEW_DEPENDENCY_STALE"):
            ledger.verify()
        with self.assertRaisesRegex(ValueError, "REVIEW_DEPENDENCY_STALE"):
            ledger.observe({"sessionUpdate": "tool_call_update", "title": "read_file", "toolCallId": "read-1",
                            "rawInput": {"target_file": str(dependency)}})


if __name__ == "__main__":
    unittest.main()
