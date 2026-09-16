"""Lease-bound, provider-neutral terminal-admission policy."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from task import journal, terminal_admission, terminal_policy, task_contract

try:
    from .fixtures import write_valid_plan
except ImportError:
    from fixtures import write_valid_plan


def receipt(*, run_id="run-1", subject="P4.1", command="plan-run"):
    return {
        "schema_version": "terminal-delivery-receipt/v1",
        "plan_id": "PLAN",
        "subject": subject,
        "next_exact": "$ task:plan-run PLAN P4.2",
        "recommendation": "Run P4.2.",
        "journal": {"run_id": run_id, "command": command},
    }


def continuity(outcome="terminal"):
    return {
        "schema_version": "session-continuity-decision/v1", "outcome": outcome,
        "reason": "terminal-evidence" if outcome == "terminal" else "compatible-active-work",
        "evidence": ["batch:" + "0" * 64],
        "runnable": outcome not in {"waiting-owner", "terminal"},
    }


class TerminalAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.clock = [1000.0]
        self.directory = tempfile.TemporaryDirectory()
        self.store = terminal_admission.FileStore(Path(self.directory.name), clock=lambda: self.clock[0])
        self.identity = terminal_admission.Identity(
            plan_id="PLAN", subject="P4.1", command="plan-run", run_id="run-1",
            task_session="task-thread-1", provider="codex", provider_session="thread-1", turn_id="turn-1",
        )

    def tearDown(self):
        self.directory.cleanup()

    def arm(self, *, outcome="continue-root"):
        return terminal_admission.arm(
            self.store, self.identity, continuity(outcome), progress_fingerprint="a" * 64,
            ttl_seconds=60,
        )

    def test_no_lease_is_a_noop_for_an_ordinary_conversation(self):
        verdict = terminal_admission.evaluate(
            self.store, self.identity, continuity(), receipt_reader=receipt,
            proposed_message="ordinary chat",
        )
        self.assertEqual(verdict.reason, "NOT_APPLICABLE")
        self.assertFalse(verdict.final_allowed)

    def test_open_run_needs_no_lease_and_observation_does_not_close_it(self):
        root = Path(self.directory.name)
        path = root / "plans/PLAN/journal.jsonl"
        path.parent.mkdir(parents=True)
        def write(result, *, session="thread-1", append=False):
            event = journal.new_entry(plan_id="PLAN", item_id="P4.1", command="plan-run",
                                      actor="sonnet/medium", result=result,
                                      session_id=session, run_id="run-1", attempt=1)
            with path.open("a" if append else "w") as stream:
                stream.write(json.dumps(event) + "\n")
        write("in-progress")
        write("local-repair", append=True)
        denied = terminal_admission.pre_final_open_runs(root, "thread-1")
        self.assertEqual(denied["reason"], "TASK_OPEN_RUN_FINAL_FORBIDDEN")
        self.assertTrue(terminal_admission.pre_final_open_runs(root, "other-thread")["final_allowed"])
        for terminal in ("closed-green", "blocked", "escalated"):
            write("in-progress")
            write(terminal, append=True)
            self.assertTrue(terminal_admission.pre_final_open_runs(root, "thread-1")["final_allowed"])
        events = (root / ".swissknifeman/terminal-admission/events.jsonl").read_text()
        self.assertIn('"state":"in-progress"', events)
        self.assertNotIn("last_assistant_message", events)

    def test_open_run_check_does_not_create_state_for_ordinary_chat(self):
        root = Path(self.directory.name)
        self.assertTrue(terminal_admission.pre_final_open_runs(root, "thread-1")["final_allowed"])
        self.assertFalse((root / ".swissknifeman").exists())

    def test_closed_first_member_does_not_hide_unstarted_workset_remainder(self):
        root = Path(self.directory.name)
        plan = write_valid_plan(root, "WORKSET", layout="v2")
        batch = {"batch_id": "B1", "items": ("P1.1", "P1.2"),
                 "routing_digest": "a" * 64, "spec_digest": "b" * 64}
        checkpoint = task_contract.build_batch_receipt(batch, membership=("P1.1", "P1.2"))
        run_id = "run-workset"
        journal.append(plan, journal.new_entry(
            plan_id=plan.name, item_id="P1.1", command="plan-run",
            actor="implementation/high", result="in-progress", session_id="thread-1",
            run_id=run_id, attempt=1, batch_receipt=checkpoint))
        decision = terminal_policy.build_decision(
            plan, "P1.1", result="closed-green",
            validation=[{"carrier": "fixture", "status": "green",
                         "evidence_ids": ["test:workset"]}])
        journal.append(plan, journal.new_entry(
            plan_id=plan.name, item_id="P1.1", command="plan-run",
            actor="implementation/high", result="closed-green", session_id="thread-1",
            run_id=run_id, attempt=1, decision=decision, batch_receipt=checkpoint))
        verdict = terminal_admission.pre_final_open_runs(root, "thread-1")
        self.assertFalse(verdict["final_allowed"])
        self.assertEqual(verdict["reason"], "TASK_WORKSET_INCOMPLETE")
        self.assertEqual(verdict["worksets"][0]["remaining"], ["P1.2"])

    def test_chat_scope_stop_and_fresh_handoff_require_terminal_receipt(self):
        from task.plan_continuity import WorkEstimate, reduce
        for lifecycle in ("scope-complete", "owner-requested-new-session"):
            with self.subTest(lifecycle=lifecycle):
                decision = reduce(WorkEstimate(True, True, True, True, "sufficient", True,
                    "a" * 64, True, 0, lifecycle=lifecycle, checkpoint="journal:closed-P4.1")).as_dict()
                terminal_admission.arm(self.store, self.identity, decision,
                    progress_fingerprint="b" * 64, ttl_seconds=60)
                rejected = terminal_admission.evaluate(self.store, self.identity, decision,
                    receipt_reader=lambda: receipt(subject="P4.2"),
                    proposed_message=terminal_admission.required_final_message(receipt()))
                self.assertFalse(rejected.final_allowed)
                allowed = terminal_admission.evaluate(self.store, self.identity, decision,
                    receipt_reader=receipt,
                    proposed_message=terminal_admission.required_final_message(receipt()))
                self.assertTrue(allowed.final_allowed)

    def test_active_progress_must_continue(self):
        self.arm()
        verdict = terminal_admission.evaluate(
            self.store, self.identity, continuity("continue-root"), receipt_reader=receipt,
            proposed_message="anything",
        )
        self.assertEqual(verdict.reason, "CONTINUE_ROOT")
        self.assertEqual(verdict.continuation, "continue-root")

    def test_waiting_owner_is_not_recomputed_as_terminal(self):
        self.arm(outcome="waiting-owner")
        verdict = terminal_admission.evaluate(
            self.store, self.identity, continuity("waiting-owner"), receipt_reader=receipt,
            proposed_message="anything",
        )
        self.assertEqual(verdict.reason, "WAITING_OWNER")
        self.assertEqual(verdict.continuation, "waiting-owner")

    def test_terminal_requires_the_exact_machine_authored_message(self):
        lease = self.arm()
        self.refresh_to_terminal(lease)
        expected = terminal_admission.required_final_message(receipt())
        rejected = terminal_admission.evaluate(
            self.store, self.identity, continuity(), receipt_reader=receipt,
            proposed_message=expected + "\nextra",
        )
        self.assertEqual(rejected.reason, "FINAL_MESSAGE_MISMATCH")
        allowed = terminal_admission.evaluate(
            self.store, self.identity, continuity(), receipt_reader=receipt,
            proposed_message=expected,
        )
        self.assertTrue(allowed.final_allowed)
        self.assertEqual(allowed.reason, "FINAL_ALLOWED")

    def test_external_pause_refresh_cannot_admit_terminal(self):
        from task.plan_continuity import WorkEstimate, reduce
        pause = {"reason": "observation", "started_at": "2026-09-10T12:00:00Z",
                 "resume_at": "2026-09-13T12:00:00Z", "observed_at": "2026-09-11T12:00:00Z",
                 "fingerprint": "b" * 64, "runnable_after": "production window complete",
                 "predicate_satisfied": False, "continuation": "task:plan-run PLAN P4.1"}
        decision = reduce(WorkEstimate(True, True, True, True, "sufficient", True,
                                       "a" * 64, True, 0, lifecycle="waiting-external",
                                       checkpoint="artifacts/window.json", external_pause=pause)).as_dict()
        lease = self.arm()
        paused = terminal_admission.refresh(self.store, self.identity, expected_sequence=lease.sequence,
                                            progress_fingerprint="a" * 64, continuity=decision, ttl_seconds=60)
        self.assertEqual(paused.lifecycle, "waiting-external")
        verdict = terminal_admission.evaluate(self.store, self.identity, decision, receipt_reader=receipt,
                                             proposed_message=terminal_admission.required_final_message(receipt()))
        self.assertEqual(verdict.reason, "WAITING_EXTERNAL")
        self.assertFalse(verdict.final_allowed)

    def test_expired_lease_fails_closed(self):
        self.arm()
        self.clock[0] += 61
        verdict = terminal_admission.evaluate(
            self.store, self.identity, continuity(), receipt_reader=receipt,
            proposed_message=terminal_admission.required_final_message(receipt()),
        )
        self.assertEqual(verdict.reason, "LEASE_EXPIRED")

    def test_refresh_requires_material_progress_and_monotonic_sequence(self):
        lease = self.arm()
        with self.assertRaisesRegex(terminal_admission.AdmissionError, "PROGRESS_UNCHANGED"):
            terminal_admission.refresh(
                self.store, self.identity, expected_sequence=lease.sequence,
                progress_fingerprint="a" * 64, continuity=continuity("continue-root"), ttl_seconds=60,
            )
        refreshed = terminal_admission.refresh(
            self.store, self.identity, expected_sequence=lease.sequence,
            progress_fingerprint="b" * 64, continuity=continuity("continue-root"), ttl_seconds=60,
        )
        self.assertEqual(refreshed.sequence, 2)

    def test_waiting_owner_refresh_is_explicit_progress_independent(self):
        lease = self.arm()
        refreshed = terminal_admission.refresh(
            self.store, self.identity, expected_sequence=lease.sequence,
            progress_fingerprint="a" * 64, continuity=continuity("waiting-owner"), ttl_seconds=60,
        )
        self.assertEqual(refreshed.lifecycle, "waiting-owner")

    def refresh_to_terminal(self, lease):
        return terminal_admission.refresh(
            self.store, self.identity, expected_sequence=lease.sequence,
            progress_fingerprint="c" * 64, continuity=continuity("terminal"), ttl_seconds=60,
        )

    def test_compare_and_swap_rejects_duplicate_stop_admission(self):
        self.refresh_to_terminal(self.arm())
        message = terminal_admission.required_final_message(receipt())
        first = terminal_admission.evaluate(
            self.store, self.identity, continuity(), receipt_reader=receipt, proposed_message=message,
        )
        second = terminal_admission.evaluate(
            self.store, self.identity, continuity(), receipt_reader=receipt, proposed_message=message,
        )
        self.assertTrue(first.final_allowed)
        self.assertEqual(second.reason, "LEASE_RELEASED")

    def test_events_are_privacy_minimal_and_crash_resume_is_named(self):
        self.arm()
        sentinel = "do not persist this transcript"
        terminal_admission.evaluate(
            self.store, self.identity, continuity("continue-root"), receipt_reader=receipt,
            proposed_message=sentinel,
        )
        events = (Path(self.directory.name) / "events.jsonl").read_text(encoding="utf-8")
        self.assertNotIn(sentinel, events)
        self.assertIn("observed_message_sha256", events)
        self.store.path_for(self.identity).write_text("{bad", encoding="utf-8")
        verdict = terminal_admission.evaluate(
            self.store, self.identity, continuity(), receipt_reader=receipt, proposed_message="x",
        )
        self.assertEqual(verdict.reason, "LEASE_INVALID")
        self.assertEqual(verdict.recovery, "re-arm")

    def test_terminal_continuity_must_be_the_refreshed_p1_3_decision(self):
        self.arm()
        verdict = terminal_admission.evaluate(
            self.store, self.identity, continuity(), receipt_reader=receipt,
            proposed_message=terminal_admission.required_final_message(receipt()),
        )
        self.assertEqual(verdict.reason, "CONTINUITY_STALE")

    def test_rearm_recovers_released_expired_and_corrupted_lease(self):
        lease = self.refresh_to_terminal(self.arm())
        terminal_admission.evaluate(
            self.store, self.identity, continuity(), receipt_reader=receipt,
            proposed_message=terminal_admission.required_final_message(receipt()),
        )
        rearmed = self.arm()
        self.assertEqual(rearmed.sequence, 1)
        self.clock[0] += 61
        self.assertEqual(self.arm().sequence, 1)
        self.store.path_for(self.identity).write_text("{bad", encoding="utf-8")
        self.assertEqual(self.arm().sequence, 1)

    def test_independent_runs_have_independent_leases(self):
        self.arm()
        another = terminal_admission.Identity(
            plan_id="PLAN", subject="P4.2", command="plan-run", run_id="run-2",
            task_session="task-thread-2", provider="codex", provider_session="thread-2", turn_id="turn-2",
        )
        lease = terminal_admission.arm(
            self.store, another, continuity("continue-root"), progress_fingerprint="d" * 64,
            ttl_seconds=60,
        )
        self.assertEqual(lease.identity, another)

    def test_next_turn_of_the_same_provider_run_keeps_the_active_lease(self):
        self.arm()
        next_turn = terminal_admission.Identity(
            plan_id="PLAN", subject="P4.1", command="plan-run", run_id="run-1",
            task_session="task-thread-1", provider="codex", provider_session="thread-1", turn_id="turn-2",
        )
        verdict = terminal_admission.evaluate(
            self.store, next_turn, continuity("continue-root"), receipt_reader=receipt,
            proposed_message="anything",
        )
        self.assertEqual(verdict.reason, "CONTINUE_ROOT")

    def test_cli_check_no_lease_returns_machine_readable_verdict(self):
        output = terminal_admission.main([
            "check", "--state-dir", self.directory.name, "--plan", "PLAN", "--subject", "P4.1",
            "--command", "plan-run", "--run-id", "run-1", "--provider", "codex",
            "--task-session", "task-thread-1", "--provider-session", "thread-1", "--turn-id", "turn-1",
            "--continuity-json", json.dumps(continuity()),
            "--message", "ordinary chat",
        ])
        self.assertEqual(output, 0)


if __name__ == "__main__":
    unittest.main()
