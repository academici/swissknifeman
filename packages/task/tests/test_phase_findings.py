"""Historical RED review resolution is exhaustive, authenticated and fail closed."""
import copy
import hashlib
import json
import runpy
import subprocess
import tempfile
import unittest
from pathlib import Path

import fixtures
from task import journal, phase_findings, plan_assurance, plan_gates, plan_item_state, plan_status, terminal_policy


class PhaseFindingsTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name)
        self.plan = self.repo / "plans" / "DEMO-1"
        phase = self.plan / "phases/P1"
        phase.mkdir(parents=True)
        (self.plan / "plan.md").write_text(fixtures.plan_md(self.plan.name))
        (phase / "P1.md").write_text(fixtures.phase_index_md().replace(
            "Demo phase.", "Demo phase.\n\n> **Phase Contract.** Produces fixed config."))
        (self.plan / "decisions").mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        product = self.repo / "lib/pkg/config.py"
        product.parent.mkdir(parents=True)
        product.write_text("fixed = True\n")
        for item in ("P1.1", "P1.2"):
            spec = fixtures.item_spec_md(item)
            if item == "P1.2":
                spec = spec.replace("**Implementation Rules:** stdlib-only.", "**Implementation Rules:** read-only review.")
                spec = spec.replace("**Files:** lib/pkg/config.py", "**Files:** `findings/review.md`")
                spec = spec.replace("**Deliverables:** validation + test.", "**Deliverables:** `findings/review.md`.")
            (phase / f"{item}.md").write_text(spec)
        report = self.plan / "findings/review.md"
        report.parent.mkdir()
        report.write_text("**Verdict: RED.**\n\n| ID | Severity | Owning item |\n| R1 | major | P1.1 |\n\n### R1 — defect\n\nProved red.\n")
        sync = None
        if getattr(self, "with_sync", False):
            report.write_text(report.read_text().replace("| R1 | major | P1.1 |",
                "| R1 | major | P1.1 |\n| R2 | minor | P1.1 |") + "\n### R2 — contract drift\n\n`phases/P1/contract.md` violates D1.\n")
            fixtures.write_decision_record(self.plan, "D1", decision="Synchronize contract.")
            sync = self.plan / "phases/P1/contract.md"
            sync.write_text("stale\n")
        gap = {"classifier": "recoverable-validation-gap/v1", "failed_carrier": "findings/review.md: RED",
               "verdict": "outside-scope", "reason": "read-only review", "continuation": "manual: frontier/high",
               "evidence_ids": ["findings/review.md"]}
        self.review = journal.new_entry(plan_id=self.plan.name, item_id="P1.2", command="plan-run",
            actor="test/high", result="closed-deviations", decision=terminal_policy.build_decision(
                self.plan, "P1.2", result="closed-deviations", repair_exhausted=gap,
                validation=[{"carrier": "bash scripts/test.sh", "status": "green", "evidence_ids": ["findings/review.md"]}]))
        journal.append(self.plan, self.review)
        self.git("add", ".")
        self.git("commit", "-qm", "RED review")
        if sync is not None:
            sync.write_text("synchronized\n")
        self.log = self.plan / "artifacts/test.log"
        self.log.parent.mkdir()
        self.log.write_text("all tests passed\n")
        self.exit = self.plan / "artifacts/test.exit"
        self.exit.write_text("0\n")
        self.repair = journal.new_entry(plan_id=self.plan.name, item_id="P1.1", command="plan-run",
            actor="test/high", result="closed-green", decision=terminal_policy.build_decision(
                self.plan, "P1.1", result="closed-green", validation=[
                    {"carrier": "bash scripts/test.sh", "status": "green", "evidence_ids": ["artifacts/test.log"]}]))
        journal.append(self.plan, self.repair)
        plan_item_state.build_states(self.plan)
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")
        anchor = self.git("rev-parse", "HEAD").strip()
        self.record = {"schema_version": phase_findings.SCHEMA, "phase_id": "P1", "validation_anchor": anchor,
            "repairs": {"P1.1": {"event_sha256": phase_findings.digest(self.repair), "commit": anchor,
                "validation": [{"carrier": "bash scripts/test.sh", "log": self.ref(self.log), "exit": self.ref(self.exit)}]}},
            "reviews": [{"item_id": "P1.2", "event_sha256": phase_findings.digest(self.review), "report": self.ref(report),
                "findings": [{"id": "R1", "status": "resolved", "kind": "owning-repair", "owner_item": "P1.1"}]}]}
        if sync is not None:
            self.record["reviews"][0]["findings"].append({"id": "R2", "status": "resolved",
                "kind": "contract-sync", "owner_item": "P1.1", "decision_id": "D1",
                "commit": anchor, "files": [self.ref(sync)]})
        self.write()

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.repo, text=True, capture_output=True, check=True).stdout

    def ref(self, path):
        return {"path": path.relative_to(self.plan).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    def write(self):
        path = phase_findings.receipt_path(self.plan, "P1")
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(self.record))

    def gate(self):
        candidate = plan_gates.phase_candidate_fingerprint(self.plan, "P1")
        return plan_gates.phase_close_gate(self.plan, "P1", candidate_fingerprint=candidate["fingerprint"],
                                            candidate_snapshot=candidate["snapshot"])

    def refused(self):
        self.write()
        gate = self.gate()
        self.assertFalse(gate["allow"], gate)
        self.assertEqual(gate["code"], "PHASE_FINDINGS_UNRESOLVED")
        self.assertNotEqual(gate["audit_policy"]["next_kind"], "audit-phase")

    def test_repaired_phase_closes_with_red_review_history_unchanged(self):
        history = (self.plan / "journal.jsonl").read_bytes()
        report = (self.plan / "findings/review.md").read_bytes()
        self.assertTrue(self.gate()["allow"])
        candidate = plan_gates.phase_candidate_fingerprint(self.plan, "P1")
        proof = self.gate()["audit_policy"]["findings_resolution"]
        event = journal.new_entry(plan_id=self.plan.name, item_id="P1", command="plan-close", actor="test/high",
            result="closed-green", fingerprint=candidate["fingerprint"], decision={"signal_class": "acceptance",
            "scope_class": "phase", "action": "close-green", "terminal": True, "recovered": True,
            "findings_resolution_sha256": proof["sha256"]})
        journal.append(self.plan, event)
        self.assertTrue((self.plan / "journal.jsonl").read_bytes().startswith(history))
        self.assertEqual((self.plan / "findings/review.md").read_bytes(), report)
        self.assertEqual(plan_status._phase_status(["🟢 Done", "🟠 Done with deviations"],
                            plan_dir=self.plan, phase_id="P1"), "🟢 Done")
        self.assertEqual(plan_item_state.state_model(self.plan, "P1.2")[0]["state"]["position"]["status"],
                         "🟠 Done with deviations")

    def test_missing_receipt_does_not_ignore_deviations(self):
        phase_findings.receipt_path(self.plan, "P1").unlink()
        self.assertFalse(self.gate()["allow"])

    def test_unresolved_missing_duplicate_and_foreign_findings_refused(self):
        base = copy.deepcopy(self.record)
        for rows in ([], [{**base["reviews"][0]["findings"][0], "status": "open"}],
                     base["reviews"][0]["findings"] * 2,
                     [{**base["reviews"][0]["findings"][0], "id": "R9"}],
                     [{**base["reviews"][0]["findings"][0], "owner_item": "P1.2"}]):
            with self.subTest(rows=rows):
                self.record = copy.deepcopy(base)
                self.record["reviews"][0]["findings"] = rows
                self.refused()

    def test_bad_event_phase_commit_log_exit_and_validation_refused(self):
        base = copy.deepcopy(self.record)
        mutations = [lambda r: r.update(phase_id="P9"),
            lambda r: r["repairs"]["P1.1"].update(event_sha256="a" * 64),
            lambda r: r["reviews"][0].update(event_sha256="b" * 64),
            lambda r: r["repairs"]["P1.1"].update(commit="c" * 40),
            lambda r: r["repairs"]["P1.1"].update(validation=[]),
            lambda r: r["repairs"]["P1.1"]["validation"][0].update(carrier="unrelated"),
            lambda r: r["repairs"]["P1.1"]["validation"][0]["log"].update(sha256="d" * 64),
            lambda r: r["repairs"]["P1.1"]["validation"][0]["log"].update(path="../outside"),
            lambda r: r["repairs"]["P1.1"]["validation"][0]["exit"].update(path="missing")]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                self.record = copy.deepcopy(base)
                mutate(self.record)
                self.refused()

    def test_failed_exit_with_updated_digest_still_refused(self):
        self.exit.write_text("1\n")
        self.record["repairs"]["P1.1"]["validation"][0]["exit"] = self.ref(self.exit)
        self.refused()

    def test_report_log_or_product_mutation_refused(self):
        for path in (self.log, self.repo / "lib/pkg/config.py", self.plan / "findings/review.md"):
            with self.subTest(path=path):
                old = path.read_bytes()
                path.write_bytes(old + b"changed\n")
                self.assertFalse(self.gate()["allow"])
                path.write_bytes(old)

    def test_later_non_green_or_unadmitted_repeat_cannot_resolve_findings(self):
        for result in ("in-progress", "closed-green"):
            with self.subTest(result=result):
                history = (self.plan / "journal.jsonl").read_bytes()
                event = copy.deepcopy(self.repair)
                event.update(attempt=2, result=result, run_id="a" * 64)
                # Import a malformed legacy row to check the reader, not the writer.
                with (self.plan / "journal.jsonl").open("a") as stream:
                    stream.write(json.dumps(event) + "\n")
                self.record["repairs"]["P1.1"]["event_sha256"] = phase_findings.digest(event)
                if result == "in-progress":
                    with self.assertRaisesRegex(ValueError, "not candidate"):
                        self.gate()
                else:
                    self.refused()
                (self.plan / "journal.jsonl").write_bytes(history)

    def test_phase_append_requires_exact_checked_resolution(self):
        candidate = plan_gates.phase_candidate_fingerprint(self.plan, "P1")
        event = journal.new_entry(plan_id=self.plan.name, item_id="P1", command="plan-close", actor="test/high",
            result="closed-green", fingerprint=candidate["fingerprint"])
        with self.assertRaisesRegex(journal.JournalValidationError, "PHASE_FINDINGS_UNRESOLVED"):
            journal.append(self.plan, event)

    def test_contract_sync_without_accepted_owner_decision_refused(self):
        row = self.record["reviews"][0]["findings"][0]
        row.update(kind="contract-sync", decision_id="D99", commit=self.record["validation_anchor"], files=[])
        self.refused()

    def test_contract_sync_green_and_changed_or_unrelated_evidence_refused(self):
        self.doCleanups()
        self.with_sync = True
        self.setUp()
        self.assertTrue(self.gate()["allow"], self.gate())
        path = self.plan / "phases/P1/contract.md"
        path.write_text("regressed\n")
        self.record["reviews"][0]["findings"][1]["files"] = [self.ref(path)]
        self.refused()

    def test_phase_close_launcher_is_idempotent_and_checks_projection(self):
        close = runpy.run_path(str(Path(__file__).parents[1] / "scripts/plan-phase-close.py"))["close"]
        close(self.plan, "P1", actor="test/high", note="Checked repair evidence.")
        history = (self.plan / "journal.jsonl").read_bytes()
        closure = self.plan / "phases/P1/P1.closed.md"
        self.assertIn("Resolved Review Findings", closure.read_text())
        close(self.plan, "P1", actor="test/high", note="Checked repair evidence.")
        close(self.plan, "P1", actor="test/high", note="Checked repair evidence.", check=True)
        self.assertEqual(history, (self.plan / "journal.jsonl").read_bytes())
        self.log.write_text("tampered\n")
        with self.assertRaisesRegex(ValueError, "PHASE_FINDINGS_UNRESOLVED"):
            close(self.plan, "P1", actor="test/high", note="Tampered.", check=True)

    def test_committing_rewritten_review_does_not_replace_historical_origin(self):
        report = self.plan / "findings/review.md"
        report.write_text(report.read_text() + "Edited history\n")
        self.git("add", ".")
        self.git("commit", "-qm", "invalid rewritten review")
        commit = self.git("rev-parse", "HEAD").strip()
        self.record["validation_anchor"] = commit
        self.record["repairs"]["P1.1"]["commit"] = commit
        self.record["reviews"][0]["report"] = self.ref(report)
        self.refused()
