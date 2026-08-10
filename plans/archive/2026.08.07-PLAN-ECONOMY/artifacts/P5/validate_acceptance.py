#!/usr/bin/env python3
"""Produce and verify the P5.5 decision-queue acceptance evidence."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import shutil
import tempfile
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[4]

import sys
sys.path.insert(0, str(ROOT / "packages/task/lib"))

from task import (  # noqa: E402
    plan_authority, plan_gates, plan_item_state, plan_lint, plan_requests,
    plan_returns, plan_status,
)


FROZEN_INPUTS = (
    "plans/2026.08.07-PLAN-ECONOMY/root/contracts/decision-request-v1.schema.json",
    "plans/2026.08.07-PLAN-ECONOMY/root/contracts/authority-frame-v1.md",
    "plans/2026.08.07-PLAN-ECONOMY/root/contracts/return-loop-v1.spec.json",
    "packages/task/configs/authority-frame.json",
)
STATUS = re.compile(r"^\*\*Status:\*\* (.+)$", re.MULTILINE)


def canonical_bytes(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def fail(message: str) -> None:
    raise SystemExit(f"acceptance failed: {message}")


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frozen_digests() -> dict[str, str]:
    return {relative: digest(ROOT / relative) for relative in FROZEN_INPUTS}


def subject_status(plan_dir: Path, item_id: str) -> str:
    phase_id = item_id.split(".", 1)[0]
    content = (plan_dir / "phases" / phase_id / f"{item_id}.state.md").read_text(encoding="utf-8")
    match = STATUS.search(content)
    if match is None:
        fail(f"{item_id} has no generated Status")
    return match.group(1)


def fresh_plan(fixture: Path) -> tuple[tempfile.TemporaryDirectory, Path]:
    directory = tempfile.TemporaryDirectory(prefix="p5.5-acceptance-")
    plan_dir = Path(directory.name) / fixture.name
    shutil.copytree(fixture, plan_dir)
    # The committed queue is regression input only. No acceptance predicate may
    # replay its already-resolved events.
    queue = plan_dir / "decisions" / "queue.jsonl"
    if queue.exists():
        queue.unlink()
    return directory, plan_dir


def continuation(item_id: str) -> dict:
    return {
        "root_session_id": "p5.5-fixture-session",
        "root_run_id": "p5.5-fixture-run",
        "target": {
            "plan_id": "plan-v2-p5", "item_id": item_id,
            "resume_command": f"task:plan-run plan-v2-p5 {item_id}",
        },
        "capabilities": {
            "snapshot_id": "p5.5-fixture-capabilities", "digest": "a" * 64,
            "available": ["filesystem"],
        },
        "preferred_mode": "resume-root",
    }


def clarification_request(decision_id: str = "p5.5-policy-clarification", *,
                          reclassifies_to_authorization: bool = False) -> dict:
    action = {
        "type": "resolve-plan-carrier", "requires_authorization": False,
        "affected_surfaces": ["plan-carrier"], "declared_scope": ["plan-carrier"],
        "frozen_contract_change": False, "closed_set_extension": False,
        "reversible": True, "decision_recorded": True,
    }
    if reclassifies_to_authorization:
        action["requires_authorization_when"] = {"carrier": "owner-authorized"}
    return {
        "decision_id": decision_id, "action_version": 1, "kind": "clarification",
        "decision_class": "constructive",
        "subject": {"plan_id": "plan-v2-p5", "phase_id": "P1", "item_id": "P1.2"},
        "action": action,
        "options": [
            {"id": "apply", "outcome": "apply", "action_ref": "plan.md", "evidence_refs": ["plan.md"]},
            {"id": "park", "outcome": "park", "action_ref": None, "evidence_refs": []},
            {"id": "escalate", "outcome": "escalate", "action_ref": None, "evidence_refs": []},
            {"id": "reject", "outcome": "reject", "action_ref": None, "evidence_refs": []},
        ],
        "default_option": None, "on_timeout": "park", "expires_at": "2099-01-01T00:00:00Z",
        "evidence": [], "attempted": [], "continuation": continuation("P1.2"),
    }


def owner_response(request: dict, option: str) -> dict:
    return {
        "decision_id": request["decision_id"], "action_version": request["action_version"],
        "selected_option": option, "resolver": "owner", "resolver_id": "owner:p5.5",
        "policy_digest": request["policy_digest"], "action_digest": request["action_digest"],
        "reason_code": "P5_DECISION_OWNER_APPROVED",
        "provenance": {"source_system": "git", "record_id": "p5.5-owner-decision",
                       "record_version": "1", "verified": True},
        "at": "2099-01-01T00:00:00Z",
    }


def verify_views(plan_dir: Path, item_id: str) -> bool:
    plan_item_state.build_states(plan_dir, item_id=item_id, check=True)
    plan_status.build_status(plan_dir, check=True)
    plan_requests.render(plan_dir, check=True)
    return True


def queue_counts(plan_dir: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in plan_requests._read_events(plan_dir):
        counts[event["type"]] = counts.get(event["type"], 0) + 1
    return dict(sorted(counts.items()))


def latest_journal_result(plan_dir: Path, item_id: str) -> str:
    events = plan_requests.journal_path_events(plan_dir, item_id)
    require(bool(events), f"{item_id} has no decision journal event")
    result = events[-1].get("result")
    require(isinstance(result, str), f"{item_id} latest journal result is absent")
    return result


def pending_ids(plan_dir: Path) -> list[str]:
    return sorted(row["decision_id"] for records in plan_requests.pending_groups(plan_dir).values()
                  for row in records)


def phase_join_blocks(plan_dir: Path, phase_id: str, decision_id: str) -> bool:
    plan_md = plan_dir / "plan.md"
    plan_md.write_text(plan_md.read_text(encoding="utf-8").replace(
        "| visibility | private |", "| visibility | private |\n| Decision Queue Gate | v1 |"),
        encoding="utf-8")
    diagnostics = plan_lint.Diagnostics()
    with mock.patch("task.plan_layout.is_terminal_phase", return_value=True):
        plan_gates.lint_return_loop(plan_dir, "v2", diagnostics)
    blocked = any(decision_id in line and phase_id in line for line in diagnostics.errors)
    # The synthetic opt-in Meta flag changes the status-view input. Restore its
    # generated freshness before the scenario's common observation boundary.
    plan_status.build_status(plan_dir)
    return blocked


def observations(plan_dir: Path, *, subject_id: str, decision_id: str,
                 continuation_mode: str, retry_count: int = 0,
                 join_blocks: bool = False, substantive_count: int | None = None,
                 mandatory_ids: list[str] | None = None) -> dict:
    fresh = verify_views(plan_dir, subject_id)
    request = plan_requests.states(plan_dir).get(decision_id, {}).get("request", {})
    if substantive_count is None:
        mandatory = {"escalate", "reject"}
        substantive_count = sum(row.get("id") not in mandatory for row in request.get("options", ()))
    if mandatory_ids is None:
        mandatory_ids = sorted(row.get("id") for row in request.get("options", ())
                               if row.get("id") in {"escalate", "reject"})
    return {
        "queue_event_counts": queue_counts(plan_dir),
        "latest_journal_result": latest_journal_result(plan_dir, subject_id),
        "subject_statuses": {"P1.1": subject_status(plan_dir, "P1.1"),
                             "P1.2": subject_status(plan_dir, "P1.2")},
        "pending_decision_ids": pending_ids(plan_dir),
        "unresolved_for_phase": plan_requests.unresolved_for_phase(plan_dir, "P1"),
        "phase_join_blocks": join_blocks,
        "gate_fresh": fresh,
        "continuation_mode": continuation_mode,
        "retry_count": retry_count,
        "substantive_count": substantive_count,
        "mandatory_ids": mandatory_ids,
    }


def policy_scenario(fixture: Path, *, authorization: bool) -> dict:
    directory, plan_dir = fresh_plan(fixture)
    try:
        scenario_id = "policy-authorization-pending" if authorization else "policy-auto-answer-apply"
        raw = clarification_request(scenario_id, reclassifies_to_authorization=authorization)
        requested = plan_requests.request(plan_dir, raw, actor="policy")
        produced = plan_authority.auto_answer_clarification(
            {**copy.deepcopy(raw), "missing_fields": ["carrier"]},
            question_class="plan_carrier", field="carrier",
            sources={"plan_carrier": {"value": "owner-authorized" if authorization else "plan.md",
                                      "record_id": "plan.md", "record_version": "fixture-v1",
                                      "at": "2099-01-01T00:00:00Z"}},
        )
        require(isinstance(produced, dict), "policy producer did not return a contract pair")
        event = plan_requests.append_auto_answer(
            plan_dir, produced["event"], response=produced["response"], actor="policy")
        state = plan_requests.states(plan_dir)[raw["decision_id"]]
        expected_outcome = "pending-authorization" if authorization else "apply"
        require(plan_requests.semantic_outcome(state) == expected_outcome, "wrong policy semantic outcome")
        require(event["response"]["resolver"] == "policy", "policy resolver was not persisted")
        require(event["response"]["provenance"]["verified"] is True, "policy provenance is unverified")
        require(event["event"]["before_digest"] == requested["request"]["action_digest"],
                "policy before digest is not linked")
        require(event["event"]["before_digest"] != event["event"]["after_digest"],
                "policy reclassification did not change digest")
        if authorization:
            require(subject_status(plan_dir, "P1.2") == "🔴 Blocked", "authorization response released subject")
            require(raw["decision_id"] in pending_ids(plan_dir), "authorization response is absent from owner pending")
            require(plan_requests.unresolved_for_phase(plan_dir, "P1") == [raw["decision_id"]],
                    "authorization response is absent from phase join")
            join_blocks = phase_join_blocks(plan_dir, "P1", raw["decision_id"])
            require(join_blocks, "opt-in terminal phase join did not block")
        else:
            require(subject_status(plan_dir, "P1.2") == "🟡 In progress", "policy apply did not resume subject")
            require(plan_requests.unresolved_for_phase(plan_dir, "P1") == [], "resolved policy request remains unresolved")
            join_blocks = False
        require(subject_status(plan_dir, "P1.1") == "🔴 Blocked", "policy changed unrelated subject")
        result = observations(plan_dir, subject_id="P1.2", decision_id=raw["decision_id"],
                              continuation_mode="none", join_blocks=join_blocks)
        return {"id": scenario_id, "observed_outcome": expected_outcome,
                "verified_provenance": True, "reclassified_to": event["event"]["reclassified_to"], **result}
    finally:
        directory.cleanup()


def terminal_auto_answer_single_use_scenario(fixture: Path) -> dict:
    """The policy producer's terminal apply cannot be claimed or overwritten."""
    directory, plan_dir = fresh_plan(fixture)
    try:
        raw = clarification_request("policy-terminal-single-use")
        plan_requests.request(plan_dir, raw, actor="policy")
        produced = plan_authority.auto_answer_clarification(
            {**copy.deepcopy(raw), "missing_fields": ["carrier"]},
            question_class="plan_carrier", field="carrier",
            sources={"plan_carrier": {"value": "plan.md", "record_id": "plan.md",
                                      "record_version": "fixture-v1", "at": "2099-01-01T00:00:00Z"}},
        )
        require(isinstance(produced, dict), "policy producer did not return a contract pair")
        plan_requests.append_auto_answer(plan_dir, produced["event"], response=produced["response"], actor="policy")
        before = queue_counts(plan_dir)
        denied = 0
        try:
            plan_requests.claim(plan_dir, raw["decision_id"], resolver_id="owner:p5.5",
                                lease_expires_at="2099-01-01T00:00:00Z")
        except plan_requests.RequestError as exc:
            require("already resolved" in str(exc), "terminal claim failed for wrong reason")
            denied += 1
        owner = owner_response(plan_requests.states(plan_dir)[raw["decision_id"]]["request"], "reject")
        owner["reclassified_to"] = "authorization"
        try:
            plan_requests.resolve(plan_dir, raw["decision_id"], owner, resolver_id="owner:p5.5")
        except plan_requests.RequestError as exc:
            require("already resolved" in str(exc), "terminal response failed for wrong reason")
            denied += 1
        require(denied == 2, "terminal auto-answer admitted a later owner flow")
        require(queue_counts(plan_dir) == before, "terminal auto-answer ingress changed queue")
        result = observations(plan_dir, subject_id="P1.2", decision_id=raw["decision_id"],
                              continuation_mode="none")
        return {"id": "policy-terminal-auto-answer-single-use", "observed_outcome": "apply",
                "verified_provenance": True, "reclassified_to": produced["event"]["reclassified_to"],
                "denied_owner_operations": denied, **result}
    finally:
        directory.cleanup()


