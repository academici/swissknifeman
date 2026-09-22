"""Durable execution position and interrupted-predecessor recovery."""
from __future__ import annotations

import fcntl
import json
import os
import re
from pathlib import Path

from task import (journal, plan_admission, plan_bundle, plan_downstream,
                  plan_item_state, plan_layout, plan_readiness, plan_weight)


_ITEM = re.compile(r"^P\d+\.\d+$")
_NEXT = re.compile(r"task:plan-(?:exec|run)\s+\S+\s+(P\d+\.\d+)")
_READY_RESULTS = frozenset(("closed-green", "closed-deviations"))


class RecoveryError(ValueError):
    """A request cannot bypass its unfinished producer."""

    def __init__(self, verdict: dict):
        self.verdict = verdict
        self.code = verdict["code"]
        self.active_item = verdict.get("active_item")
        self.mode = verdict.get("mode")
        super().__init__(f"{self.code}: {verdict['reason']}")


def _key(item_id: str) -> tuple[int, int]:
    return tuple(int(part) for part in item_id[1:].split("."))


def _positions(plan_dir: Path) -> dict[str, dict]:
    events = {}
    try:
        rows = (plan_dir / journal.FILENAME).read_text(encoding="utf-8").splitlines()
        for raw in rows:
            if not raw.strip():
                continue
            event = json.loads(raw)
            if not isinstance(event, dict):
                raise ValueError("journal row должен быть object")
            item_id = event.get("item_id", "")
            if isinstance(item_id, str) and _ITEM.fullmatch(item_id):
                events.setdefault(item_id, []).append(event)
    except (OSError, ValueError) as exc:
        raise RecoveryError({"code": "RECOVERY_POSITION_UNAVAILABLE", "reason": str(exc)}) from exc
    return {item_id: position for item_id, history in events.items()
            if (position := plan_item_state.latest_execution_event(history)) is not None}


def _dependencies(plan_dir: Path, item_id: str, items: dict[str, dict]) -> set[str]:
    """Reuse declared producer/path ownership; Next alone never grants exclusivity."""
    fields = items[item_id]
    producers = set()
    for field in ("Inputs", "Required Reads"):
        for entry in plan_weight.split_entries(fields.get(field, "")):
            producer = plan_admission.producer_annotation(entry)
            if producer:
                producers.add(producer)
    repo_root = plan_weight.repo_root_for(plan_dir)
    inputs = set()
    for field in ("Inputs", "Required Reads"):
        inputs.update(plan_downstream._field_paths(
            fields.get(field, ""), plan_dir=plan_dir, repo_root=repo_root))
    for producer, spec in items.items():
        if _key(producer) >= _key(item_id):
            continue
        declared = plan_readiness.directive(spec.get("Deliverables", ""))
        if declared and declared["consumer_item"] == item_id:
            producers.add(producer)
        outputs = set()
        for field in ("Files", "Deliverables"):
            outputs.update(plan_downstream._field_paths(
                spec.get(field, ""), plan_dir=plan_dir, repo_root=repo_root))
        if inputs & outputs:
            producers.add(producer)
        state_path = plan_layout.carrier_path(plan_dir, "item-state", item_id=producer)
        relative_state = state_path.resolve().relative_to(repo_root.resolve()).as_posix()
        if relative_state in inputs:
            producers.add(producer)
        phase = producer.split(".")[0]
        closure_path = plan_dir / "phases" / phase / f"{phase}.closed.md"
        if closure_path.resolve().relative_to(repo_root.resolve()).as_posix() in inputs:
            producers.add(producer)
    return producers


