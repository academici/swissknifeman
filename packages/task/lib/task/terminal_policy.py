"""One reducer-owned terminal policy for executable Task items."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from task import plan_layout


class TerminalPolicyError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


_ITEM_RE = re.compile(r"^P[0-9]+\.[0-9]+$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_EXECUTION_COMMANDS = frozenset(("plan-exec", "plan-run", "plan-close", "plan-audit"))
_CLOSE_RESULTS = frozenset(("closed-green", "closed-deviations"))
_BLOCK_RESULTS = frozenset(("blocked", "escalated"))
_TERMINAL_ACTIONS = frozenset(("terminal-block", "approval-required", "authority-denied"))
_REPAIR_VERDICTS = frozenset(("material", "outside-scope", "unsafe"))


def _nonempty_strings(value) -> bool:
    return (isinstance(value, list) and bool(value) and len(value) == len(set(value))
            and all(isinstance(item, str) and item for item in value))


def _spec_digest(plan_dir: Path, item_id: str) -> str:
    path = plan_layout.carrier_path(plan_dir, "item-spec", item_id=item_id)
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise TerminalPolicyError(
            "TERMINAL_SPEC_UNREADABLE", f"item spec не читается: {path}") from exc


def build_decision(plan_dir, item_id: str, *, result: str, validation: list[dict],
                   repair_exhausted: dict | None = None,
                   producer_readiness: dict | None = None,
                   phase_reentry: dict | None = None,
                   fix_branch: dict | None = None) -> dict:
    """Build the decision carrier required by a new item close."""
    if result not in _CLOSE_RESULTS:
        raise TerminalPolicyError("TERMINAL_RESULT_INVALID", f"не close result: {result}")
    decision = {
        "signal_class": "acceptance",
        "scope_class": "item",
        "action": "close-green" if result == "closed-green" else "close-deviations",
        "recovered": True,
        "terminal": True,
        "terminal_evidence": {
            "schema_version": "terminal-evidence/v1",
            "spec_sha256": _spec_digest(Path(plan_dir), item_id),
            "validation": validation,
            "repair_exhausted": repair_exhausted,
        },
    }
    if producer_readiness is not None:
        decision["producer_readiness"] = producer_readiness
    if phase_reentry is not None:
        decision["phase_reentry"] = phase_reentry
    if fix_branch is not None:
        decision["fix_branch"] = fix_branch
    validate(decision, result=result, plan_dir=Path(plan_dir), item_id=item_id)
    return decision


def validate(decision, *, result: str, plan_dir: Path | None = None,
             item_id: str | None = None) -> None:
    if not isinstance(decision, dict):
        raise TerminalPolicyError(
            "TERMINAL_EVIDENCE_REQUIRED", "terminal item требует reducer decision")
    if result in _BLOCK_RESULTS:
        if decision.get("terminal") is not True or decision.get("action") not in _TERMINAL_ACTIONS:
            raise TerminalPolicyError(
                "TERMINAL_BLOCK_UNCONFIRMED",
                "blocked/escalated допустим только после terminal reducer action",
            )
        return
    if result not in _CLOSE_RESULTS:
        return
    evidence = decision.get("terminal_evidence")
    expected = {"schema_version", "spec_sha256", "validation", "repair_exhausted"}
    if not isinstance(evidence, dict) or set(evidence) != expected:
        raise TerminalPolicyError(
            "TERMINAL_EVIDENCE_REQUIRED", "нет closed terminal-evidence/v1")
    if evidence["schema_version"] != "terminal-evidence/v1":
        raise TerminalPolicyError(
            "TERMINAL_EVIDENCE_REQUIRED", "неподдерживаемая terminal evidence schema")
    if not isinstance(evidence["spec_sha256"], str) or not _SHA256_RE.fullmatch(
            evidence["spec_sha256"]):
        raise TerminalPolicyError("TERMINAL_SPEC_STALE", "spec_sha256 невалиден")
    if plan_dir is not None and item_id is not None:
        if evidence["spec_sha256"] != _spec_digest(plan_dir, item_id):
            raise TerminalPolicyError("TERMINAL_SPEC_STALE", "terminal evidence привязано к старому ТЗ")
        # A producer that declares a semantic readiness edge cannot silently
        # close with an empty or unqualified output.  The typed record remains
        # additive to terminal-evidence so historic terminal rows stay readable.
        from task import plan_bundle, plan_readiness
        try:
            declared = plan_readiness.directive(
                plan_bundle._fields(plan_dir, item_id).get("Deliverables", ""))
        except plan_bundle.BundleError:
            # Minimal historic/unit fixtures can lack a complete phase item
            # carrier. They have no declared readiness edge to enforce.
            declared = None
        if declared is not None:
            record = decision.get("producer_readiness")
            try:
                plan_readiness.validate_readiness(record)
            except plan_readiness.ReadinessError as exc:
                raise TerminalPolicyError("PRODUCER_READINESS_REQUIRED", str(exc)) from exc
            if (record["producer_item"] != item_id
                    or record["consumer_item"] != declared["consumer_item"]
                    or record["mode"] not in declared["modes"]):
                raise TerminalPolicyError("PRODUCER_READINESS_REQUIRED", "readiness не совпадает с Deliverables")
        if "phase_reentry" in decision:
            try:
                plan_readiness.validate_reentry(decision["phase_reentry"])
            except plan_readiness.ReadinessError as exc:
                raise TerminalPolicyError("PHASE_REENTRY_INVALID", str(exc)) from exc
        if "fix_branch" in decision:
            try:
                plan_readiness.validate_fix_branch(decision["fix_branch"])
            except plan_readiness.ReadinessError as exc:
                raise TerminalPolicyError("FIX_BRANCH_INVALID", str(exc)) from exc
    rows = evidence["validation"]
    if not isinstance(rows, list) or not rows:
        raise TerminalPolicyError(
            "TERMINAL_VALIDATION_MISSING", "нет recorded Validation carriers")
    for index, row in enumerate(rows):
        if (not isinstance(row, dict)
                or set(row) != {"carrier", "status", "evidence_ids"}
                or not isinstance(row.get("carrier"), str) or not row["carrier"]
                or row.get("status") not in {"green", "red"}
                or not _nonempty_strings(row.get("evidence_ids"))):
            raise TerminalPolicyError(
                "TERMINAL_VALIDATION_INVALID", f"validation[{index}] невалидна")
    red = [row["carrier"] for row in rows if row["status"] != "green"]
    if red:
        raise TerminalPolicyError(
            "TERMINAL_VALIDATION_RED",
            f"обязательная Validation ещё красная: {', '.join(red)}",
        )

    exhausted = evidence["repair_exhausted"]
    if result == "closed-green":
        if exhausted is not None:
            raise TerminalPolicyError(
                "TERMINAL_EVIDENCE_INVALID", "green close не принимает repair_exhausted")
        return
    required = {"classifier", "failed_carrier", "verdict", "reason", "continuation",
                "evidence_ids"}
    if (not isinstance(exhausted, dict) or set(exhausted) != required
            or exhausted.get("classifier") != "recoverable-validation-gap/v1"
            or not isinstance(exhausted.get("failed_carrier"), str)
            or not exhausted["failed_carrier"]
            or exhausted.get("verdict") not in _REPAIR_VERDICTS
            or not isinstance(exhausted.get("reason"), str) or not exhausted["reason"]
            or not isinstance(exhausted.get("continuation"), str)
            or not exhausted["continuation"]
            or not _nonempty_strings(exhausted.get("evidence_ids"))):
        raise TerminalPolicyError(
            "REPAIR_EXHAUSTED_REQUIRED",
            "closed-deviations требует closed repair_exhausted evidence",
        )


def validate_entry(entry: dict, *, plan_dir: Path | None = None) -> None:
    item_id = entry.get("item_id")
    if (entry.get("command") not in _EXECUTION_COMMANDS
            or not isinstance(item_id, str) or not _ITEM_RE.fullmatch(item_id)
            or entry.get("result") not in (_CLOSE_RESULTS | _BLOCK_RESULTS)):
        return
    validate(
        entry.get("decision"), result=entry["result"], plan_dir=plan_dir, item_id=item_id)