def authorization_owner_flow_scenario(fixture: Path) -> dict:
    """Authorization reclassification is the sole policy-answer path an owner may resolve."""
    directory, plan_dir = fresh_plan(fixture)
    try:
        raw = clarification_request("policy-authorization-owner-flow", reclassifies_to_authorization=True)
        plan_requests.request(plan_dir, raw, actor="policy")
        produced = plan_authority.auto_answer_clarification(
            {**copy.deepcopy(raw), "missing_fields": ["carrier"]},
            question_class="plan_carrier", field="carrier",
            sources={"plan_carrier": {"value": "owner-authorized", "record_id": "plan.md",
                                      "record_version": "fixture-v1", "at": "2099-01-01T00:00:00Z"}},
        )
        require(isinstance(produced, dict), "policy producer did not return a contract pair")
        plan_requests.append_auto_answer(plan_dir, produced["event"], response=produced["response"], actor="policy")
        require(plan_requests.semantic_outcome(plan_requests.states(plan_dir)[raw["decision_id"]]) == "pending-authorization",
                "policy answer did not preserve owner authorization")
        plan_requests.claim(plan_dir, raw["decision_id"], resolver_id="owner:p5.5",
                            lease_expires_at="2099-01-01T00:00:00Z")
        owner = owner_response(plan_requests.states(plan_dir)[raw["decision_id"]]["request"], "apply")
        owner["reclassified_to"] = "authorization"
        resolved = plan_requests.resolve(plan_dir, raw["decision_id"], owner, resolver_id="owner:p5.5",
                                         current_continuation=continuation("P1.2"))
        result = observations(plan_dir, subject_id="P1.2", decision_id=raw["decision_id"],
                              continuation_mode=resolved["continuation"]["mode"])
        require(result["queue_event_counts"] == {"auto_answer": 1, "claim": 1, "request": 1, "response": 1},
                "pending authorization owner flow has wrong queue cardinality")
        return {"id": "policy-authorization-owner-flow", "observed_outcome": "apply",
                "verified_provenance": True, "reclassified_to": "authorization", **result}
    finally:
        directory.cleanup()


