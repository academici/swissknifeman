"""Whole-plan closure and phase acceptance without a phase-close lifecycle."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from task import journal, plan_downstream, plan_gates, plan_item_state, plan_layout, plan_recovery, plan_status


class AcceptanceError(ValueError):
    def __init__(self, gate, subject):
        self.next_exact = gate.get("next_exact")
        super().__init__(f"{gate.get('code', 'PHASE_ACCEPTANCE_REQUIRED')}: {subject}")


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _validation(path: Path) -> str:
    text = path.read_text()
    match = re.search(r"^## (?:\d+\. )?Validation[^\n]*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    return match[1].strip() if match else ""


def validate_acceptance(plan_dir, subject: str, fingerprint: str) -> None:
    root = Path(plan_dir)
    contract = root / "plan.md" if subject == "plan" else plan_layout.phase_path(root, subject)
    validation = _validation(contract)
    if not validation or validation == "—":
        return
    target = root / "acceptance" / (subject + ".json")
    try:
        value = json.loads(target.read_text())
        if (not isinstance(value, dict) or value.get("schema_version") != "plan-acceptance/v1"
                or value.get("subject") != subject or value.get("plan_id") != root.name
                or value.get("candidate_sha256") != fingerprint
                or value.get("validation_sha256") != _sha(validation.encode())
                or not isinstance(value.get("checks"), list) or not value["checks"]):
            raise ValueError("missing/stale candidate or validation binding")
        for check in value["checks"]:
            if (not isinstance(check, dict) or check.get("status") != "green"
                    or not isinstance(check.get("requirement"), str) or not check["requirement"].strip()
                    or not isinstance(check.get("path"), str)):
                raise ValueError("RED/missing validation check")
            path = root / check["path"]
            if not path.resolve().is_relative_to(root.resolve()) or _sha(path.read_bytes()) != check.get("sha256"):
                raise ValueError("missing/changed evidence")
        # Every declared bullet is a distinct mandatory gate, including external
        # authority gates. A JSON assertion cannot silently omit one of them.
        requirements = [line.strip()[2:].strip() for line in validation.splitlines()
                        if line.strip().startswith(("- ", "* "))]
        if not requirements:
            requirements = [validation]
        if set(requirements) != {check["requirement"] for check in value["checks"]}:
            raise ValueError("validation coverage mismatch")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ValueError(f"PLAN_ACCEPTANCE_REQUIRED: {subject}: {exc}") from exc


def phase_acceptance(plan_dir, phase_id: str) -> dict:
    from task import terminal_policy
    for spec in plan_layout.item_spec_paths(plan_dir, phase_id):
        evidence = plan_item_state.material_terminal_evidence(plan_dir, spec.stem)
        terminal_policy.validate_predecessor(evidence.get("decision"), result=evidence["result"],
                                            plan_dir=Path(plan_dir), item_id=spec.stem)
    candidate = plan_gates.phase_candidate_fingerprint(plan_dir, phase_id)
    gate = plan_gates.phase_close_gate(plan_dir, phase_id,
        candidate_fingerprint=candidate["fingerprint"], candidate_snapshot=candidate["snapshot"])
    if not gate.get("allow"):
        raise AcceptanceError(gate, phase_id)
    statuses = [row["status"] for row in candidate["snapshot"]["terminal_item_heads"]]
    if plan_status.STATUS_BLOCKED in statuses and gate.get("phase_status") != plan_status.STATUS_DEVIATIONS:
        raise ValueError(f"PLAN_NOT_COMPLETE: {phase_id} contains unresolved blocked owning work")
    validate_acceptance(plan_dir, phase_id, candidate["fingerprint"])
    acceptance = Path(plan_dir) / "acceptance" / (phase_id + ".json")
    return {"phase_id": phase_id, "fingerprint": candidate["fingerprint"],
            "contract_sha256": _sha(plan_layout.phase_path(plan_dir, phase_id).read_bytes()),
            "acceptance_sha256": _sha(acceptance.read_bytes()) if acceptance.is_file() else None,
            "gate": gate}


def candidate(plan_dir) -> dict:
    root = Path(plan_dir)
    phases = plan_layout.phase_paths(root)
    if not phases:
        raise ValueError("PLAN_NOT_COMPLETE: no phases")
    declared = set(re.findall(r"^\|\s*(P\d+)\s*\|", (root / "plan.md").read_text(), re.M))
    if declared and declared != set(phases):
        raise ValueError("PLAN_NOT_COMPLETE: declared phase carriers are missing or inconsistent")
    rows = []
    for phase in sorted(phases, key=lambda value: int(value[1:])):
        rows.append(phase_acceptance(root, phase))
    proofs = [{key: row[key] for key in ("phase_id", "fingerprint", "contract_sha256", "acceptance_sha256")}
              for row in rows]
    digest = _sha(json.dumps({"phases": proofs,
                             "plan_sha256": _sha((root / "plan.md").read_bytes())}, sort_keys=True).encode())
    validate_acceptance(root, "plan", digest)
    acceptance = root / "acceptance/plan.json"
    # Persist only stable proof fields, not diagnostic policy metadata.
    return {"schema_version": "plan-completion/v1", "plan_id": root.name,
            "candidate_sha256": digest, "phases": proofs,
            "plan_acceptance_sha256": _sha(acceptance.read_bytes()) if acceptance.is_file() else None}


def successor(plan_dir) -> str:
    """Select actual remaining work; never compile phase assurance to phase close."""
    root = Path(plan_dir)
    items = plan_downstream._all_items(root)
    ranks = plan_recovery._execution_ranks(root, items)
    ready = plan_recovery.design_ready_items(root)
    states = {item: plan_item_state.state_model(root, item)[0]["state"]["position"]["status"]
              for item in items}
    for phase, path in sorted(plan_layout.phase_paths(root).items(), key=lambda row: int(row[0][1:])):
        for item in sorted((item for item in items if item.startswith(phase + ".")), key=ranks.__getitem__):
            if states[item] in {plan_status.STATUS_PROGRESS, plan_status.STATUS_NOT_STARTED} and item in ready:
                from task import task_contract
                try:
                    compiled = task_contract.compile_batch_routing(root)
                    owner = compiled["items"].get(item)
                    group = compiled["batches"][owner["batch_key"]] if owner else None
                    targets = (item,)
                    if group and group["batch_id"].lower() != "solo" and not group["recommended"]:
                        prefix = task_contract._derived_completed_prefix(root, group["items"])
                        targets = group["items"][len(prefix):]
                    return f"run-items: task:plan-run {root.name} " + " ".join(targets)
                except task_contract.TaskContractBuildError:
                    # Readable minimal legacy plans have no executable Batch table.
                    return f"run-items: task:plan-run {root.name} {item}"
        if not any(item.startswith(phase + ".") for item in items) or re.search(
                r"^>\s*SKELETON\s*[—-]\s*not detailed", path.read_text(), re.M):
            return f"design-phase: task:plan-design {root.name} {phase}"
    if any(status not in {plan_status.STATUS_DONE, plan_status.STATUS_DEVIATIONS, plan_status.STATUS_SKIPPED}
           for status in states.values()):
        item = next(item for item in sorted(items, key=ranks.__getitem__)
                    if states[item] not in {plan_status.STATUS_DONE, plan_status.STATUS_DEVIATIONS, plan_status.STATUS_SKIPPED})
        return f"waiting: resolve {item} owning work or external authority → run-items: task:plan-run {root.name} {item}"
    try:
        candidate(root)
    except AcceptanceError as exc:
        return exc.next_exact or "manual: implementation/high"
    except (OSError, ValueError):
        return "manual: implementation/high"
    return f"close: task:plan-close {root.name}"


def close(plan_dir, *, actor: str, session_id: str) -> dict:
    root = Path(plan_dir)
    if not session_id:
        raise ValueError("PLAN_CLOSE_SESSION_REQUIRED")
    # The journal lock serializes both candidate validation and terminal append.
    with journal._journal_lock(root):
        journal_rows, _exceptions = journal._authoritative_state_locked(root)
        rows = [row for _line, _raw, row in journal_rows]
        value = candidate(root)
        previous = [row for row in rows if row.get("command") == "plan-close" and row.get("item_id") == "plan"
                    and row.get("result") == "closed-green" and row.get("fingerprint") == value["candidate_sha256"]]
        if not previous:
            pending = [row for row in rows if row.get("item_id") == "plan" and row.get("result") == "in-progress"
                and row.get("session_id") == session_id and row.get("fingerprint") == value["candidate_sha256"]
                and not any(end.get("run_id") == row.get("run_id") and end.get("result") in journal.TERMINAL_CLOSE_RESULTS
                            for end in rows)]
            if len(pending) > 1:
                raise ValueError("PLAN_CLOSE_RUN_AMBIGUOUS: reconcile duplicate starts")
            if pending:
                start = pending[0]
                attempt, run_id = start["attempt"], start["run_id"]
            else:
                attempt = 1 + max((row.get("attempt", 1) for row in rows if row.get("item_id") == "plan"), default=0)
                run_id = journal.derive_run_id(plan_id=root.name, item_id="plan", attempt=attempt, session_id=session_id)
                start = journal.new_entry(plan_id=root.name, item_id="plan", command="plan-close", actor=actor,
                    result="in-progress", session_id=session_id, run_id=run_id, attempt=attempt,
                    fingerprint=value["candidate_sha256"], note="Whole plan acceptance verified; persisting closure.")
                journal.validate_entry(start)
                journal._append_locked(root, start, journal_rows)
                journal_rows.append((len(journal_rows) + 1, "", start))
            event = journal.new_entry(plan_id=root.name, item_id="plan", command="plan-close", actor=actor,
                result="closed-green", session_id=session_id, run_id=run_id, attempt=attempt,
                fingerprint=value["candidate_sha256"], note="Whole plan acceptance verified.",
                decision={"signal_class": "acceptance", "scope_class": "plan", "action": "close-green",
                          "recovered": True, "terminal": True})
            journal.validate_entry(event)
            journal._append_locked(root, event, journal_rows, enforce_terminal_order=True)
        target = root / "closure" / "plan.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        expected = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
        if not target.exists() or target.read_text() != expected:
            target.write_text(expected)
    plan_status.build_status(root)
    from task import plan_reconcile, plan_delivery
    plan_reconcile.write_handoff(root, "plan", "terminal: plan closed")
    receipt = plan_delivery.build_terminal_receipt(root, "plan")
    plan_delivery.write_receipt(root / ".plan-cache/plan-terminal-delivery-receipt.json", receipt)
    return {**value, "closure_path": str(target), "next_exact": "terminal: plan closed", "receipt": receipt}
