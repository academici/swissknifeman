"""Terminal continuity and handoff recommendation receipts."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from .fixtures import write_valid_plan
except ImportError:
    from fixtures import write_valid_plan
from task import (journal, plan_closure, plan_delivery, plan_gates, plan_item_state,
                  terminal_policy, plan_bundle, plan_continuity)
from task import plan_readiness


class PlanDeliveryTests(unittest.TestCase):
    def test_waiting_owner_can_resume_escalated_item_but_cannot_replay_green_item(self):
        for result in ("escalated", "closed-green"):
            with self.subTest(result=result):
                plan = self._terminal_plan(result=result, root=self.root / result)
                decision = plan_continuity.evaluate(
                    route_attested=True, context_attested=True,
                    batch_receipt_valid=True, waiting_owner=True,
                )
                (plan / "handoff.md").write_text(
                    "# HANDOFF — 2026-09-28 — after P1.1\n\n"
                    "**Next:** waiting: owner approval → exec-items: task:plan-run DEMO-DELIVERY P1.1\n\n"
                    "| Model | implementation |\n| Thinking | high |\n| Context | waiting-owner |\n\n"
                    "```session-continuity-decision/v1\n"
                    + json.dumps(decision.as_dict()) + "\n```\n\n**Done:** pending approval\n",
                )
                if result == "escalated":
                    receipt = plan_delivery.build_terminal_receipt(plan, "P1.1")
                    self.assertEqual(receipt["continuity"]["outcome"], "waiting-owner")
                else:
                    with self.assertRaisesRegex(plan_delivery.DeliveryError, "FINAL_BEFORE_TERMINAL_FORBIDDEN"):
                        plan_delivery.build_terminal_receipt(plan, "P1.1")

    def test_required_final_message_is_machine_authored_and_exact(self):
        message = plan_delivery.required_final_message({
            "schema_version": "terminal-delivery-receipt/v1", "recommendation": "Run P4.2.",
        })
        self.assertEqual(message, "Next step recommendation:\nRun P4.2.")
        with self.assertRaisesRegex(plan_delivery.DeliveryError, "STALE_TERMINAL_RECEIPT"):
            plan_delivery.required_final_message({"schema_version": "unknown"})

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def _events(path):
        return [json.loads(row) for row in Path(path).read_text(
            encoding="utf-8").splitlines() if row.strip()]

    @staticmethod
    def _write_events(path, events):
        Path(path).write_text("".join(
            json.dumps(event, ensure_ascii=False) + "\n" for event in events),
            encoding="utf-8")

    def _terminal_plan(self, *, layout="v2", result="closed-green", root=None):
        fixture_root = Path(root or self.root)
        fixture_root.mkdir(parents=True, exist_ok=True)
        subprocess.run(("git", "init", "-q"), cwd=fixture_root, check=True)
        subprocess.run(("git", "config", "user.email", "delivery@example.invalid"),
                       cwd=fixture_root, check=True)
        subprocess.run(("git", "config", "user.name", "Delivery Fixture"),
                       cwd=fixture_root, check=True)
        plan = write_valid_plan(fixture_root, "DEMO-DELIVERY", layout=layout)
        phase = plan / "phases" / "P1" / "P1.md"
        phase.write_text(
            phase.read_text(encoding="utf-8")
            + "\n> **Phase Contract | v1.**\n> Delivery fixture contract.\n",
            encoding="utf-8")
        (plan / "journal.jsonl").write_text("", encoding="utf-8")
        handoff = plan / "handoff.md"
        handoff.write_text(handoff.read_text(encoding="utf-8").replace(
            "/task:plan-run DEMO-DELIVERY P1.1",
            "archive: task:plan-close DEMO-DELIVERY archive"), encoding="utf-8")
        subprocess.run(("git", "add", "."), cwd=fixture_root, check=True)
        subprocess.run(("git", "commit", "-qm", "fixture"), cwd=fixture_root, check=True)
        if result in {"blocked", "escalated"}:
            decision = {
                "signal_class": "authority",
                "scope_class": "item",
                "action": "terminal-block",
                "recovered": False,
                "terminal": True,
                "reason_code": "OWNER_AUTHORITY_REQUIRED",
            }
        else:
            decision = terminal_policy.build_decision(
                plan, "P1.1", result=result,
                validation=[{"carrier": "bash test.sh", "status": "green",
                             "evidence_ids": ["test:exit-0"]}],
                repair_exhausted=(
                    {"classifier": "recoverable-validation-gap/v1",
                     "failed_carrier": "bash test.sh", "verdict": "outside-scope",
                     "reason": "fixture deviation", "continuation": "follow-up: fixture",
                     "evidence_ids": ["test:deviation"]}
                    if result == "closed-deviations" else None),
            )
        journal.append(plan, journal.new_entry(
            plan_id=plan.name,
            item_id="P1.1",
            command="plan-run",
            actor="implementation/high",
            result=result,
            session_id="session-1",
            run_id="run-1",
            fingerprint="a" * 64,
            decision=decision,
        ))
        plan_item_state.build_states(plan, item_id="P1.1")
        if result == "closed-green":
            plan_closure.build_closure(plan, "P1")
            journal.append(plan, journal.new_entry(
                plan_id=plan.name,
                item_id="P1",
                command="plan-close",
                actor="implementation/high",
                result="closed-green",
                session_id="session-1",
                run_id="run-phase-1",
                fingerprint="b" * 64,
            ))
        return plan

    def test_cli_renders_shared_final_without_optional_admission_lease(self):
        plan = self._terminal_plan()
        script = Path(__file__).resolve().parents[1] / "scripts" / "plan-delivery.py"
        output = self.root / "receipt.json"
        args = ["python3", str(script), "--plan-dir", str(plan), "--subject", "P1.1",
                "--kind", "terminal", "--render-final"]
        written = subprocess.run(args + ["--output", str(output)], capture_output=True, text=True)
        self.assertEqual(written.returncode, 0, written.stderr)
        receipt = json.loads(output.read_text())
        self.assertEqual(written.stdout.strip(), plan_delivery.required_final_message(receipt))
        verified = subprocess.run(args + ["--verify", str(output)], capture_output=True, text=True)
        self.assertEqual(verified.returncode, 0, verified.stderr)
        self.assertEqual(verified.stdout, written.stdout)
        receipt["recommendation"] = "stale successor"
        output.write_text(json.dumps(receipt))
        rejected = subprocess.run(args + ["--verify", str(output)], capture_output=True, text=True)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertEqual(rejected.stdout, "")

    def test_terminal_item_receipt_binds_state_journal_and_exact_recommendation(self):
        plan = self._terminal_plan()
        receipt = plan_delivery.build_terminal_receipt(plan, "P1.1")
        self.assertEqual(receipt["schema_version"], "terminal-delivery-receipt/v1")
        self.assertEqual(receipt["status"], "🟢 Done")
        self.assertEqual(
            receipt["next_exact"], "archive: task:plan-close DEMO-DELIVERY archive")
        self.assertIn("| Model | sonnet |", receipt["recommendation"])
        self.assertEqual(receipt["journal"]["run_id"], "run-1")
        self.assertEqual(receipt["journal"]["line"], 1)
        routing = json.loads((Path(__file__).resolve().parents[1]
                              / "configs" / "command-routing.json").read_text())
        self.assertEqual(receipt["adapter_attestation"]["version"],
                         routing["plugin_version"])
        self.assertEqual(receipt["adapter_attestation"]["command_id"], "task:plan-run")
        self.assertRegex(
            receipt["adapter_attestation"]["canonical_command_sha256"],
            r"^sha256:[0-9a-f]{64}$")
        self.assertRegex(receipt["digests"]["state"], r"^sha256:[0-9a-f]{64}$")
        self.assertTrue(plan_delivery.verify_receipt(plan, receipt))

    def test_terminal_item_handoff_rejects_relaunch_via_plan_close(self):
        plan = self._terminal_plan(root=self.root / "close-loop")
        phase_dir = plan / "phases" / "P1"
        (phase_dir / "P1.2.md").write_text(
            (phase_dir / "P1.1.md").read_text(encoding="utf-8").replace(
                "P1.1", "P1.2"), encoding="utf-8")
        (phase_dir / "P1.2.state.md").write_text(
            "**Status:** ⬜ Not started\n"
            "**Completion Notes:** —\n"
            "**Pending Work:** —\n"
            "**Known Deviations:** —\n"
            "**Escalation Needed:** —\n",
            encoding="utf-8")
        (phase_dir / "P1.closed.md").unlink()
        self._write_events(plan / "journal.jsonl", self._events(plan / "journal.jsonl")[:1])
        handoff = plan / "handoff.md"
        handoff.write_text(handoff.read_text(encoding="utf-8").replace(
            "archive: task:plan-close DEMO-DELIVERY archive",
            "close: task:plan-close DEMO-DELIVERY P1.1"), encoding="utf-8")

        with self.assertRaisesRegex(
                plan_delivery.DeliveryError, "FINAL_BEFORE_TERMINAL_FORBIDDEN"):
            plan_delivery.build_terminal_receipt(plan, "P1.1")

    def _plan_with_ready_successor(self, *, root=None):
        plan = self._terminal_plan(root=root)
        phase_dir = plan / "phases" / "P1"
        (phase_dir / "P1.2.md").write_text(
            (phase_dir / "P1.1.md").read_text(encoding="utf-8").replace(
                "P1.1", "P1.2"), encoding="utf-8")
        (phase_dir / "P1.closed.md").unlink()
        plan_item_state.build_states(plan, item_id="P1.2")
        plan_bundle.build(plan, "P1.2")
        return plan

    @staticmethod
    def _write_terminal_handoff(plan, next_exact):
        handoff = plan / "handoff.md"
        text = handoff.read_text(encoding="utf-8").replace(
            "archive: task:plan-close DEMO-DELIVERY archive", next_exact
        ).replace("| Context | fresh session |", "| Context | terminal |")
        decision = plan_continuity.ContinuityDecision(
            "terminal", "terminal-evidence", ("batch:solo-complete",), False)
        block = "\n```session-continuity-decision/v1\n" + json.dumps(
            decision.as_dict()) + "\n```\n"
        text = text.replace("\n**Done:**", block + "\n**Done:**", 1)
        handoff.write_text(text, encoding="utf-8")

    def test_completed_solo_batch_cannot_hide_ready_successor_as_terminal(self):
        for index, next_exact in enumerate(("none: solo complete", "terminal: solo complete")):
            with self.subTest(next_exact=next_exact):
                plan = self._plan_with_ready_successor(root=self.root / str(index))
                self._write_terminal_handoff(plan, next_exact)
                with self.assertRaisesRegex(
                        plan_delivery.DeliveryError, "TERMINAL_NEXT_FORBIDDEN"):
                    plan_delivery.build_terminal_receipt(plan, "P1.1")
                with self.assertRaisesRegex(
                        plan_delivery.DeliveryError, "TERMINAL_NEXT_FORBIDDEN"):
                    plan_delivery.build_handoff_receipt(plan, "P1.1")

    def test_ready_successor_outside_completed_batch_keeps_executable_handoff(self):
        plan = self._plan_with_ready_successor()
        handoff = plan / "handoff.md"
        handoff.write_text(handoff.read_text(encoding="utf-8").replace(
            "archive: task:plan-close DEMO-DELIVERY archive",
            "run-items: task:plan-run DEMO-DELIVERY P1.2"), encoding="utf-8")
        receipt = plan_delivery.build_terminal_receipt(plan, "P1.1")
        self.assertEqual(receipt["next_exact"],
                         "run-items: task:plan-run DEMO-DELIVERY P1.2")
        self.assertEqual(receipt["continuity"]["outcome"], "cold-start-root")

    def test_terminal_next_is_allowed_after_all_plan_items_complete(self):
        plan = self._terminal_plan()
        self._write_terminal_handoff(plan, "terminal: plan complete")
        receipt = plan_delivery.build_terminal_receipt(plan, "P1.1")
        self.assertEqual(receipt["continuity"]["outcome"], "terminal")

    def test_last_green_item_requires_inline_phase_closure(self):
        plan = self._terminal_plan(root=self.root / "phase-closure-required")
        (plan / "phases" / "P1" / "P1.closed.md").unlink()

        with self.assertRaisesRegex(plan_delivery.DeliveryError, "PHASE_CLOSURE_REQUIRED"):
            plan_delivery.build_terminal_receipt(plan, "P1.1")

    def test_terminal_non_green_item_keeps_ordinary_handoff(self):
        for result, expected_status in (
                ("closed-deviations", "🟠 Done with deviations"),
                ("blocked", "🔴 Blocked")):
            with self.subTest(result=result):
                plan = self._terminal_plan(
                    root=self.root / result, result=result)

                receipt = plan_delivery.build_terminal_receipt(plan, "P1.1")

                self.assertEqual(receipt["status"], expected_status)
                self.assertIsNone(receipt["digests"]["closure"])

    def test_green_item_with_other_blocked_phase_item_does_not_force_phase_close(self):
        plan = self._terminal_plan(root=self.root / "other-blocked")
        phase_dir = plan / "phases" / "P1"
        (phase_dir / "P1.2.md").write_text(
            (phase_dir / "P1.1.md").read_text(encoding="utf-8").replace(
                "P1.1", "P1.2"), encoding="utf-8")
        (phase_dir / "P1.closed.md").unlink()
        self._write_events(plan / "journal.jsonl", self._events(plan / "journal.jsonl")[:1])
        journal.append(plan, journal.new_entry(
            plan_id=plan.name,
            item_id="P1.2",
            command="plan-run",
            actor="implementation/high",
            result="blocked",
            session_id="session-2",
            run_id="run-2",
            decision={
                "signal_class": "authority",
                "scope_class": "item",
                "action": "terminal-block",
                "recovered": False,
                "terminal": True,
                "reason_code": "OWNER_AUTHORITY_REQUIRED",
            },
        ))
        plan_item_state.build_states(plan, item_id="P1.2")

        receipt = plan_delivery.build_terminal_receipt(plan, "P1.1")

        self.assertEqual(receipt["status"], "🟢 Done")
        self.assertIsNone(receipt["digests"]["closure"])

    def test_unconsented_audit_next_is_rejected_from_rebuilt_candidate(self):
        plan = self._terminal_plan(root=self.root / "audit-not-admitted")
        handoff = plan / "handoff.md"
        handoff.write_text(handoff.read_text(encoding="utf-8").replace(
            "archive: task:plan-close DEMO-DELIVERY archive",
            "audit-phase: task:plan-audit DEMO-DELIVERY P1"), encoding="utf-8")

        with self.assertRaisesRegex(plan_delivery.DeliveryError, "PHASE_AUDIT_NOT_ADMITTED"):
            plan_delivery.build_terminal_receipt(plan, "P1.1")

    def test_consented_audit_next_must_match_policy_exactly(self):
        plan = self._terminal_plan(root=self.root / "audit-exact")
        (plan / "phases" / "P1" / "P1.closed.md").unlink()
        self._write_events(plan / "journal.jsonl", self._events(plan / "journal.jsonl")[:1])
        handoff = plan / "handoff.md"
        expected = "audit-phase: task:plan-audit DEMO-DELIVERY P1"
        handoff.write_text(handoff.read_text(encoding="utf-8").replace(
            "archive: task:plan-close DEMO-DELIVERY archive", expected), encoding="utf-8")
        policy = {
            "action": "audit-required",
            "audit_required": True,
            "close_allowed": False,
            "code": "PHASE_AUDIT_APPROVED",
            "next_kind": "audit-phase",
            "next_exact": expected,
        }

        with patch.object(plan_gates, "phase_audit_policy", return_value=policy) as reducer:
            receipt = plan_delivery.build_terminal_receipt(plan, "P1.1")

        self.assertEqual(receipt["next_exact"], expected)
        self.assertGreaterEqual(reducer.call_count, 2)

    def test_nonterminal_item_forbids_terminal_receipt(self):
        plan = write_valid_plan(self.root, "DEMO-LIVE", layout="v2")
        (plan / "journal.jsonl").write_text("", encoding="utf-8")
        journal.append(plan, journal.new_entry(
            plan_id=plan.name, item_id="P1.1", command="plan-run",
            actor="implementation/high", result="in-progress",
            session_id="session-1", run_id="run-1",
        ))
        plan_item_state.build_states(plan, item_id="P1.1")
        with self.assertRaisesRegex(plan_delivery.DeliveryError, "FINAL_BEFORE_TERMINAL_FORBIDDEN"):
            plan_delivery.build_terminal_receipt(plan, "P1.1")

    def test_handoff_receipt_is_available_for_nonterminal_design_delivery(self):
        plan = write_valid_plan(self.root, "DEMO-HANDOFF", layout="v2")
        receipt = plan_delivery.build_handoff_receipt(plan, "design")
        self.assertEqual(receipt["schema_version"], "handoff-recommendation-receipt/v1")
        self.assertEqual(receipt["status"], "handoff-persisted")
        self.assertEqual(receipt["next_exact"], "/task:plan-run DEMO-HANDOFF P1.1")
        self.assertEqual(receipt["continuity"]["outcome"], "cold-start-root")
        self.assertEqual(receipt["continuity"]["reason"], "owner-pause-no-resume")

    def test_terminal_phase_design_handoff_requires_typed_reentry(self):
        plan = write_valid_plan(self.root, "2026.09.09-№1-DEMO-REENTRY", layout="v2")
        handoff = plan / "handoff.md"
        handoff.write_text(handoff.read_text(encoding="utf-8").replace(
            "/task:plan-run 2026.09.09-№1-DEMO-REENTRY P1.1",
            "/task:plan-design 2026.09.09-№1-DEMO-REENTRY P1"), encoding="utf-8")
        with self.assertRaisesRegex(plan_delivery.DeliveryError,
                                    "PHASE_REENTRY_UNJUSTIFIED"):
            plan_delivery.build_handoff_receipt(plan, "design")
        reentry = {
            "schema_version": "phase-reentry-justification/v1", "phase_id": "P1",
            "trigger": "terminal-evidence-invalid", "evidence_ids": ["audit:P1"],
            "origin_item": "P1.1", "resume_item": "P1.1",
        }
        decision = plan_readiness.correction_decision(
            observed_mode="contract-conflict", reentry=reentry)
        journal.append(plan, journal.new_entry(
            plan_id=plan.name, item_id="P1", command="plan-audit",
            actor="frontier/xhigh", result="local-repair", decision=decision,
        ))
        receipt = plan_delivery.build_handoff_receipt(plan, "design")
        self.assertIn("plan-design", receipt["next_exact"])

    def test_generated_design_handoff_rejects_a_ready_unfinished_phase(self):
        plan = write_valid_plan(self.root, "2026.09.14-№1-DEMO-READY", layout="v2")
        state = plan / "phases" / "P1" / "P1.1.state.md"
        state.write_text(state.read_text(encoding="utf-8").replace(
            "🟢 Done", "⬜ Not started"), encoding="utf-8")
        handoff = plan / "handoff.md"
        handoff.write_text(handoff.read_text(encoding="utf-8").replace(
            "/task:plan-run 2026.09.14-№1-DEMO-READY P1.1",
            "/task:plan-design 2026.09.14-№1-DEMO-READY P1"), encoding="utf-8")
        with self.assertRaisesRegex(plan_delivery.DeliveryError, "PLAN_DESIGN_NOT_NEEDED"):
            plan_delivery.build_handoff_receipt(plan, "design")

    def test_handoff_receipt_rejects_unknown_persisted_context(self):
        plan = write_valid_plan(self.root, "DEMO-BAD-CONTEXT", layout="v2")
        handoff = plan / "handoff.md"
        handoff.write_text(handoff.read_text(encoding="utf-8").replace(
            "| Context | fresh session |", "| Context | maybe-new-root |"),
            encoding="utf-8")
        with self.assertRaisesRegex(
                plan_delivery.DeliveryError, "CONTINUITY_CONTEXT_INVALID"):
            plan_delivery.build_handoff_receipt(plan, "design")

    def test_handoff_receipt_preserves_visible_batch(self):
        plan = write_valid_plan(self.root, "DEMO-BATCH-HANDOFF", layout="v2")
        handoff = plan / "handoff.md"
        handoff.write_text(handoff.read_text(encoding="utf-8").replace(
            "| Model | sonnet |", "| Batch | B1 |\n| Model | sonnet |"), encoding="utf-8")
        receipt = plan_delivery.build_handoff_receipt(plan, "design")
        self.assertEqual(receipt["route"]["batch"], "B1")

    def test_phase_audit_receipt_rejects_repair_successor_without_terminal_evidence(self):
        plan = write_valid_plan(self.root, "DEMO-AUDIT", layout="v2")
        phase = plan / "phases" / "P1" / "P1.md"
        phase.write_text(
            phase.read_text(encoding="utf-8")
            + "\n## Audit P1 — 2026-08-12\n\n**Verdict: RED**\n\n"
            "### What to run\n\n"
            "| Batch | Model | Thinking | Context | The bottom line | Command |\n"
            "|:--|:--|:--|:--|:--|:--|\n"
            "| repair | frontier | high | `continue-root` | fix | "
            "`$ task:plan-run DEMO-AUDIT P1.1` |\n\n"
            "```text\n$ task:plan-run DEMO-AUDIT P1.1\n\n"
            "MODE: bounded audit repair-forward\nENTRANCE: audit\nSCORE: fix\nDO NOT TOUCH: other\n```\n",
            encoding="utf-8",
        )
        journal.append(plan, journal.new_entry(
            plan_id=plan.name, item_id="P1", command="plan-audit",
            actor="frontier/xhigh", result="audit-green", session_id="session-audit",
            fingerprint="a" * 64,
        ))
        with self.assertRaisesRegex(
                plan_delivery.DeliveryError, "AUDIT_VERDICT_EVENT_MISMATCH"):
            plan_delivery.build_handoff_receipt(plan, "P1")

    def test_phase_audit_green_receipt_binds_close_successor(self):
        plan = write_valid_plan(self.root, "DEMO-AUDIT-GREEN", layout="v2")
        phase = plan / "phases" / "P1" / "P1.md"
        phase.write_text(
            phase.read_text(encoding="utf-8")
            + "\n## Audit P1 — 2026-08-13\n\n**Verdict: GREEN**\n\n"
            "### What to run\n\n"
            "Semantic Next: `close: task:plan-close DEMO-AUDIT-GREEN P1`.\n\n"
            "| Batch | Model | Thinking | Context | The bottom line | Command |\n"
            "|:--|:--|:--|:--|:--|:--|\n"
            "| n/a | implementation | high | `continue-root` | close | "
            "`$ task:plan-close DEMO-AUDIT-GREEN P1` |\n",
            encoding="utf-8",
        )
        journal.append(plan, journal.new_entry(
            plan_id=plan.name, item_id="P1 — phase mode", command="plan-audit",
            actor="frontier/xhigh", result="audit-green", session_id="session-audit",
            fingerprint="b" * 64,
        ))
        receipt = plan_delivery.build_handoff_receipt(plan, "P1")
        self.assertEqual(
            receipt["next_exact"], "close: task:plan-close DEMO-AUDIT-GREEN P1")
        self.assertEqual(receipt["continuity"]["reason"], "compatible-active-work")
        self.assertEqual(receipt["digests"]["handoff"], plan_delivery.file_digest(phase))

    def test_stale_handoff_recommendation_is_rejected(self):
        plan = self._terminal_plan()
        receipt = plan_delivery.build_terminal_receipt(plan, "P1.1")
        handoff = plan / "handoff.md"
        handoff.write_text(
            handoff.read_text(encoding="utf-8").replace("P1.1", "P1.2"),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(plan_delivery.DeliveryError,
                                    "FINAL_BEFORE_TERMINAL_FORBIDDEN"):
            plan_delivery.verify_receipt(plan, receipt)

    def test_terminal_item_rejects_stale_subject_handoff(self):
        plan = self._terminal_plan()
        handoff = plan / "handoff.md"
        handoff.write_text(
            handoff.read_text(encoding="utf-8").replace("after P1.1", "after P1.0"),
            encoding="utf-8")
        with self.assertRaisesRegex(
                plan_delivery.DeliveryError, "FINAL_BEFORE_TERMINAL_FORBIDDEN"):
            plan_delivery.build_terminal_receipt(plan, "P1.1")

    def test_v2_receipt_uses_generated_item_state_digest(self):
        plan = self._terminal_plan(layout="v2")
        receipt = plan_delivery.build_terminal_receipt(plan, "P1.1")
        state = plan / "phases" / "P1" / "P1.1.state.md"
        self.assertEqual(receipt["digests"]["state"], plan_delivery.file_digest(state))

    def test_terminal_receipt_survives_bookkeeping_head_change(self):
        plan = self._terminal_plan()
        receipt = plan_delivery.build_terminal_receipt(plan, "P1.1")
        original = plan_delivery._git_commit
        plan_delivery._git_commit = lambda _plan: "f" * 40
        try:
            self.assertTrue(plan_delivery.verify_receipt(plan, receipt))
        finally:
            plan_delivery._git_commit = original

    def test_terminal_phase_and_archive_receipts_are_supported(self):
        phase_plan = self._terminal_plan()
        journal.append(phase_plan, journal.new_entry(
            plan_id=phase_plan.name, item_id="P1", command="plan-close",
            actor="implementation/high", result="closed-green", session_id="session-phase",
            run_id="run-phase", fingerprint="c" * 64,
        ))
        phase_receipt = plan_delivery.build_terminal_receipt(phase_plan, "P1")
        self.assertEqual(phase_receipt["status"], "🟢 Done")
        self.assertEqual(phase_receipt["journal"]["run_id"], "run-phase")

        archive_plan = write_valid_plan(self.root, "DEMO-ARCHIVE")
        archived_path = archive_plan.parent / "archive" / archive_plan.name
        archived_path.parent.mkdir()
        archive_plan.rename(archived_path)
        archive_plan = archived_path
        journal.append(archive_plan, journal.new_entry(
            plan_id=archive_plan.name, item_id="archive", command="plan-close",
            actor="implementation/high", result="closed-green", session_id="session-archive",
            run_id="run-archive", fingerprint="d" * 64,
        ))
        archive_receipt = plan_delivery.build_terminal_receipt(archive_plan, "archive")
        self.assertEqual(archive_receipt["status"], "archived")
        self.assertEqual(archive_receipt["journal"]["run_id"], "run-archive")

    def test_terminal_receipt_refuses_missing_carrier_and_run_id(self):
        plan = self._terminal_plan(root=self.root / "missing-carrier")
        (plan / "phases" / "P1" / "P1.1.state.md").unlink()
        with self.assertRaisesRegex(plan_delivery.DeliveryError, "DELIVERY_CARRIER_MISSING"):
            plan_delivery.build_terminal_receipt(plan, "P1.1")

        plan = self._terminal_plan(root=self.root / "missing-run-id-terminal")
        journal_path = plan / "journal.jsonl"
        events = self._events(journal_path)
        events[0].pop("run_id")
        self._write_events(journal_path, events)
        with self.assertRaisesRegex(plan_delivery.DeliveryError, "STALE_TERMINAL_RECEIPT|TERMINAL_RUN_ID_MISSING"):
            plan_delivery.build_terminal_receipt(plan, "P1.1")

    def test_terminal_receipt_skips_historical_missing_run_id_when_latest_is_valid(self):
        plan = self._terminal_plan(root=self.root / "historical-missing-run-id")
        journal_path = plan / "journal.jsonl"
        latest, phase_close = self._events(journal_path)
        historical = {**latest, "run_id": None, "ts": "2026-08-12T00:00:00Z"}
        self._write_events(journal_path, (historical, latest, phase_close))
        plan_item_state.build_states(plan, item_id="P1.1")
        plan_closure.build_closure(plan, "P1")

        receipt = plan_delivery.build_terminal_receipt(plan, "P1.1")

        self.assertEqual(receipt["journal"]["line"], 2)
        self.assertEqual(receipt["journal"]["run_id"], "run-1")

    def test_terminal_receipt_skips_historical_invalid_terminal_when_recovered_close_is_valid(self):
        plan = self._terminal_plan(root=self.root / "historical-invalid-terminal")
        journal_path = plan / "journal.jsonl"
        latest, phase_close = self._events(journal_path)
        historical = {
            **latest,
            "result": "blocked",
            "decision": None,
            "ts": "2026-08-12T00:00:00Z",
        }
        self._write_events(journal_path, (historical, latest, phase_close))
        plan_item_state.build_states(plan, item_id="P1.1")
        plan_closure.build_closure(plan, "P1")

        receipt = plan_delivery.build_terminal_receipt(plan, "P1.1")

        self.assertEqual(receipt["journal"]["line"], 2)
        self.assertEqual(receipt["journal"]["run_id"], "run-1")

    def test_terminal_receipt_still_refuses_only_invalid_terminal(self):
        plan = self._terminal_plan(root=self.root / "only-invalid-terminal")
        path = plan / "journal.jsonl"
        event, phase_close = self._events(path)
        event["result"] = "blocked"
        event["decision"] = None
        self._write_events(path, (event, phase_close))
        plan_item_state.build_states(plan, item_id="P1.1")

        with self.assertRaisesRegex(plan_delivery.DeliveryError, "TERMINAL_EVIDENCE_REQUIRED"):
            plan_delivery.build_terminal_receipt(plan, "P1.1")

    def test_terminal_receipt_refuses_journal_state_result_mismatch(self):
        plan = self._terminal_plan(result="closed-deviations")
        state = plan / "phases" / "P1" / "P1.1.state.md"
        state.write_text(
            state.read_text(encoding="utf-8").replace("🟠 Done with deviations", "🟢 Done"),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(plan_delivery.DeliveryError, "STALE_TERMINAL_RECEIPT"):
            plan_delivery.build_terminal_receipt(plan, "P1.1")

    def test_terminal_receipt_rejects_tampered_red_validation(self):
        plan = self._terminal_plan()
        path = plan / "journal.jsonl"
        event, phase_close = self._events(path)
        event["decision"]["terminal_evidence"]["validation"][0]["status"] = "red"
        self._write_events(path, (event, phase_close))
        plan_item_state.build_states(plan, item_id="P1.1")
        with self.assertRaisesRegex(plan_delivery.DeliveryError, "TERMINAL_VALIDATION_RED"):
            plan_delivery.build_terminal_receipt(plan, "P1.1")

    def test_atomic_write_round_trips_receipt(self):
        plan = self._terminal_plan()
        receipt = plan_delivery.build_terminal_receipt(plan, "P1.1")
        target = plan / "artifacts" / "receipt.json"
        plan_delivery.write_receipt(target, receipt)
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), receipt)
        self.assertEqual(list(target.parent.glob(".receipt.json.*.tmp")), [])

    def test_every_plan_command_reports_the_exact_next_plan_line(self):
        command_dir = Path(__file__).resolve().parents[1] / "commands"
        for name in ("plan-design.md", "plan-run.md", "plan-audit.md", "plan-close.md"):
            source = (command_dir / name).read_text(encoding="utf-8")
            self.assertIn("plan.py next", source, name)


if __name__ == "__main__":
    unittest.main()
