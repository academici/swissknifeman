"""Small command facade over the existing Task state and admission owners.

Snapshots, compiled contracts and generated views stay inside the tool. The model
receives the selected authoring context and a compact result, not transport chunks.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import re
import sys
from pathlib import Path

from task import (journal, plan_admission, plan_bundle, plan_decisions,
                  plan_delivery, plan_evidence, plan_item_state, plan_layout,
                  plan_lint, plan_projection, plan_readiness, plan_reconcile,
                  plan_recovery, plan_status, plan_weight,
                  session_context, task_contract, validation_admission)


class WorkError(ValueError):
    def __init__(self, code: str, detail):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def _phase(root: Path, phase_id: str) -> dict:
    if not re.fullmatch(r"P\d+", phase_id):
        raise WorkError("PLAN_WORK_INVALID_TARGET", "phase должна иметь форму Pn")
    diagnostics = plan_lint.Diagnostics()
    value = plan_lint.parse_phase_md(plan_layout.phase_path(root, phase_id),
                                     phase_id, diagnostics, layout="v2")
    if diagnostics.errors or value is None:
        raise WorkError("PLAN_WORK_SCHEMA_INVALID", diagnostics.errors)
    return value


def _foreign_baseline(key, phase_id: str) -> bool:
    """Only unrelated phase diagnostics can be carried as historical debt."""
    _kind, path, message = key
    return (path.startswith("phases/")
            and not path.startswith(f"phases/{phase_id}/")
            and not re.search(r"authority|routing|полномочи", message, re.IGNORECASE)
            and not re.search(rf"\b{re.escape(phase_id)}(?:\.|\b)", message))


def prepare(plan_dir, item_id: str, *, command: str, actor: str,
            session_id: str | None = None, actual_route: dict | None = None,
            capabilities=(), request=None, batch_receipt=None) -> dict:
    """Admit and durably start one item, exposing only its selected context."""
    from task import route_evidence

    root = Path(plan_dir)
    if command not in {"plan-exec", "plan-run"}:
        raise WorkError("PLAN_WORK_INVALID_COMMAND", command)
    session_id = session_id or session_context.current_id()
    plan_readiness.validate_execution_target(root, (item_id,))
    plan_recovery.validate_request(root, item_id)
    admission = plan_admission.batch_admission(
        root, request or [item_id], receipt=batch_receipt)
    if admission["verdict"] != "ALLOW":
        raise WorkError(admission["verdict"], admission)
    if item_id not in admission["requested"]:
        raise WorkError("BATCH_AMBIGUOUS", "item отсутствует в запросе")
    invocation = f"task:{command} {root.name} " + " ".join(admission["requested"])
    if actual_route is None:
        actual_route = route_evidence.capture_launch(
            expected_invocation=invocation,
            expected_cwd=plan_weight.repo_root_for(root))
    contract = task_contract.build(root, item_id, actual_route=actual_route,
                                   capabilities=capabilities, carrier=invocation)
    bundle_model = plan_bundle.model(root, item_id)
    producer_readiness = plan_bundle.producer_readiness(root, item_id)
    graph = plan_evidence.compile_graph(
        root, item_id, bundle=bundle_model, readiness=producer_readiness)
    validation = validation_admission.inspect(root, item_id)
    bundle_rendered = plan_bundle.canonical_json(bundle_model)
    try:
        started = plan_recovery.start(
            root, item_id, command=command, actor=actor, session_id=session_id,
            contract=contract, batch_receipt=admission.get("batch_receipt", batch_receipt),
            route_evidence=actual_route, evidence_graph=graph,
            bundle_rendered=bundle_rendered, producer_readiness=producer_readiness,
            return_context=True)
    except plan_recovery.RecoveryError as exc:
        if exc.code in {"ROUTE_UNDERSHOOT", "ROUTE_UNVERIFIABLE", "AUTHORITY_BOUNDARY",
                        "ECONOMY_ROUTE_OVERSHOOT", "CAPABILITY_UNSUPPORTED"}:
            raise WorkError(exc.code, exc.verdict) from exc
        raise
    position, snapshot = started["position"], started["snapshot"]
    selected = {member.role: member for member in snapshot.members}
    result = {
        "plan_id": root.name, "item_id": item_id, "position": position,
        "context": {"item-spec": selected["item-spec"].content.decode("utf-8")},
        "phase": {"id": item_id.split(".")[0],
                  "path": selected["phase-context"].path.relative_to(root).as_posix()},
        "snapshot": snapshot.receipt(),
        "route": contract["route"], "authority": contract["authority"],
        "validation": validation,
        "batch_receipt": admission.get("batch_receipt", batch_receipt),
    }
    snapshot.assert_live_integrity()
    return result


def design_context(plan_dir, phase_id: str, *, actual_route=None,
                   owner_accepts_overshoot: bool = False) -> dict:
    """Expose canonical field names and current selected phase/routing only."""
    root = Path(plan_dir)
    if actual_route is not None:
        effort = actual_route.get("effort")
        if actual_route.get("model_class") != "frontier" or effort not in {"high", "xhigh"}:
            raise WorkError("ROUTE_UNDERSHOOT", "design требует frontier/high")
        if effort == "xhigh" and not owner_accepts_overshoot:
            raise WorkError("ECONOMY_ROUTE_OVERSHOOT", "design использует frontier/high; более дорогой маршрут требует выбора владельца")
    plan_readiness.validate_design_target(root, phase_id)
    phase = _phase(root, phase_id)
    routing = task_contract.compile_batch_routing(root)
    diagnostics = plan_lint.Diagnostics()
    plan_lint.lint_plan(root, diagnostics)
    baseline = [key for key in diagnostics.normalized_keys(root)
                if key[0] == "ERROR" and _foreign_baseline(key, phase_id)]
    plan_projection.write_or_check(
        root / ".plan-cache" / f"design-{phase_id}-baseline.json",
        json.dumps(baseline, ensure_ascii=False) + "\n", check=False)
    return {
        "plan_id": root.name, "phase_id": phase_id,
        "schema": {"layout": "v2", "item_fields": list(plan_lint.ITEM_SPEC_FIELDS),
                   "handoff_fields": list(plan_lint.HANDOFF_REQUIRED_FIELDS),
                   "reference": "runtime/plan-protocol/references/plan-layout-v2.md"},
        "phase": plan_layout.phase_path(root, phase_id).read_text(encoding="utf-8"),
        "items": {item: {field: value[0] for field, value in rows[0]["fields"].items()
                          if field in plan_lint.ITEM_SPEC_FIELDS}
                  for item, rows in phase["items"].items()},
        "routing": {item: value for item, value in routing["items"].items()
                    if item.split(".")[0] == phase_id},
        "handoff": (root / "handoff.md").read_text(encoding="utf-8"),
        "baseline_errors": diagnostics.errors,
    }


def finalize_design(plan_dir, phase_id: str, *, actor: str,
                    session_id: str | None = None) -> dict:
    """Converge authored design through existing writers; never execute Next."""
    root = Path(plan_dir)
    plan_readiness.validate_design_target(root, phase_id)
    session_id = session_id or session_context.current_id()
    for path in plan_layout.item_spec_paths(root, phase_id):
        plan_item_state.build_states(root, item_id=path.stem, materialize_successor=False)
    _phase(root, phase_id)
    task_contract.compile_batch_routing(root)
    plan_decisions.build_views(root)
    plan_status.build_status(root)
    ready = []
    specs = list(plan_layout.item_spec_paths(root, phase_id))
    # Also materialize the explicitly selected successor, even across a phase.
    handoff = (root / "handoff.md").read_text(encoding="utf-8")
    match = re.search(r"^\*\*Next:\*\*\s*(?:(?:exec|run)-items:\s*)?/?task:plan-(?:exec|run)\s+\S+\s+(P\d+\.\d+)",
                      handoff, re.MULTILINE)
    if match and match[1] not in {path.stem for path in specs}:
        specs.append(plan_layout.carrier_path(root, "item-spec", item_id=match[1]))
    for path in specs:
        item = path.stem
        if plan_recovery.inspect(root, item)["allowed"]:
            plan_bundle.build(root, item)
            ready.append(item)
    diagnostics = plan_lint.Diagnostics()
    plan_lint.lint_plan(root, diagnostics)
    baseline_path = root / ".plan-cache" / f"design-{phase_id}-baseline.json"
    current = Counter(key for key in diagnostics.normalized_keys(root) if key[0] == "ERROR")
    baseline = Counter(tuple(key) for key in json.loads(baseline_path.read_text())
                       if _foreign_baseline(key, phase_id)) \
        if baseline_path.is_file() else Counter()
    new_errors = list((current - baseline).elements())
    if new_errors:
        raise WorkError("PLAN_WORK_SCHEMA_INVALID", new_errors)
    # Verify authored semantic Next/continuity before reporting completion or
    # recording the design event. Receipt regeneration below binds final views.
    plan_delivery.build_handoff_receipt(root, phase_id)
    sources = [plan_layout.plan_core_path(root), plan_layout.phase_path(root, phase_id),
               root / "handoff.md", *plan_layout.item_spec_paths(root, phase_id)]
    fingerprint = plan_projection.inputs_sha256(sources, root=root)
    existing = [json.loads(line) for line in (root / journal.FILENAME).read_text(
        encoding="utf-8").splitlines() if line.strip()]
    if not any(row.get("command") == "plan-design" and row.get("item_id") == phase_id
               and row.get("fingerprint") == fingerprint for row in existing):
        journal.append(root, journal.new_entry(
            plan_id=root.name, item_id=phase_id, command="plan-design", actor=actor,
            result="no-op", session_id=session_id, fingerprint=fingerprint,
            note="Design finalized; execution has not started."))
    # The phase-level design event changes the global status journal input. Item
    # states are scoped to their own Pn.m rows and bundles contain no journal
    # input, so rebuilding them here only repeats identical work.
    plan_status.build_status(root)
    receipt = plan_delivery.build_handoff_receipt(root, phase_id)
    target = root / ".plan-cache" / "design-receipt.json"
    plan_delivery.write_receipt(target, receipt)
    return {"plan_id": root.name, "phase_id": phase_id, "ready_items": ready,
            "receipt": receipt, "receipt_path": str(target),
            "warnings": diagnostics.warnings, "baseline_errors": diagnostics.errors}


def finalize(plan_dir, item_id: str) -> dict:
    """Existing terminal evidence remains mandatory; this never invents GREEN."""
    return plan_reconcile.reconcile_terminal(plan_dir, item_id)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Компактный Task work context и завершение")
    actions = parser.add_subparsers(dest="action", required=True)
    for name in ("prepare", "design-context", "finalize-design", "finalize"):
        action = actions.add_parser(name)
        action.add_argument("--plan-dir", type=Path, required=True)
        action.add_argument("--phase" if "design" in name else "--item", required=True)
        if name in {"prepare", "finalize-design"}:
            action.add_argument("--actor", required=True)
            action.add_argument("--session-id")
        if name == "design-context":
            action.add_argument("--owner-accepts-overshoot", action="store_true",
                                help="только при явном выборе более дорогого маршрута владельцем")
        if name == "prepare":
            action.add_argument("--command", choices=("plan-exec", "plan-run"), required=True)
            action.add_argument("--actual-route", type=Path)
            action.add_argument("--request", nargs="+")
            action.add_argument("--batch-receipt", type=Path)
            action.add_argument("--capability", action="append", default=[],
                                help="JSON capability binding: id и support")
    args = parser.parse_args(argv)
    try:
        if args.action == "prepare":
            result = prepare(args.plan_dir, args.item, command=args.command, actor=args.actor,
                             session_id=args.session_id, request=args.request,
                             capabilities=[json.loads(value) for value in args.capability],
                             actual_route=json.loads(args.actual_route.read_text()) if args.actual_route else None,
                             batch_receipt=json.loads(args.batch_receipt.read_text()) if args.batch_receipt else None)
        elif args.action == "design-context":
            from task import route_evidence

            actual = route_evidence.capture_launch(
                expected_invocation=f"task:plan-design {args.plan_dir.name} {args.phase}",
                expected_cwd=plan_weight.repo_root_for(args.plan_dir))
            result = design_context(args.plan_dir, args.phase, actual_route=actual,
                                    owner_accepts_overshoot=args.owner_accepts_overshoot)
        elif args.action == "finalize-design":
            result = finalize_design(args.plan_dir, args.phase, actor=args.actor,
                                     session_id=args.session_id)
        else:
            result = finalize(args.plan_dir, args.item)
    except (OSError, ValueError) as exc:
        print(json.dumps({"error": getattr(exc, "code", "PLAN_WORK_FAILED"),
                          "detail": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0
