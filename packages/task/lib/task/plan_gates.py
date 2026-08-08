"""Hard admission gates for executable-plan layout v2.

The gate deliberately delegates all measurement and timing decisions: ``plan_weight``
owns the mandatory-read graph and its one weight, while ``plan_admission`` owns the
``historical``/``pending``/``ready`` state machine.  This module only turns a failed
ready D2 result into actionable plan-lint diagnostics.
"""
from __future__ import annotations

from pathlib import Path

from task import plan_weight


GATE_ID = "read-budget-v1"


def _calibration_label(measurer) -> str:
    artifact = measurer.artifact
    target = artifact["calibration_target"]
    return (f"token-estimate-calibration v{artifact['version']} "
            f"({target['provider']}/{target['requested_model_id']})")


def _error(diag, path, message: str) -> None:
    diag.error(Path(path), None, f"{GATE_ID}: {message}")


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


__all__ = ("GATE_ID", "lint_read_budget")