def owner_scenario(fixture: Path, option: str) -> dict:
    directory, plan_dir = fresh_plan(fixture)
    try:
        other_before = (plan_dir / "phases/P1/P1.2.state.md").read_bytes()
        expected_continuation = continuation("P1.1")
        created = plan_returns.dispatch_owner_gates(
            plan_dir, continuations={"P1.1": expected_continuation},
            expires_at="2099-01-01T00:00:00Z", actor="return-loop")
        require(len(created) == 1, "P4 producer did not create exactly one owner request")
        request = created[0]["request"]
        require(request["kind"] == "authorization", "P4 request lost authorization kind")
        require("owner_packet" not in request["canonical_action"]["action"], "P4 owner packet was copied")
        plan_requests.claim(plan_dir, request["decision_id"], resolver_id="owner:p5.5",
                            lease_expires_at="2099-01-01T00:00:00Z")
        resolved = plan_requests.resolve(
            plan_dir, request["decision_id"], owner_response(request, option), resolver_id="owner:p5.5",
            current_continuation=expected_continuation if option == "continue" else None)
        mode = resolved.get("continuation", {}).get("mode", "none")
        expected_status = "🟡 In progress" if option == "continue" else "🔴 Blocked"
        require(subject_status(plan_dir, "P1.1") == expected_status, f"{option} produced wrong subject status")
        require((plan_dir / "phases/P1/P1.2.state.md").read_bytes() == other_before,
                f"{option} changed unrelated subject")
        require(mode == ("resume-root" if option == "continue" else "none"),
                f"{option} produced wrong continuation")
        result = observations(plan_dir, subject_id="P1.1", decision_id=request["decision_id"],
                              continuation_mode=mode)
        return {"id": f"owner-{option}", "observed_outcome": "apply" if option == "continue" else option,
                "verified_provenance": True, "reclassified_to": None, **result}
    finally:
        directory.cleanup()


