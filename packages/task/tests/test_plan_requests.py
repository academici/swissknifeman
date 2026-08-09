"""P5.4 durable queue: ownership, continuation and opt-in join boundaries."""
import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from task import plan_gates, plan_lint, plan_requests, plan_returns


DATA = Path(__file__).resolve().parent / "data" / "plan-v2"


def request_value(*, decision_id="Q1", phase_id="P0", item_id="P0.1"):
    continuation = {"root_session_id": "session-1", "root_run_id": "run-1",
                    "target": {"plan_id": "plan-v2", "item_id": item_id,
                               "resume_command": "task:plan-run plan-v2 " + item_id},
                    "capabilities": {"snapshot_id": "cap-1", "digest": "a" * 64,
                                     "available": ["filesystem"]}, "preferred_mode": "resume-root"}
    return {"contract_version": "v1", "decision_id": decision_id, "action_version": 1,
            "kind": "authorization", "decision_class": "scope_change",
            "subject": {"plan_id": "plan-v2", "phase_id": phase_id, "item_id": item_id},
            "action_digest": "b" * 64, "canonical_action": {}, "material_fields": [],
            "options": [{"id": "approve", "outcome": "apply", "action_ref": "x", "evidence_refs": []},
                        {"id": "reject", "outcome": "reject", "action_ref": None, "evidence_refs": []}],
            "default_option": None, "on_timeout": "park", "expires_at": "2099-01-01T00:00:00Z",
            "evidence": [], "policy_digest": "c" * 64, "attempted": [], "continuation": continuation}


class PlanRequestsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.plan = Path(self.tmp.name) / "plan-v2"
        shutil.copytree(DATA, self.plan)

    def _response(self, request):
        return {"decision_id": request["decision_id"], "action_version": 1,
                "selected_option": "approve", "resolver": "owner", "resolver_id": "owner:1",
                "policy_digest": request["policy_digest"], "action_digest": request["action_digest"],
                "reason_code": "P5_DECISION_OWNER_APPROVED", "provenance": {"source_system": "git",
                "record_id": "r1", "record_version": "1", "verified": True}, "at": "2099-01-01T00:00:00Z"}

    def test_request_parks_only_subject_and_response_resumes_same_root(self):
        value = request_value()
        plan_requests.request(self.plan, value)
        self.assertIn("Q1", plan_requests.states(self.plan))
        plan_requests.claim(self.plan, "Q1", resolver_id="owner:1", lease_expires_at="2099-01-01T00:00:00Z")
        resolved = plan_requests.resolve(self.plan, "Q1", self._response(value), resolver_id="owner:1",
                                         current_continuation=value["continuation"])
        self.assertEqual(resolved["continuation"]["mode"], "resume-root")
        events = [json.loads(line) for line in (self.plan / "journal.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(events[-1]["item_id"], "P0.1")
        self.assertEqual(events[-1]["result"], "in-progress")

    def test_lease_and_continuation_mismatch_fail_closed(self):
        value = request_value()
        plan_requests.request(self.plan, value)
        plan_requests.claim(self.plan, "Q1", resolver_id="owner:1", lease_expires_at="2099-01-01T00:00:00Z")
        with self.assertRaisesRegex(plan_requests.RequestError, "active resolver lease"):
            plan_requests.claim(self.plan, "Q1", resolver_id="owner:2", lease_expires_at="2099-01-01T00:00:00Z")
        bad = copy.deepcopy(value["continuation"])
        bad["root_run_id"] = "other"
        with self.assertRaisesRegex(plan_requests.RequestError, "continuation identity mismatch"):
            plan_requests.resolve(self.plan, "Q1", self._response(value), resolver_id="owner:1", current_continuation=bad)

    def test_cold_start_fallback_requires_explicit_reason(self):
        value = request_value()
        plan_requests.request(self.plan, value)
        plan_requests.claim(self.plan, "Q1", resolver_id="owner:1", lease_expires_at="2099-01-01T00:00:00Z")
        with self.assertRaisesRegex(plan_requests.RequestError, "requires exact fallback reason"):
            plan_requests.resolve(self.plan, "Q1", self._response(value), resolver_id="owner:1", resume_available=False)
        result = plan_requests.resolve(self.plan, "Q1", self._response(value), resolver_id="owner:1",
                                       resume_available=False, fallback_reason="root session expired")
        self.assertEqual(result["continuation"]["mode"], "cold-start-root")

    def test_render_is_deterministic_and_join_is_opt_in(self):
        plan_requests.request(self.plan, request_value())
        first = self.plan / "a.md"
        second = self.plan / "b.md"
        plan_requests.render(self.plan, out=first)
        plan_requests.render(self.plan, out=second)
        self.assertEqual(first.read_bytes(), second.read_bytes())
        diag = plan_lint.Diagnostics()
        plan_gates.lint_return_loop(self.plan, "v2", diag)
        self.assertFalse(any(plan_gates.DECISION_QUEUE_GATE_ID in line for line in diag.errors))
        plan_md = self.plan / "plan.md"
        plan_md.write_text(plan_md.read_text(encoding="utf-8").replace(
            "| visibility | private |", "| visibility | private |\n| Decision Queue Gate | v1 |"), encoding="utf-8")
        diag = plan_lint.Diagnostics()
        plan_gates.lint_return_loop(self.plan, "v2", diag)
        self.assertTrue(any("P0" in line and "Q1" in line for line in diag.errors), diag.errors)

    def test_forbidden_content_and_size_are_rejected_before_append(self):
        value = request_value()
        value["model_reasoning"] = "no"
        with self.assertRaisesRegex(plan_requests.RequestError, "FORBIDDEN"):
            plan_requests.request(self.plan, value)
        oversized = request_value()
        oversized["action"] = {"payload": "x" * 20000}
        with self.assertRaisesRegex(plan_requests.RequestError, "TOO_LARGE"):
            plan_requests.request(self.plan, oversized)

    def test_return_loop_owner_gate_uses_references_and_parks_only_subject(self):
        continuation = request_value(item_id="P1.1")["continuation"]
        events = plan_returns.dispatch_owner_gates(
            self.plan, continuations={"P1.1": continuation},
            expires_at="2099-01-01T00:00:00Z")
        self.assertEqual(len(events), 1)
        request = events[0]["request"]
        self.assertEqual(request["kind"], "authorization")
        self.assertEqual(request["on_timeout"], "park")
        self.assertEqual(request["decision_class"], "authority_change")
        self.assertNotIn("owner_packet", request["canonical_action"]["action"])
        self.assertTrue(request["evidence"])
        self.assertTrue(all(row["carrier"] == "journal.jsonl" for row in request["evidence"]))
        state = (self.plan / "phases/P1/P1.1.state.md").read_text(encoding="utf-8")
        self.assertIn("**Status:** 🔴 Blocked", state)
        other = (self.plan / "phases/P0/P0.1.state.md").read_text(encoding="utf-8")
        self.assertIn("**Status:** 🟢 Done", other)


if __name__ == "__main__":
    unittest.main()