def inspect(plan_dir, item_id: str) -> dict:
    """Diagnose execution order before attempting the five-carrier snapshot."""
    root = Path(plan_dir)
    if not _ITEM.fullmatch(item_id):
        raise ValueError("item должен иметь форму Pn.m")
    items = plan_downstream._all_items(root)
    positions = _positions(root)
    current = positions.get(item_id, {})
    verdict = {"schema_version": "plan-recovery/v1", "allowed": True,
               "code": "RESUME_ITEM" if current.get("result") == "in-progress" else "START_ITEM",
               "requested_item": item_id, "active_item": item_id,
               "mode": "resume" if current.get("result") == "in-progress" else "start",
               "run_id": current.get("run_id"), "attempt": current.get("attempt", 1),
               "reason": f"{item_id}: продолжить durable execution" if current.get("result") == "in-progress"
               else f"{item_id}: закрепить старт до первой product write"}
    if item_id not in items:
        return verdict  # Missing item carriers stay owned by the snapshot gate.
    pending = sorted((producer for producer in _dependencies(root, item_id, items)
                      if positions.get(producer, {}).get("result") not in _READY_RESULTS), key=_key)
    if not pending:
        return verdict
    # Prefer a durable active producer, then the semantic Next among actual
    # dependencies, then dependency order. An independent ready subset is legal.
    active = next((producer for producer in pending
                   if positions.get(producer, {}).get("result") == "in-progress"), None)
    if active is None:
        handoff = root / "handoff.md"
        matches = _NEXT.findall(handoff.read_text(encoding="utf-8")) if handoff.is_file() else []
        active = next((producer for producer in matches if producer in pending), pending[0])
    position = positions.get(active, {})
    mode = "resume" if position.get("result") == "in-progress" else "start"
    verdict.update(allowed=False, code="OUT_OF_ORDER_REQUEST", active_item=active,
                   mode=mode, run_id=position.get("run_id"), attempt=position.get("attempt", 1),
                   reason=f"{item_id} зависит от незавершённого {active}; {mode} {active} "
                          "в текущем invocation, затем продолжить successor после terminal event")
    return verdict


def validate_request(plan_dir, item_id: str) -> dict:
    verdict = inspect(plan_dir, item_id)
    if not verdict["allowed"]:
        raise RecoveryError(verdict)
    return verdict


def prepare(plan_dir, item_id: str) -> dict:
    """Converge deterministic selected-item carriers before taking the snapshot."""
    from task import plan_context

    root = Path(plan_dir)
    verdict = validate_request(root, item_id)
    try:
        plan_item_state.build_states(root, item_id=item_id)
        bundle = plan_bundle.build(root, item_id)
        readiness = plan_bundle.producer_readiness(root, item_id)
        snapshot = plan_context.capture(root, item_id)
        plan_item_state.build_states(root, item_id=item_id, check=True)
        plan_bundle.build(root, item_id, check=True)
        snapshot.assert_live_integrity()
    except plan_bundle.BundleError as exc:
        command = (f"python3 packages/task/scripts/plan-views.py bundle --plan-dir "
                   f"{root} --item {item_id} --stdout")
        raise RecoveryError({
            "code": "PLAN_BUNDLE_UNRESOLVABLE", "reason": str(exc),
            "requested_item": item_id, "active_item": item_id,
            "mode": verdict["mode"], "entry": str(exc).removeprefix("unresolvable_entry: "),
            "recovery_command": command,
        }) from exc
    return {"recovery": verdict, "bundle": bundle, "producer_readiness": readiness,
            "snapshot": snapshot}