def option_bound_scenario(fixture: Path, substantive_count: int) -> dict:
    directory, plan_dir = fresh_plan(fixture)
    try:
        raw = clarification_request(f"options-{substantive_count}")
        for number in range(3, substantive_count + 1):
            raw["options"].append({"id": f"option-{number}", "outcome": "park",
                                   "action_ref": None, "evidence_refs": []})
        plan_requests.request(plan_dir, raw, actor="bounds")
        result = observations(plan_dir, subject_id="P1.2", decision_id=raw["decision_id"],
                              continuation_mode="none")
        require(result["substantive_count"] == substantive_count, "substantive option count is wrong")
        require(result["mandatory_ids"] == ["escalate", "reject"], "mandatory options are incomplete")
        return {"id": f"options-{substantive_count}-substantive", "observed_outcome": "pending",
                "verified_provenance": True, "reclassified_to": None, **result}
    finally:
        directory.cleanup()


def mandatory_only_scenario(fixture: Path) -> dict:
    directory, plan_dir = fresh_plan(fixture)
    try:
        raw = clarification_request("options-mandatory-only")
        raw["options"] = [row for row in raw["options"] if row["id"] in {"escalate", "reject"}]
        with_error = False
        try:
            plan_requests.request(plan_dir, raw, actor="bounds")
        except plan_requests.RequestError as exc:
            require("frozen bounds" in str(exc), "mandatory-only request failed for wrong reason")
            with_error = True
        require(with_error, "mandatory-only request was appended")
        require(queue_counts(plan_dir) == {}, "mandatory-only request changed queue")
        # A rejected ingress has no transition producer. Materialize the empty
        # deterministic owner view before checking that it is fresh.
        plan_requests.render(plan_dir)
        return {
            "id": "options-mandatory-only-rejected", "observed_outcome": "rejected-before-append",
            "verified_provenance": True, "reclassified_to": None, "queue_event_counts": {},
            "latest_journal_result": "none", "subject_statuses": {
                "P1.1": subject_status(plan_dir, "P1.1"), "P1.2": subject_status(plan_dir, "P1.2")},
            "pending_decision_ids": [], "unresolved_for_phase": [], "phase_join_blocks": False,
            "gate_fresh": verify_views(plan_dir, "P1.2"), "continuation_mode": "none",
            "retry_count": 0, "substantive_count": 0, "mandatory_ids": ["escalate", "reject"],
        }
    finally:
        directory.cleanup()


