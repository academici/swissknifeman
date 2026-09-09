"""P5.4 durable queue: ownership, continuation and opt-in join boundaries."""
import copy
import json
import shutil
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from task import plan_authority, plan_gates, plan_item_state, plan_lint, plan_requests, plan_returns, plan_status


DATA = Path(__file__).resolve().parent / "data" / "plan-v2"


class TestDecisionRequestSchemaLocation(unittest.TestCase):
    def test_runtime_contract_is_package_owned(self):
        self.assertEqual(
            plan_requests._CONTRACT_PATH,
            Path(__file__).resolve().parents[1] / "configs" / "decision-request-v1.schema.json",
        )
        self.assertNotIn("plans", plan_requests._CONTRACT_PATH.parts)
        self.assertEqual(json.loads(plan_requests._CONTRACT_PATH.read_text(encoding="utf-8"))["contract_version"], "v1")
P5_DATA = Path(__file__).resolve().parent / "data" / "plan-v2-p5"


def request_value(*, decision_id="Q1", phase_id="P0", item_id="P0.1", kind="authorization"):
    continuation = {"root_session_id": "session-1", "root_run_id": "run-1",
                    "target": {"plan_id": "plan-v2", "item_id": item_id,
                               "resume_command": "task:plan-run plan-v2 " + item_id},
                    "capabilities": {"snapshot_id": "cap-1", "digest": "a" * 64,
                                     "available": ["filesystem"]}, "preferred_mode": "resume-root"}
    raw = {"decision_id": decision_id, "action_version": 1,
            "kind": kind, "decision_class": "scope_change",
            "subject": {"plan_id": "plan-v2", "phase_id": phase_id, "item_id": item_id},
            "action": {"type": "fixture-scope-change", "requires_authorization": kind == "authorization",
                       "affected_surfaces": ["fixture"], "declared_scope": ["fixture"],
                       "frozen_contract_change": False, "closed_set_extension": False,
                       "reversible": True, "decision_recorded": True},
            "options": [{"id": "approve", "outcome": "apply", "action_ref": "x", "evidence_refs": []},
                        {"id": "escalate", "outcome": "escalate", "action_ref": None, "evidence_refs": []},
                        {"id": "park", "outcome": "park", "action_ref": None, "evidence_refs": []},
                        {"id": "reject", "outcome": "reject", "action_ref": None, "evidence_refs": []}],
            "default_option": None, "on_timeout": "park", "expires_at": "2099-01-01T00:00:00Z",
            "evidence": [], "attempted": [], "continuation": continuation}
    durable = plan_requests.prepare_request(raw)
    raw.update({key: durable[key] for key in ("contract_version", "action_digest", "canonical_action",
                                               "material_fields", "policy_digest")})
    return raw


class PlanRequestsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.plan = Path(self.tmp.name) / "plan-v2"
        shutil.copytree(DATA, self.plan)

    def _response(self, request, *, option="approve"):
        return {"decision_id": request["decision_id"], "action_version": 1,
                "selected_option": option, "resolver": "owner", "resolver_id": "owner:1",
                "policy_digest": request["policy_digest"], "action_digest": request["action_digest"],
                "reason_code": "P5_DECISION_OWNER_APPROVED", "provenance": {"source_system": "git",
                "record_id": "r1", "record_version": "1", "verified": True}, "at": "2099-01-01T00:00:00Z"}

    def _auto_answer_pair(self, request, *, option="approve", reclassified_to="clarification"):
        """Return one contract-valid policy answer without bypassing queue validation."""
        after = {"approve": "a", "park": "b", "reject": "c", "escalate": "d"}[option] * 64
        response = self._response(request, option=option)
        response.update({"resolver": "policy", "resolver_id": "policy:fixture",
                         "reclassified_to": reclassified_to, "action_digest": after})
        event = {"decision_id": request["decision_id"], "question_class": "plan",
                 "resolver_id": "policy:fixture", "source_system": "git",
                 "source_record_id": "r1", "source_record_version": "1",
                 "before_digest": request["action_digest"], "after_digest": after,
                 "provenance_verified": True, "policy_digest": request["policy_digest"],
                 "reclassified_action_digest": after, "reclassified_to": reclassified_to}
        return event, response

    def test_request_parks_only_subject_and_response_resumes_same_root(self):
        value = request_value()
        plan_requests.request(self.plan, value)
        self.assertIn("Q1", plan_requests.states(self.plan))
        plan_requests.claim(self.plan, "Q1", resolver_id="owner:1", lease_expires_at="2099-01-01T00:00:00Z")
        resolved = plan_requests.resolve(self.plan, "Q1", self._response(value), resolver_id="owner:1",
                                         current_continuation=value["continuation"])
        self.assertEqual(resolved["continuation"]["mode"], "resume-root")
        self.assertEqual(resolved["continuation"]["decision"]["outcome"], "continue-root")
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
        with self.assertRaisesRegex(plan_requests.RequestError, "exact fallback reason"):
            plan_requests.resolve(self.plan, "Q1", self._response(value), resolver_id="owner:1",
                                  resume_available=False, fallback_reason="root session expired")
        result = plan_requests.resolve(
            self.plan, "Q1", self._response(value), resolver_id="owner:1",
            resume_available=False, fallback_reason="owner-pause-no-resume")
        self.assertEqual(result["continuation"]["mode"], "cold-start-root")
        self.assertEqual(result["continuation"]["decision"]["reason"],
                         "owner-pause-no-resume")

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
        self.assertFalse(diag.errors, diag.errors)

    def test_forbidden_content_and_size_are_rejected_before_append(self):
        value = request_value()
        value["model_reasoning"] = "no"
        with self.assertRaisesRegex(plan_requests.RequestError, "FORBIDDEN"):
            plan_requests.request(self.plan, value)
        oversized = request_value()
        for key in ("contract_version", "action_digest", "canonical_action", "material_fields", "policy_digest"):
            oversized.pop(key)
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
        self.assertIn("**Status:** 🟡 In progress", state)
        other = (self.plan / "phases/P0/P0.1.state.md").read_text(encoding="utf-8")
        self.assertIn("**Status:** 🟢 Done", other)

    def test_schema_dialect_is_fully_consumed(self):
        schema = plan_requests._schema()
        used = set()
        def walk(value):
            if isinstance(value, dict):
                used.update(set(value) & plan_requests._SCHEMA_KEYWORDS)
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)
        walk(schema["request"])
        walk(schema["response"])
        self.assertEqual(used, plan_requests._SCHEMA_KEYWORDS)
        self.assertEqual(["unsupported frozen schema keyword at probe: oneOf"],
                         plan_requests._shape_errors({}, {"type": "object", "oneOf": []}, schema, "probe"))

    def test_invalid_ingress_is_atomic(self):
        paths = (self.plan / "decisions" / "queue.jsonl", self.plan / "journal.jsonl",
                 self.plan / "phases/P0/P0.1.state.md", self.plan / "status.md")
        before = [path.read_bytes() if path.exists() else None for path in paths]
        value = request_value()
        value["kind"] = "NOT_A_KIND"
        with self.assertRaises(plan_requests.RequestError):
            plan_requests.request(self.plan, value)
        self.assertEqual(before, [path.read_bytes() if path.exists() else None for path in paths])

    def test_response_outcome_drives_subject_state(self):
        for option in ("park", "escalate", "reject"):
            with self.subTest(option=option):
                self.setUp()
                value = request_value(decision_id="Q-" + option)
                plan_requests.request(self.plan, value)
                plan_requests.claim(self.plan, value["decision_id"], resolver_id="owner:1", lease_expires_at="2099-01-01T00:00:00Z")
                result = plan_requests.resolve(self.plan, value["decision_id"], self._response(value, option=option), resolver_id="owner:1")
                self.assertNotIn("continuation", result)
                self.assertIn("**Status:** 🔴 Blocked", (self.plan / "phases/P0/P0.1.state.md").read_text())
                plan_item_state.build_states(self.plan, item_id="P0.1", check=True)
                plan_status.build_status(self.plan, check=True)

    def test_terminal_decision_transition_carries_reducer_evidence(self):
        value = request_value(decision_id="Q-terminal-decision")
        plan_requests.request(self.plan, value)
        plan_requests.claim(self.plan, value["decision_id"], resolver_id="owner:1",
                            lease_expires_at="2099-01-01T00:00:00Z")
        plan_requests.resolve(
            self.plan, value["decision_id"], self._response(value, option="reject"),
            resolver_id="owner:1",
        )
        entry = json.loads((self.plan / "journal.jsonl").read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(entry["result"], "blocked")
        self.assertEqual(entry["decision"]["action"], "authority-denied")
        self.assertEqual(entry["decision"]["evidence_ids"], ["decision:Q-terminal-decision"])

    def test_auto_answer_requires_contract_pair_and_reclassification(self):
        value = request_value(decision_id="Q-auto", kind="clarification")
        plan_requests.request(self.plan, value)
        with self.assertRaisesRegex(plan_requests.RequestError, "requires response"):
            plan_requests.append_auto_answer(self.plan, {"decision_id": "Q-auto"})
        response = self._response(value)
        after = "d" * 64
        response.update({"resolver": "policy", "resolver_id": "policy:fixture", "reclassified_to": "authorization",
                         "action_digest": after})
        event = {"decision_id": "Q-auto", "question_class": "plan", "resolver_id": "policy:fixture",
                 "source_system": "git", "source_record_id": "r1", "source_record_version": "1",
                 "before_digest": value["action_digest"], "after_digest": after,
                 "provenance_verified": True, "policy_digest": value["policy_digest"],
                 "reclassified_action_digest": after, "reclassified_to": "authorization"}
        plan_requests.append_auto_answer(self.plan, event, response=response)
        self.assertIn("**Status:** 🟢 Done", (self.plan / "phases/P0/P0.1.state.md").read_text())

    def test_auto_answer_producer_creates_the_contract_valid_pair(self):
        value = request_value(decision_id="Q-produced-auto", kind="clarification")
        value["options"][0]["id"] = "apply"
        for field in ("contract_version", "action_digest", "canonical_action", "material_fields", "policy_digest"):
            value.pop(field)
        plan_requests.request(self.plan, value)
        producer_input = copy.deepcopy(value)
        producer_input["missing_fields"] = ["carrier"]
        produced = plan_authority.auto_answer_clarification(
            producer_input, question_class="plan_carrier", field="carrier",
            sources={"plan_carrier": {"value": "plan.md", "record_id": "plan.md",
                                      "record_version": "fixture", "at": "2099-01-01T00:00:00Z"}})
        self.assertIsInstance(produced, dict)
        event = plan_requests.append_auto_answer(self.plan, produced["event"], response=produced["response"])
        self.assertEqual(event["response"]["resolver"], "policy")
        self.assertTrue(event["response"]["provenance"]["verified"])
        self.assertEqual(plan_requests.unresolved_for_phase(self.plan, "P0"), [])
        self.assertIn("**Status:** 🟡 In progress", (self.plan / "phases/P0/P0.1.state.md").read_text())

    def test_return_loop_producer_outcomes_are_subject_local(self):
        for option in ("continue", "park", "reject"):
            with self.subTest(option=option):
                plan = Path(self.tmp.name) / f"plan-v2-p5-{option}"
                shutil.copytree(P5_DATA, plan)
                (plan / "decisions" / "queue.jsonl").unlink()
                continuation = {"root_session_id": "fixture-session", "root_run_id": "fixture-run",
                                "target": {"plan_id": plan.name, "item_id": "P1.1",
                                           "resume_command": f"task:plan-run {plan.name} P1.1"},
                                "capabilities": {"snapshot_id": "cap-1", "digest": "a" * 64,
                                                 "available": ["filesystem"]}, "preferred_mode": "resume-root"}
                other_before = (plan / "phases/P1/P1.2.state.md").read_bytes()
                created = plan_returns.dispatch_owner_gates(
                    plan, continuations={"P1.1": continuation}, expires_at="2099-01-01T00:00:00Z")
                self.assertEqual(1, len(created))
                request = created[0]["request"]
                plan_requests.claim(plan, request["decision_id"], resolver_id="owner:1",
                                    lease_expires_at="2099-01-01T00:00:00Z")
                resolved = plan_requests.resolve(
                    plan, request["decision_id"], self._response(request, option=option), resolver_id="owner:1",
                    current_continuation=continuation if option == "continue" else None)
                self.assertEqual("resume-root" if option == "continue" else None,
                                 resolved.get("continuation", {}).get("mode"))
                expected = "🟡 In progress" if option == "continue" else "🔴 Blocked"
                self.assertIn(f"**Status:** {expected}", (plan / "phases/P1/P1.1.state.md").read_text())
                self.assertEqual(other_before, (plan / "phases/P1/P1.2.state.md").read_bytes())

    def test_projection_failure_never_releases_continuation(self):
        value = request_value(decision_id="Q-fail")
        with mock.patch("task.plan_item_state.build_states", side_effect=RuntimeError("injected")):
            with self.assertRaisesRegex(plan_requests.RequestError, "projection failed"):
                plan_requests.request(self.plan, value)
        events = [json.loads(line) for line in (self.plan / "journal.jsonl").read_text().splitlines()]
        self.assertEqual(events[-1]["result"], "decision-pending")

    def test_auto_answer_semantic_outcome_is_consistent_across_consumers(self):
        value = request_value(decision_id="Q-auto-semantic", kind="clarification")
        plan_requests.request(self.plan, value)
        response = self._response(value)
        after = "d" * 64
        response.update({"resolver": "policy", "resolver_id": "policy:fixture",
                         "reclassified_to": "authorization", "action_digest": after})
        event = {"decision_id": value["decision_id"], "question_class": "plan",
                 "resolver_id": "policy:fixture", "source_system": "git",
                 "source_record_id": "r1", "source_record_version": "1",
                 "before_digest": value["action_digest"], "after_digest": after,
                 "provenance_verified": True, "policy_digest": value["policy_digest"],
                 "reclassified_action_digest": after, "reclassified_to": "authorization"}
        plan_requests.append_auto_answer(self.plan, event, response=response)

        state = plan_requests.states(self.plan)[value["decision_id"]]
        self.assertEqual("pending-authorization", plan_requests.semantic_outcome(state))
        self.assertIn("**Status:** 🟢 Done",
                      (self.plan / "phases/P0/P0.1.state.md").read_text())
        self.assertIn(value["decision_id"], {
            row["decision_id"] for records in plan_requests.pending_groups(self.plan).values()
            for row in records
        })
        self.assertEqual([value["decision_id"]], plan_requests.unresolved_for_phase(self.plan, "P0"))
        plan_requests.render(self.plan)
        plan_requests.render(self.plan, check=True)
        plan_md = self.plan / "plan.md"
        plan_md.write_text(plan_md.read_text(encoding="utf-8").replace(
            "| visibility | private |", "| visibility | private |\n| Decision Queue Gate | v1 |"),
            encoding="utf-8")
        diag = plan_lint.Diagnostics()
        with mock.patch("task.plan_layout.is_terminal_phase", return_value=True), \
                mock.patch("task.plan_gate_activation.active_phases", return_value={"P0"}):
            plan_gates.lint_return_loop(self.plan, "v2", diag)
        self.assertTrue(any(value["decision_id"] in line for line in diag.errors), diag.errors)

    def test_terminal_auto_answer_is_single_use_in_ingress_and_reducer(self):
        for option, outcome in (("approve", "apply"), ("park", "park"),
                                ("reject", "reject"), ("escalate", "escalate")):
            with self.subTest(outcome=outcome):
                self.setUp()
                value = request_value(decision_id=f"Q-terminal-{outcome}", kind="clarification")
                plan_requests.request(self.plan, value)
                event, policy_response = self._auto_answer_pair(value, option=option)
                plan_requests.append_auto_answer(self.plan, event, response=policy_response)
                self.assertEqual(outcome, plan_requests.semantic_outcome(
                    plan_requests.states(self.plan)[value["decision_id"]]))
                queue = self.plan / "decisions" / "queue.jsonl"
                before = queue.read_bytes()
                owner_response = self._response(value, option="reject")
                owner_response["reclassified_to"] = "authorization"
                with self.assertRaisesRegex(plan_requests.RequestError, "already resolved"):
                    plan_requests.claim(self.plan, value["decision_id"], resolver_id="owner:1",
                                        lease_expires_at="2099-01-01T00:00:00Z")
                with self.assertRaisesRegex(plan_requests.RequestError, "already resolved"):
                    plan_requests.resolve(self.plan, value["decision_id"], owner_response,
                                          resolver_id="owner:1")
                self.assertEqual(before, queue.read_bytes())

                illegal_claim = {"type": "claim", "at": "2099-01-01T00:00:00Z",
                                 "actor": "owner", "decision_id": value["decision_id"],
                                 "resolver_id": "owner:1", "lease_expires_at": "2099-01-01T00:00:00Z"}
                queue.write_bytes(before + plan_requests._canonical(illegal_claim) + b"\n")
                with self.assertRaisesRegex(plan_requests.RequestError, "already resolved"):
                    plan_requests.states(self.plan)

                illegal_response = {"type": "response", "at": "2099-01-01T00:00:00Z",
                                    "actor": "owner", "decision_id": value["decision_id"],
                                    "resolver_id": "owner:1", "response": owner_response,
                                    "outcome": "reject"}
                queue.write_bytes(before + plan_requests._canonical(illegal_response) + b"\n")
                with self.assertRaisesRegex(plan_requests.RequestError, "already resolved"):
                    plan_requests.states(self.plan)

    def test_pending_authorization_auto_answer_preserves_owner_flow(self):
        value = request_value(decision_id="Q-pending-owner-flow", kind="clarification")
        plan_requests.request(self.plan, value)
        event, policy_response = self._auto_answer_pair(value, reclassified_to="authorization")
        plan_requests.append_auto_answer(self.plan, event, response=policy_response)
        self.assertEqual("pending-authorization", plan_requests.semantic_outcome(
            plan_requests.states(self.plan)[value["decision_id"]]))
        plan_requests.claim(self.plan, value["decision_id"], resolver_id="owner:1",
                            lease_expires_at="2099-01-01T00:00:00Z")
        response = self._response(value)
        response["reclassified_to"] = "authorization"
        resolved = plan_requests.resolve(self.plan, value["decision_id"], response,
                                         resolver_id="owner:1",
                                         current_continuation=value["continuation"])
        self.assertEqual("resume-root", resolved["continuation"]["mode"])
        self.assertEqual(["request", "auto_answer", "claim", "response"],
                         [row["type"] for row in plan_requests._read_events(self.plan)])

    def test_request_accepts_two_substantive_plus_mandatory(self):
        value = request_value(decision_id="Q-two-substantive")
        plan_requests.request(self.plan, value)
        self.assertIn(value["decision_id"], plan_requests.states(self.plan))

    def test_request_accepts_five_substantive_plus_mandatory(self):
        value = request_value(decision_id="Q-five-substantive")
        for option_id in ("option-3", "option-4", "option-5"):
            value["options"].append({"id": option_id, "outcome": "park", "action_ref": None,
                                     "evidence_refs": []})
        for field in ("contract_version", "action_digest", "canonical_action", "material_fields",
                      "policy_digest"):
            value.pop(field)
        plan_requests.request(self.plan, value)
        self.assertIn(value["decision_id"], plan_requests.states(self.plan))

    def test_request_rejects_mandatory_only(self):
        value = request_value(decision_id="Q-mandatory-only")
        value["options"] = [row for row in value["options"]
                            if row["id"] in {"escalate", "reject"}]
        for field in ("contract_version", "action_digest", "canonical_action", "material_fields",
                      "policy_digest"):
            value.pop(field)
        with self.assertRaisesRegex(plan_requests.RequestError, "frozen bounds"):
            plan_requests.request(self.plan, value)

    def test_request_projection_failure_is_exactly_retryable(self):
        value = request_value(decision_id="Q-request-retry")
        original = plan_item_state.build_states
        calls = 0

        def fail_once(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("injected request projection failure")
            return original(*args, **kwargs)

        with mock.patch("task.plan_item_state.build_states", side_effect=fail_once):
            with self.assertRaisesRegex(plan_requests.RequestError, "projection failed"):
                plan_requests.request(self.plan, value)
        retried = plan_requests.request(self.plan, value)
        events = [json.loads(line) for line in (self.plan / "decisions" / "queue.jsonl").read_text().splitlines()]
        self.assertEqual(1, sum(row["type"] == "request" for row in events))
        self.assertEqual(value["decision_id"], retried["decision_id"])
        plan_item_state.build_states(self.plan, item_id="P0.1", check=True)
        plan_status.build_status(self.plan, check=True)
        plan_requests.render(self.plan, check=True)

    def test_resolve_projection_failure_is_exactly_retryable(self):
        value = request_value(decision_id="Q-resolve-retry")
        plan_requests.request(self.plan, value)
        plan_requests.claim(self.plan, value["decision_id"], resolver_id="owner:1",
                            lease_expires_at="2099-01-01T00:00:00Z")
        original = plan_item_state.build_states
        calls = 0

        def fail_once(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("injected resolve projection failure")
            return original(*args, **kwargs)

        response = self._response(value)
        with mock.patch("task.plan_item_state.build_states", side_effect=fail_once):
            with self.assertRaisesRegex(plan_requests.RequestError, "projection failed"):
                plan_requests.resolve(self.plan, value["decision_id"], response, resolver_id="owner:1",
                                      current_continuation=value["continuation"])
        events = [json.loads(line) for line in (self.plan / "decisions" / "queue.jsonl").read_text().splitlines()]
        responses = [row for row in events if row["type"] == "response"]
        self.assertEqual(1, len(responses))
        self.assertNotIn("continuation", responses[0])
        retried = plan_requests.resolve(self.plan, value["decision_id"], response, resolver_id="owner:1",
                                        current_continuation=value["continuation"])
        self.assertEqual("resume-root", retried["continuation"]["mode"])
        events = [json.loads(line) for line in (self.plan / "decisions" / "queue.jsonl").read_text().splitlines()]
        self.assertEqual(1, sum(row["type"] == "response" for row in events))
        plan_item_state.build_states(self.plan, item_id="P0.1", check=True)
        plan_status.build_status(self.plan, check=True)
        plan_requests.render(self.plan, check=True)


if __name__ == "__main__":
    unittest.main()