def start(plan_dir, item_id: str, *, command: str, actor: str, session_id: str,
          contract: dict, batch_receipt=None, route_evidence=None) -> dict:
    """Admit one durable start; a restarted session reuses the open run identity."""
    from task import plan_context, task_contract

    code = task_contract.pre_mutation(contract)
    if code:
        raise RecoveryError({"code": code, "reason": "pre-mutation admission запрещает старт"})
    root = Path(plan_dir)
    identity = contract.get("cold_start", {})
    if (identity.get("plan_id"), identity.get("item_id")) != (root.name, item_id):
        raise RecoveryError({"code": "RECOVERY_CONTRACT_IDENTITY_MISMATCH",
                             "reason": "pre-mutation contract принадлежит другому plan/item"})
    # A process lock covers position inspection, durable append, and the state
    # projection. Interrupted processes release it automatically.
    lock_path = root / ".plan-cache" / "execution-start.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        from task import plan_lint, plan_layout
        phase_id = item_id.split(".")[0]
        phase_path = plan_layout.phase_path(root, phase_id)
        phase = plan_lint.parse_phase_md(phase_path, phase_id, plan_lint.Diagnostics(),
                                         layout=plan_layout.layout_version(root))
        occurrences = phase["items"].get(item_id, []) if phase else []
        if len(occurrences) != 1:
            raise RecoveryError({"code": "RECOVERY_CONTRACT_IDENTITY_MISMATCH", "reason": "live item неоднозначен"})
        fields = occurrences[0]["fields"]
        request = task_contract.declared_authority(item_id, fields, for_execution=True)
        rules = fields.get("Implementation Rules", "")
        rules = rules[0] if isinstance(rules, tuple) else rules
        authority = task_contract._resolve_authority(plan_lint, [], root, item_id,
                                                     phase_path, rules, None, request)
        if not authority[1] or (contract.get("authority", {}).get("class") == "owner-gate" and
                                (authority[0] != "owner-gate" or contract["authority"].get("granted_by") != authority[2])):
            raise RecoveryError({"code": "AUTHORITY_BOUNDARY", "reason": "live declared gate/grant изменён или отозван"})
        verdict = validate_request(root, item_id)
        if verdict["mode"] == "resume":
            if not verdict["run_id"]:
                raise RecoveryError({"code": "RECOVERY_RUN_ID_UNAVAILABLE",
                                     "reason": f"{item_id}: durable start не содержит run_id"})
            prepare(root, item_id)
            return verdict
        prepared = prepare(root, item_id)
        snapshot = prepared["snapshot"]
        positions = _positions(root)
        attempt = int(positions.get(item_id, {}).get("attempt", 0)) + 1
        run_id = journal.derive_run_id(plan_id=root.name, item_id=item_id,
                                       attempt=attempt, session_id=session_id)
        decision = None
        if route_evidence is not None:
            from task import route_evidence as route_owner
            receipt = route_owner.build_run_receipt(
                plan_id=root.name, item_id=item_id, attempt=attempt,
                session_id=session_id, run_id=run_id, evidence=route_evidence)
            decision = route_owner.start_decision(receipt)
        event = journal.new_entry(plan_id=root.name, item_id=item_id, command=command,
                                  actor=actor, result="in-progress", session_id=session_id,
                                  run_id=run_id, attempt=attempt, batch_receipt=batch_receipt,
                                  decision=decision)
        path = journal.append(root, event)
        with path.open("a") as stream:
            os.fsync(stream.fileno())
        plan_item_state.build_states(root, item_id=item_id)
        verdict.update(run_id=run_id, attempt=attempt)
        return verdict


def materialize_next_ready(plan_dir, terminal_item: str) -> Path | None:
    """Generate exactly one ready successor after its producer terminal event."""
    root = Path(plan_dir)
    positions = _positions(root)
    if positions.get(terminal_item, {}).get("result") not in _READY_RESULTS:
        return None
    items = plan_downstream._all_items(root)
    for item_id in sorted(items, key=_key):
        if _key(item_id) <= _key(terminal_item):
            continue
        if positions.get(item_id, {}).get("result") in _READY_RESULTS:
            continue
        dependencies = _dependencies(root, item_id, items)
        if any(positions.get(producer, {}).get("result") not in _READY_RESULTS
               for producer in dependencies):
            continue
        # Unresolved current inputs remain fail-closed; future bundles are never
        # manufactured by ignoring a missing producer carrier.
        plan_bundle.producer_readiness(root, item_id)
        try:
            return plan_bundle.build(root, item_id)
        except plan_bundle.BundleError as exc:
            if str(exc).startswith("unresolvable_entry:"):
                return None  # e.g. phase closure is generated after item state.
            raise
    return None
