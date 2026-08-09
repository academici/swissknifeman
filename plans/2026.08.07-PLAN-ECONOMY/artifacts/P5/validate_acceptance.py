#!/usr/bin/env python3
"""Produce and verify the P5.5 decision-queue acceptance evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]

import sys
sys.path.insert(0, str(ROOT / "packages/task/lib"))

from task import plan_authority, plan_item_state, plan_requests, plan_returns, plan_status  # noqa: E402


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
    # The committed queue is a regression input only.  Producer scenarios start
    # with a new queue in their own copy and cannot obtain a green result by
    # replaying these pre-built records.
    queue = plan_dir / "decisions" / "queue.jsonl"
    if queue.exists():
        queue.unlink()
    return directory, plan_dir


def continuation(item_id: str) -> dict:
    return {
        "root_session_id": "p5.5-fixture-session",
        "root_run_id": "p5.5-fixture-run",
        "target": {
            "plan_id": "plan-v2-p5",
            "item_id": item_id,
            "resume_command": f"task:plan-run plan-v2-p5 {item_id}",
        },
        "capabilities": {
            "snapshot_id": "p5.5-fixture-capabilities",
            "digest": "a" * 64,
            "available": ["filesystem"],
        },
        "preferred_mode": "resume-root",
    }


def clarification_request() -> dict:
    return {
        "decision_id": "p5.5-policy-clarification",
        "action_version": 1,
        "kind": "clarification",
        "decision_class": "constructive",
        "subject": {"plan_id": "plan-v2-p5", "phase_id": "P1", "item_id": "P1.2"},
        "action": {
            "type": "resolve-plan-carrier",
            "requires_authorization": False,
            "affected_surfaces": ["plan-carrier"],
            "declared_scope": ["plan-carrier"],
            "frozen_contract_change": False,
            "closed_set_extension": False,
            "reversible": True,
            "decision_recorded": True,
        },
        "options": [
            {"id": "apply", "outcome": "apply", "action_ref": "plan.md", "evidence_refs": ["plan.md"]},
            {"id": "park", "outcome": "park", "action_ref": None, "evidence_refs": []},
            {"id": "escalate", "outcome": "escalate", "action_ref": None, "evidence_refs": []},
            {"id": "reject", "outcome": "reject", "action_ref": None, "evidence_refs": []},
        ],
        "default_option": None,
        "on_timeout": "park",
        "expires_at": "2099-01-01T00:00:00Z",
        "evidence": [],
        "attempted": [],
        "continuation": continuation("P1.2"),
    }


def owner_response(request: dict, option: str) -> dict:
    return {
        "decision_id": request["decision_id"],
        "action_version": request["action_version"],
        "selected_option": option,
        "resolver": "owner",
        "resolver_id": "owner:p5.5",
        "policy_digest": request["policy_digest"],
        "action_digest": request["action_digest"],
        "reason_code": "P5_DECISION_OWNER_APPROVED",
        "provenance": {
            "source_system": "git",
            "record_id": "p5.5-owner-decision",
            "record_version": "1",
            "verified": True,
        },
        "at": "2099-01-01T00:00:00Z",
    }


def verify_views(plan_dir: Path, item_id: str) -> None:
    plan_item_state.build_states(plan_dir, item_id=item_id, check=True)
    plan_status.build_status(plan_dir, check=True)


def policy_scenario(fixture: Path) -> dict:
    directory, plan_dir = fresh_plan(fixture)
    try:
        raw = clarification_request()
        requested = plan_requests.request(plan_dir, raw, actor="policy")
        producer_input = {**raw, "missing_fields": ["carrier"]}
        produced = plan_authority.auto_answer_clarification(
            producer_input,
            question_class="plan_carrier",
            field="carrier",
            sources={"plan_carrier": {
                "value": "plan.md",
                "record_id": "plan.md",
                "record_version": "fixture-v1",
                "at": "2099-01-01T00:00:00Z",
            }},
        )
        require(isinstance(produced, dict), "policy producer did not return a contract pair")
        event = plan_requests.append_auto_answer(
            plan_dir, produced["event"], response=produced["response"], actor="policy")
        state = plan_requests.states(plan_dir)[raw["decision_id"]]
        require(state["auto_answer"] is not None, "policy auto-answer was not persisted")
        require(event["response"]["resolver"] == "policy", "policy resolver was not persisted")
        require(event["response"]["provenance"]["verified"] is True, "policy provenance is unverified")
        require(event["event"]["before_digest"] == requested["request"]["action_digest"],
                "policy before digest is not linked")
        require(event["event"]["before_digest"] != event["event"]["after_digest"],
                "policy reclassification did not change digest")
        require(event["event"]["reclassified_to"] == "clarification", "policy scenario changed authority class")
        require(plan_requests.unresolved_for_phase(plan_dir, "P1") == [], "resolved policy request remains unresolved")
        require(subject_status(plan_dir, "P1.2") == "🟡 In progress", "policy apply did not resume subject")
        require(subject_status(plan_dir, "P1.1") == "🔴 Blocked", "policy changed unrelated subject")
        verify_views(plan_dir, "P1.2")
        events = plan_requests._read_events(plan_dir)
        return {
            "id": "policy-auto-answer",
            "observed_outcome": "apply",
            "queue_event_count": len(events),
            "queue_event_types": [entry["type"] for entry in events],
            "journal_count": len((plan_dir / "journal.jsonl").read_text(encoding="utf-8").splitlines()),
            "subject_statuses": {"P1.1": subject_status(plan_dir, "P1.1"), "P1.2": subject_status(plan_dir, "P1.2")},
            "continuation_mode": "none",
            "verified_provenance": True,
            "reclassified_to": event["event"]["reclassified_to"],
        }
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
        verify_views(plan_dir, "P1.1")
        events = plan_requests._read_events(plan_dir)
        return {
            "id": f"owner-{option}",
            "observed_outcome": "apply" if option == "continue" else option,
            "queue_event_count": len(events),
            "queue_event_types": [entry["type"] for entry in events],
            "journal_count": len((plan_dir / "journal.jsonl").read_text(encoding="utf-8").splitlines()),
            "subject_statuses": {"P1.1": subject_status(plan_dir, "P1.1"), "P1.2": subject_status(plan_dir, "P1.2")},
            "continuation_mode": mode,
            "verified_provenance": True,
            "reclassified_to": None,
        }
    finally:
        directory.cleanup()


def generate(fixture: Path) -> dict:
    require((fixture / "decisions" / "queue.jsonl").is_file(), "baseline queue fixture is absent")
    scenarios = [policy_scenario(fixture)]
    scenarios.extend(owner_scenario(fixture, option) for option in ("continue", "park", "reject"))
    return {
        "artifact_version": "p5.5-acceptance-v2",
        "fixture": "packages/task/tests/data/plan-v2-p5",
        "frozen_input_digests": frozen_digests(),
        "scenario_ids": [scenario["id"] for scenario in scenarios],
        "scenarios": scenarios,
    }


def render_report(results: dict) -> bytes:
    rows = [
        "# P5.5 producer-based acceptance report",
        "",
        "Synthetic Layout-v2 scenarios are proven; P6 command integration and live fleet behavior are not proven.",
        "",
        "The committed fixture queue is retained only as regression input. Each scenario below starts from a fresh copy, removes that pre-built queue, and creates its evidence through the runtime producer APIs.",
        "",
        "| Scenario | Outcome | Queue events | Journal rows | P1.1 | P1.2 | Continuation |",
        "|:--|:--|--:|--:|:--|:--|:--|",
    ]
    for scenario in results["scenarios"]:
        statuses = scenario["subject_statuses"]
        rows.append("| {id} | {outcome} | {queue} | {journal} | {p11} | {p12} | {continuation} |".format(
            id=scenario["id"], outcome=scenario["observed_outcome"], queue=scenario["queue_event_count"],
            journal=scenario["journal_count"], p11=statuses["P1.1"], p12=statuses["P1.2"],
            continuation=scenario["continuation_mode"]))
    rows.extend(("", "All scenario claims derive from the generated results JSON; volatile timestamps and temporary paths are checked during execution but are not emitted."))
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
    results_bytes = canonical_bytes(results)
    report_bytes = render_report(results)
    results_path, report_path = Path(args.results), Path(args.report)
    if args.write:
        results_path.write_bytes(results_bytes)
        report_path.write_bytes(report_bytes)
    else:
        require(results_path.is_file() and report_path.is_file(), "generated acceptance artifacts are absent")
        require(results_path.read_bytes() == results_bytes, "results are not byte-identical")
        require(report_path.read_bytes() == report_bytes, "report is not byte-identical")
    print("acceptance: four producer scenarios; deterministic results and report")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
