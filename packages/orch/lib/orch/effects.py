"""Effect receipts: the precondition is checked again right before an effect, and an effect happens once.

Pure functions: no I/O and no system clock; the time of a check or a record comes from the caller.
"""
from __future__ import annotations

from dataclasses import dataclass

from orch import CONTRACT_VERSION, contracts
from orch.port import PortError

MISMATCH_CODE = "PRECONDITION_CHANGED"


@dataclass(frozen=True)
class Verdict:
    proceed: bool
    receipt: dict | None  # a schema-valid effect-receipt when the effect is not executed; None to execute or to reconcile


def _validated(receipt: dict) -> dict:
    issues = [issue for issue in contracts.validate(receipt, "effect-receipt") if issue.level == "error"]
    if issues:
        raise PortError("INPUT_INVALID", "effect-receipt does not match exec/v1",
                        {"issues": [issue._asdict() for issue in issues]})
    return receipt


def record(*, effect_key: str, kind: str, intent: dict, outcome: str, result: dict | None = None,
           reconcile_method: str = "none", observed_prior: dict | None = None, attempt_id: str | None = None,
           owner_epoch: int | None = None, now: str) -> dict:
    """Build a schema-valid receipt. With ``observed_prior`` the precondition re-check is recorded as well."""
    receipt = {
        "$schema": contracts.URN_PREFIX + "effect-receipt:v1",
        "contract_version": CONTRACT_VERSION,
        "effect_key": effect_key,
        "kind": kind,
        "intent": intent,
        "precondition_checked": observed_prior is not None,
        "outcome": outcome,
        "reconcile": {"method": reconcile_method},
        "recorded_at": now,
    }
    if observed_prior is not None:
        matched = observed_prior == intent.get("expected_prior")
        receipt["precondition"] = {"checked_at": now, "matched": matched, "observed_prior": observed_prior}
        if not matched:
            receipt["precondition"]["reason_code"] = MISMATCH_CODE
    if result is not None:
        receipt["result"] = result
    if attempt_id is not None:
        receipt["attempt_id"] = attempt_id
    if owner_epoch is not None:
        receipt["owner_epoch"] = owner_epoch
    return _validated(receipt)


def check(*, effect_key: str, kind: str, intent: dict, observed_prior: dict, receipts: list,
          attempt_id: str | None = None, owner_epoch: int | None = None, now: str) -> Verdict:
    """Decide, right before an effect, whether it may run.

    1. a receipt of the same ``effect_key`` that is applied: ``already_applied``, nothing runs again;
    2. a receipt with outcome ``unknown``: no verdict to run, the caller reconciles (``retry.decide``);
    3. the observed prior state differs from the expected one: outcome ``failed``, nothing runs;
    4. otherwise the effect may run; after it ``record(outcome="applied", observed_prior=...)``.
    """
    same = [_validated(receipt) for receipt in receipts if receipt.get("effect_key") == effect_key]
    common = {"effect_key": effect_key, "kind": kind, "intent": intent, "attempt_id": attempt_id,
              "owner_epoch": owner_epoch, "now": now}
    if any(receipt["outcome"] in ("applied", "already_applied") for receipt in same):
        return Verdict(False, record(outcome="already_applied", **common))
    if any(receipt["outcome"] == "unknown" for receipt in same):
        return Verdict(False, None)
    if observed_prior != intent.get("expected_prior"):
        return Verdict(False, record(outcome="failed", observed_prior=observed_prior,
                                     result={"reason": MISMATCH_CODE}, **common))
    return Verdict(True, None)