def request_retry_scenario(fixture: Path) -> dict:
    directory, plan_dir = fresh_plan(fixture)
    try:
        raw = clarification_request("request-projection-retry")
        original = plan_item_state.build_states
        calls = 0

        def fail_once(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("injected request projection failure")
            return original(*args, **kwargs)

        with mock.patch("task.plan_item_state.build_states", side_effect=fail_once):
            with_error = False
            try:
                plan_requests.request(plan_dir, raw, actor="retry")
            except plan_requests.RequestError as exc:
                require("projection failed" in str(exc), "request failure escaped projection seam")
                with_error = True
            require(with_error, "one-shot request failure did not fail")
        plan_requests.request(plan_dir, raw, actor="retry")
        bad = copy.deepcopy(raw)
        bad["action"]["type"] = "different-payload"
        try:
            plan_requests.request(plan_dir, bad, actor="retry")
        except plan_requests.RequestError:
            pass
        else:
            fail("request retry accepted a different payload under the same id")
        result = observations(plan_dir, subject_id="P1.2", decision_id=raw["decision_id"],
                              continuation_mode="none", retry_count=1,
                              join_blocks=phase_join_blocks(plan_dir, "P1", raw["decision_id"]))
        require(result["queue_event_counts"] == {"request": 1}, "request retry duplicated queue event")
        require(result["latest_journal_result"] == "blocked", "request retry did not restore blocked state")
        return {"id": "request-projection-failure-retry", "observed_outcome": "pending",
                "verified_provenance": True, "reclassified_to": None, **result}
    finally:
        directory.cleanup()


def resolve_retry_scenario(fixture: Path) -> dict:
    directory, plan_dir = fresh_plan(fixture)
    try:
        expected_continuation = continuation("P1.1")
        created = plan_returns.dispatch_owner_gates(
            plan_dir, continuations={"P1.1": expected_continuation},
            expires_at="2099-01-01T00:00:00Z", actor="return-loop")
        request = created[0]["request"]
        plan_requests.claim(plan_dir, request["decision_id"], resolver_id="owner:p5.5",
                            lease_expires_at="2099-01-01T00:00:00Z")
        response = owner_response(request, "continue")
        original = plan_item_state.build_states
        calls = 0

        def fail_once(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("injected resolve projection failure")
            return original(*args, **kwargs)

        with mock.patch("task.plan_item_state.build_states", side_effect=fail_once):
            with_error = False
            try:
                plan_requests.resolve(plan_dir, request["decision_id"], response, resolver_id="owner:p5.5",
                                      current_continuation=expected_continuation)
            except plan_requests.RequestError as exc:
                require("projection failed" in str(exc), "resolve failure escaped projection seam")
                with_error = True
            require(with_error, "one-shot resolve failure did not fail")
        durable = [row for row in plan_requests._read_events(plan_dir) if row["type"] == "response"]
        require(len(durable) == 1 and "continuation" not in durable[0],
                "failed resolve leaked durable continuation")
        retried = plan_requests.resolve(plan_dir, request["decision_id"], response, resolver_id="owner:p5.5",
                                        current_continuation=expected_continuation)
        bad = copy.deepcopy(response)
        bad["reason_code"] = "P5_DECISION_REJECTED"
        try:
            plan_requests.resolve(plan_dir, request["decision_id"], bad, resolver_id="owner:p5.5",
                                  current_continuation=expected_continuation)
        except plan_requests.RequestError:
            pass
        else:
            fail("resolve retry accepted a different response under the same id")
        result = observations(plan_dir, subject_id="P1.1", decision_id=request["decision_id"],
                              continuation_mode=retried["continuation"]["mode"], retry_count=1)
        require(result["queue_event_counts"] == {"claim": 1, "request": 1, "response": 1},
                "resolve retry duplicated queue event")
        require(result["latest_journal_result"] == "in-progress", "resolve retry did not restore apply state")
        return {"id": "resolve-apply-projection-failure-retry", "observed_outcome": "apply",
                "verified_provenance": True, "reclassified_to": None, **result}
    finally:
        directory.cleanup()


def generate(fixture: Path) -> dict:
    require((fixture / "decisions" / "queue.jsonl").is_file(), "baseline queue fixture is absent")
    scenarios = [policy_scenario(fixture, authorization=False), policy_scenario(fixture, authorization=True),
                 terminal_auto_answer_single_use_scenario(fixture), authorization_owner_flow_scenario(fixture)]
    scenarios.extend(owner_scenario(fixture, option) for option in ("continue", "park", "reject"))
    scenarios.extend(option_bound_scenario(fixture, count) for count in (2, 5))
    scenarios.append(mandatory_only_scenario(fixture))
    scenarios.extend((request_retry_scenario(fixture), resolve_retry_scenario(fixture)))
    return {
        "artifact_version": "p5.5-acceptance-v4", "fixture": "packages/task/tests/data/plan-v2-p5",
        "frozen_input_digests": frozen_digests(), "scenario_ids": [scenario["id"] for scenario in scenarios],
        "scenarios": scenarios,
    }


def render_report(results: dict) -> bytes:
    rows = [
        "Synthetic Layout-v2 scenarios are proven; P6 command integration and live fleet behavior are not proven.",
        "", "# P5.5 producer-based acceptance report", "",
        "The committed fixture queue is regression input only. Every scenario starts from a fresh copy, removes that queue, and reaches its observations through runtime producers.",
        "", "| Scenario | Outcome | Queue events | Latest journal | Pending | Join | Retry | Continuation |",
        "|:--|:--|:--|:--|:--|:--|--:|:--|",
    ]
    for scenario in results["scenarios"]:
        counts = ", ".join(f"{kind}:{count}" for kind, count in scenario["queue_event_counts"].items()) or "—"
        pending = ", ".join(scenario["pending_decision_ids"]) or "—"
        rows.append("| {id} | {outcome} | {counts} | {journal} | {pending} | {join} | {retry} | {continuation} |".format(
            id=scenario["id"], outcome=scenario["observed_outcome"], counts=counts,
            journal=scenario["latest_journal_result"], pending=pending,
            join="blocks" if scenario["phase_join_blocks"] else "clear", retry=scenario["retry_count"],
            continuation=scenario["continuation_mode"]))
    rows.extend(("", "The report is rendered only from results JSON. Volatile timestamps and temporary paths are checked while running but are not emitted."))
    return ("\n".join(rows) + "\n").encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--results", required=True)
    parser.add_argument("--report", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    results = generate(Path(args.fixture))
    results_bytes, report_bytes = canonical_bytes(results), render_report(results)
    results_path, report_path = Path(args.results), Path(args.report)
    if args.write:
        results_path.write_bytes(results_bytes)
        report_path.write_bytes(report_bytes)
    else:
        require(results_path.is_file() and report_path.is_file(), "generated acceptance artifacts are absent")
        require(results_path.read_bytes() == results_bytes, "results are not byte-identical")
        require(report_path.read_bytes() == report_bytes, "report is not byte-identical")
    print("acceptance: twelve producer/error scenarios; deterministic results and report")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
