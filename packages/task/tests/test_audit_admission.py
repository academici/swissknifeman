from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import fixtures
from task import audit_admission
from task.plan_gates import _candidate_snapshot_fingerprint


def candidate(phase_id="P1"):
    return {
        "phase_id": phase_id,
        "scope": ["lib/pkg/config.py"],
        "terminal_item_heads": [{"item_id": f"{phase_id}.1", "status": "GREEN"}],
        "material_risks": ["live boundary"],
        "declared_files": ["lib/pkg/config.py"],
        "product_tree_sha256": "a" * 64,
    }


def record(snapshot, *, run_id="audit-run-1", risks=None, phase_id="P1",
           owner_message="brief/owner.md#audit-p1"):
    value = {
        "schema_version": "audit-admission/v2",
        "target": {
            "phase_id": phase_id,
            "candidate_fingerprint": _candidate_snapshot_fingerprint(snapshot),
        },
        "run_id": run_id,
        "residual_risks": risks if risks is not None else [{
            "id": "R1",
            "impact": "A live migration may expose stale state.",
            "evidence_gap": "The production boundary is not represented locally.",
            "bounded_question": "Does the migration preserve reads during cutover?",
        }],
        "owner_message": owner_message,
        "scope_sha256": "",
    }
    bound = {key: value[key] for key in ("target", "run_id", "residual_risks")}
    value["scope_sha256"] = hashlib.sha256(json.dumps(
        bound, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    return value


class AuditAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.plan_dir = fixtures.write_valid_plan(Path(self.tmp.name), "AUDIT-CONSENT")
        self.snapshot = candidate()

    def tearDown(self):
        self.tmp.cleanup()

    def grant(self, value=None, *, identifier="D1", item_id="P1"):
        value = value or record(self.snapshot)
        body = "Audit is bounded.\n\n```audit-admission/v2\n" + json.dumps(
            value, ensure_ascii=False, indent=2, sort_keys=True) + "\n```"
        path = self.plan_dir / "decisions" / f"{identifier}-fixture.md"
        if path.exists():
            path.unlink()
        fixtures.write_decision_record(
            self.plan_dir, identifier, decision=body, item_id=item_id)
        request = audit_admission.consent_request(value)
        message_id = value["owner_message"].rsplit("#", 1)[-1]
        owner_path = self.plan_dir / "brief" / "owner.md"
        existing = owner_path.read_text(encoding="utf-8").splitlines() if owner_path.exists() else []
        existing = [line for line in existing
                    if not line.startswith(f"[REPOSITORY-OWNER-MESSAGE:{message_id}]")]
        existing.append(
            f"[REPOSITORY-OWNER-MESSAGE:{message_id}] "
            f"[OWNER-GRANT:{request['gate_id']}] branch=`{request['branch']}`; "
            f"scope=`{request['scope']}`; provenance=`repository-owner`")
        owner_path.write_text("\n".join(existing) + "\n", encoding="utf-8")
        return path

    def append_audit(self, result, *, run_id="audit-run-1", phase_id="P1",
                     fingerprint=None, command="plan-audit"):
        row = {
            "command": command,
            "item_id": phase_id,
            "run_id": run_id,
            "fingerprint": fingerprint or _candidate_snapshot_fingerprint(self.snapshot),
            "result": result,
        }
        with (self.plan_dir / "journal.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, sort_keys=True) + "\n")

    def test_exact_consent_allows_and_exposes_owner_request(self):
        value = record(self.snapshot)
        self.grant(value)

        result = audit_admission.evaluate(
            self.plan_dir, "P1", self.snapshot, run_id="audit-run-1")

        self.assertEqual(result, {
            "allowed": True, "code": "AUDIT_ADMITTED", "record": value})
        self.assertEqual(audit_admission.consent_request(value), {
            "gate_id": "AUDIT-P1",
            "branch": "phase-audit",
            "scope": f"audit-admission/v2:{value['scope_sha256']}",
        })

    def test_missing_optional_decisions_directory_is_a_local_refusal(self):
        for path in (self.plan_dir / "decisions").iterdir():
            path.unlink()
        (self.plan_dir / "decisions").rmdir()

        result = audit_admission.evaluate(self.plan_dir, "P1", self.snapshot)

        self.assertFalse(result["allowed"])
        self.assertEqual(result["code"], "AUDIT_CONSENT_MISSING")

    def test_candidate_phase_fingerprint_and_run_mismatches_fail_closed(self):
        self.grant()
        changed = candidate()
        changed["material_risks"] = ["different risk"]
        cases = (
            ("P2", self.snapshot, None),
            ("P1", changed, None),
            ("P1", self.snapshot, "another-run"),
        )
        for phase_id, snapshot, run_id in cases:
            with self.subTest(phase_id=phase_id, run_id=run_id):
                result = audit_admission.evaluate(
                    self.plan_dir, phase_id, snapshot, run_id=run_id)
                self.assertFalse(result["allowed"])

    def test_empty_risk_or_bad_owner_source_is_invalid(self):
        empty_risk = record(self.snapshot, risks=[])
        empty_risk["scope_sha256"] = hashlib.sha256(json.dumps({
            key: empty_risk[key] for key in ("target", "run_id", "residual_risks")
        }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        body = "```audit-admission/v2\n" + json.dumps(empty_risk) + "\n```"
        fixtures.write_decision_record(
            self.plan_dir, "D1", decision=body, item_id="P1")
        self.assertEqual(audit_admission.evaluate(
            self.plan_dir, "P1", self.snapshot)["code"], "AUDIT_CONSENT_INVALID")

        self.grant()
        (self.plan_dir / "brief" / "owner.md").write_text(
            "copied owner identity is not consent\n", encoding="utf-8")
        self.assertEqual(audit_admission.evaluate(
            self.plan_dir, "P1", self.snapshot)["code"], "AUDIT_CONSENT_INVALID")

    def test_duplicate_grants_and_reused_run_ids_are_ambiguous(self):
        value = record(self.snapshot)
        self.grant(value)
        self.grant(value, identifier="D2")
        self.assertEqual(audit_admission.evaluate(
            self.plan_dir, "P1", self.snapshot)["code"], "AUDIT_CONSENT_AMBIGUOUS")

        second = record(candidate("P2"), phase_id="P2")
        self.grant(second, identifier="D2", item_id="P2")
        self.assertEqual(audit_admission.evaluate(
            self.plan_dir, "P1", self.snapshot)["code"], "AUDIT_CONSENT_AMBIGUOUS")

    def test_started_run_is_reserved_for_itself_and_terminal_consumes_it(self):
        self.grant()
        self.append_audit("in-progress")
        self.assertTrue(audit_admission.evaluate(
            self.plan_dir, "P1", self.snapshot, run_id="audit-run-1")["allowed"])

        self.append_audit("audit-green")
        result = audit_admission.evaluate(
            self.plan_dir, "P1", self.snapshot, run_id="audit-run-1")
        self.assertFalse(result["allowed"])
        self.assertEqual(result["code"], "AUDIT_CONSENT_CONSUMED")
        self.assertIsNotNone(result["record"])

    def test_consumed_grant_yields_to_one_new_grant_for_the_same_candidate(self):
        old = record(self.snapshot)
        self.grant(old)
        self.append_audit("in-progress")
        self.append_audit("audit-green")
        new = record(
            self.snapshot, run_id="audit-run-2",
            owner_message="brief/owner.md#audit-p1-run-2")
        self.grant(new, identifier="D2")

        implicit = audit_admission.evaluate(self.plan_dir, "P1", self.snapshot)
        consumed = audit_admission.evaluate(
            self.plan_dir, "P1", self.snapshot, run_id="audit-run-1")

        self.assertEqual(implicit, {
            "allowed": True, "code": "AUDIT_ADMITTED", "record": new})
        self.assertEqual(consumed, {
            "allowed": False, "code": "AUDIT_CONSENT_CONSUMED", "record": old})

    def test_two_unconsumed_grants_for_same_candidate_remain_ambiguous(self):
        self.grant(record(self.snapshot))
        self.grant(record(
            self.snapshot, run_id="audit-run-2",
            owner_message="brief/owner.md#audit-p1-run-2"), identifier="D2")

        result = audit_admission.evaluate(self.plan_dir, "P1", self.snapshot)

        self.assertEqual(result["code"], "AUDIT_CONSENT_AMBIGUOUS")

    def test_invalid_public_input_types_are_normalized_to_invalid(self):
        self.grant()
        cases = (
            (None, "P1", self.snapshot, None),
            (self.plan_dir, 1, self.snapshot, None),
            (self.plan_dir, "P1", [], None),
            (self.plan_dir, "P1", {}, None),
            (self.plan_dir, "P1", self.snapshot, 7),
        )
        for plan_dir, phase_id, snapshot, run_id in cases:
            with self.subTest(phase_id=phase_id, run_id=run_id):
                result = audit_admission.evaluate(
                    plan_dir, phase_id, snapshot, run_id=run_id)
                self.assertEqual(result, {
                    "allowed": False,
                    "code": "AUDIT_CONSENT_INVALID",
                    "record": None,
                })

    def test_reusing_grant_run_for_another_target_is_invalid(self):
        self.grant()
        self.append_audit("in-progress", phase_id="P2")
        result = audit_admission.evaluate(self.plan_dir, "P1", self.snapshot)
        self.assertEqual(result["code"], "AUDIT_CONSENT_INVALID")

    def test_symlink_and_malformed_admission_are_rejected(self):
        path = self.grant()
        target = path.with_name("grant-target.md")
        path.rename(target)
        path.symlink_to(target.name)
        self.assertEqual(audit_admission.evaluate(
            self.plan_dir, "P1", self.snapshot)["code"], "AUDIT_CONSENT_INVALID")

        path.unlink()
        target.rename(path)
        text = path.read_text(encoding="utf-8").replace('"schema_version"', 'schema_version')
        path.write_text(text, encoding="utf-8")
        self.assertEqual(audit_admission.evaluate(
            self.plan_dir, "P1", self.snapshot)["code"], "AUDIT_CONSENT_INVALID")


if __name__ == "__main__":
    unittest.main()
