"""Hard admission gates for executable-plan layout v2.

The gate deliberately delegates all measurement and timing decisions: ``plan_weight``
owns the mandatory-read graph and its one weight, while ``plan_admission`` owns the
``historical``/``pending``/``ready`` state machine.  This module only turns a failed
ready D2 result into actionable plan-lint diagnostics.
"""
from __future__ import annotations

import json
from pathlib import Path

from task import (plan_bundle, plan_decisions, plan_item_state, plan_layout,
                  plan_projection, plan_status, plan_weight)


GATE_ID = "read-budget-v1"
BUNDLE_GATE_ID = "bundle-v1"


def _calibration_label(measurer) -> str:
    artifact = measurer.artifact
    target = artifact["calibration_target"]
    return (f"token-estimate-calibration v{artifact['version']} "
            f"({target['provider']}/{target['requested_model_id']})")


def _error(diag, path, message: str) -> None:
    diag.error(Path(path), None, f"{GATE_ID}: {message}")


def _bundle_error(diag, path, message: str) -> None:
    diag.error(Path(path), None, f"{BUNDLE_GATE_ID}: {message}")


def lint_read_budget(plan_dir, layout: str, diag) -> None:
    """Emit D2 errors for ready layout-v2 items only.

    Layout v1 is structurally outside the frozen contract.  In layout v2 a missing
    calibration, read-limit artifact, or plan-owned contract is an error rather than
    an implicit skip.  ``measure_plan`` attaches the canonical admission result to
    each item, so this function never re-counts files or parses producer annotations.
    """
    if layout != "v2":
        return

    plan_dir = Path(plan_dir)
    try:
        measurer = plan_weight.Measurer()
        measured = plan_weight.measure_plan(plan_dir, measurer)
    except plan_weight.PlanWeightError as exc:
        _error(diag, plan_dir / "plan.md", f"не удалось загрузить вход гейта: {exc}")
        return

    admission = measured["totals"].get("admission") or {}
    contract = admission.get("contract")
    if contract is None:
        _error(diag, plan_dir / "root" / "contracts" / "read-budget-v1.md",
               "контракт порога отсутствует или невалиден; D2 не может быть применён")
        return

    threshold = contract["item_tokens"]
    calibration = _calibration_label(measurer)
    limits = measurer.limits
    for item in measured["items"]:
        if item.get("admission_state") != "ready" or item.get("admission_pass") is not False:
            continue

        item_id = item["item_id"]
        if item.get("d2a_pass") is False:
            _error(diag, plan_dir / "plan.md",
                   f"пункт {item_id}: вес {item['weight_tokens']} > порога {threshold} "
                   f"оценочных токенов ({calibration})")

        for gap in item.get("gaps", []):
            kind = gap.get("kind")
            if kind == plan_weight.GAP_OVERSIZED_FILE:
                _error(diag, plan_dir / "plan.md",
                       f"пункт {item_id}: файл {gap['path']} — {gap['bytes']} байт, "
                       f"{gap['est_tokens']} оценочных токенов; лимиты одного чтения "
                       f"{limits['size_bytes']} байт / {limits['tokens']} токенов "
                       f"({calibration})")
            elif kind in (plan_weight.GAP_MISSING_FILE, plan_weight.GAP_UNREADABLE_ROOT,
                          plan_weight.GAP_UNRESOLVED_ENTRY):
                subject = gap.get("path") or gap.get("entry") or "обязательный вход"
                _error(diag, plan_dir / "plan.md",
                       f"пункт {item_id}: обязательный вход {subject!r} не проходит "
                       f"D2(b): {gap['detail']}")

        for gap in item.get("admission_gaps", []):
            if gap.get("code") == "read_budget_contract_invalid":
               _error(diag, plan_dir / "root" / "contracts" / "read-budget-v1.md",
                       f"пункт {item_id}: {gap.get('detail')}")


def lint_bundle_freshness(plan_dir, layout: str, diag) -> None:
    """Verify ready v2 bundles and committed deterministic projections without rebuilding."""
    if layout != "v2":
        return
    plan_dir = Path(plan_dir)
    try:
        measured = plan_weight.measure_plan(plan_dir, plan_weight.Measurer())
        active_phases = {phase_id for phase_id, status in plan_layout.phase_statuses(plan_dir).items()
                         if status == plan_status.STATUS_PROGRESS}
    except plan_weight.PlanWeightError as exc:
        _bundle_error(diag, plan_dir / "plan.md", f"не удалось загрузить ready-область: {exc}")
        return
    except plan_layout.PlanLayoutError as exc:
        _bundle_error(diag, plan_dir / "status.md", f"не удалось определить активную фазу: {exc}")
        return
    active_items = [item for item in measured["items"]
                    if item.get("admission_state") == "ready"
                    and item["item_id"].split(".", 1)[0] in active_phases]
    # Bundle v1 became a committed carrier in P3. A v2 plan that has not entered
    # that producer surface must remain compatible with the pre-P3 reader path.
    if not any(plan_layout.carrier_path(plan_dir, "bundle", item_id=item["item_id"]).is_file()
               for item in active_items):
        return
    for item in active_items:
        if item.get("admission_state") != "ready":
            continue
        item_id = item["item_id"]
        target = plan_layout.carrier_path(plan_dir, "bundle", item_id=item_id)
        try:
            expected = plan_bundle.render(plan_dir, item_id).encode("utf-8")
            actual = target.read_bytes()
        except plan_bundle.BundleError as exc:
            _bundle_error(diag, target, f"пункт {item_id}: {exc}")
            continue
        except OSError:
            _bundle_error(diag, target, f"пункт {item_id}: missing_entry: bundle отсутствует")
            continue
        if actual == expected:
            continue
        try:
            current = json.loads(actual)
            expected_model = json.loads(expected)
            current_entries = {(e["declaration_ref"]["field"], e["declaration_ref"]["ordinal"],
                                e["path"], str(e["selector"])) for e in current.get("entries", [])}
            expected_entries = {(e["declaration_ref"]["field"], e["declaration_ref"]["ordinal"],
                                 e["path"], str(e["selector"])) for e in expected_model["entries"]}
            if current.get("declaration") != expected_model["declaration"]:
                code = "stale_vs_spec"
            elif expected_entries - current_entries:
                code = "missing_entry"
            elif current_entries - expected_entries:
                diag.warning(target, None, f"{BUNDLE_GATE_ID}: пункт {item_id}: extraneous_entry")
                continue
            else:
                code = "hash_mismatch"
        except Exception:
            code = "hash_mismatch"
        _bundle_error(diag, target, f"пункт {item_id}: {code}")
    for builder in (plan_decisions.build_views, plan_status.build_status, plan_item_state.build_states):
        try:
            builder(plan_dir, check=True)
        except (plan_decisions.DecisionError, plan_status.StatusError,
                plan_item_state.ItemStateError, plan_projection.ProjectionError) as exc:
            _bundle_error(diag, plan_dir, f"generated view stale: {exc}")


__all__ = ("BUNDLE_GATE_ID", "GATE_ID", "lint_bundle_freshness", "lint_read_budget")
