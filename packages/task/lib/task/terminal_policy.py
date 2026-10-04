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
# `plan-exec` is the legacy spelling of `plan-run`; readers accept both.
_EXECUTION_COMMANDS = frozenset(("plan-run", "plan-exec", "plan-close", "plan-audit"))
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
            "TERMINAL_SPEC_UNREADABLE", f"item spec is not readable: {path}") from exc


def build_decision(plan_dir, item_id: str, *, result: str, validation: list[dict],
                   repair_exhausted: dict | None = None,
                   producer_readiness: dict | None = None,
                   phase_reentry: dict | None = None,
                   fix_branch: dict | None = None) -> dict:
    """Build the decision carrier required by a new item close."""
    if result not in _CLOSE_RESULTS:
        raise TerminalPolicyError("TERMINAL_RESULT_INVALID", f"not close result: {result}")
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
             item_id: str | None = None, _historical: bool = False) -> None:
    if not isinstance(decision, dict):
        raise TerminalPolicyError(
            "TERMINAL_EVIDENCE_REQUIRED", "terminal item requires reducer decision")
    if result in _BLOCK_RESULTS:
        if decision.get("terminal") is not True or decision.get("action") not in _TERMINAL_ACTIONS:
            raise TerminalPolicyError(
                "TERMINAL_BLOCK_UNCONFIRMED",
                "blocked/escalated is only valid after terminal reducer action",
            )
        return
    if result not in _CLOSE_RESULTS:
        return
    evidence = decision.get("terminal_evidence")
    expected = {"schema_version", "spec_sha256", "validation", "repair_exhausted"}
    if not isinstance(evidence, dict) or set(evidence) != expected:
        raise TerminalPolicyError(
            "TERMINAL_EVIDENCE_REQUIRED", "no closed terminal-evidence/v1")
    if evidence["schema_version"] != "terminal-evidence/v1":
        raise TerminalPolicyError(
            "TERMINAL_EVIDENCE_REQUIRED", "unsupported terminal evidence schema")
    if not isinstance(evidence["spec_sha256"], str) or not _SHA256_RE.fullmatch(
            evidence["spec_sha256"]):
        raise TerminalPolicyError("TERMINAL_SPEC_STALE", "spec_sha256 is invalid")
    if plan_dir is not None and item_id is not None:
        if evidence["spec_sha256"] != _spec_digest(plan_dir, item_id):
            raise TerminalPolicyError("TERMINAL_SPEC_STALE", "terminal evidence is tied to the old technical specification")
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
                plan_readiness.validate_readiness(record, plan_dir=plan_dir)
            except plan_readiness.ReadinessError as exc:
                raise TerminalPolicyError("PRODUCER_READINESS_REQUIRED", str(exc)) from exc
            if (record["producer_item"] != item_id
                    or record["consumer_item"] != declared["consumer_item"]
                    or record["mode"] not in declared["modes"]):
                raise TerminalPolicyError("PRODUCER_READINESS_REQUIRED", "readiness does not match Deliverables")
        if "phase_reentry" in decision:
            try:
                plan_readiness.validate_reentry(decision["phase_reentry"])
            except plan_readiness.ReadinessError as exc:
                raise TerminalPolicyError("PHASE_REENTRY_INVALID", str(exc)) from exc
        if "fix_branch" in decision:
            declared_items = tuple(
                spec.stem
                for phase_id in plan_layout.phase_paths(plan_dir)
                for spec in plan_layout.item_spec_paths(plan_dir, phase_id)
            )
            try:
                plan_readiness.validate_fix_branch(
                    decision["fix_branch"], declared_items=declared_items)
            except plan_readiness.ReadinessError as exc:
                raise TerminalPolicyError("FIX_BRANCH_INVALID", str(exc)) from exc
            if decision["fix_branch"]["target_item"] != item_id:
                raise TerminalPolicyError(
                    "FIX_BRANCH_INVALID", "terminal fix evidence belongs to another target item")
    rows = evidence["validation"]
    if not isinstance(rows, list) or not rows:
        raise TerminalPolicyError(
            "TERMINAL_VALIDATION_MISSING", "no recorded Validation carriers")
    for index, row in enumerate(rows):
        if (not isinstance(row, dict)
                or set(row) != {"carrier", "status", "evidence_ids"}
                or not isinstance(row.get("carrier"), str) or not row["carrier"]
                or row.get("status") not in {"green", "red"}
                or not _nonempty_strings(row.get("evidence_ids"))):
            raise TerminalPolicyError(
                "TERMINAL_VALIDATION_INVALID", f"validation[{index}] is invalid")
    red = [row["carrier"] for row in rows if row["status"] != "green"]
    if red:
        raise TerminalPolicyError(
            "TERMINAL_VALIDATION_RED",
            f"mandatory Validation still red: {', '.join(red)}",
        )

    if plan_dir is not None and item_id is not None:
        from task import plan_repair
        from task import review_packet, plan_bundle
        try:
            declared = review_packet.declarations(plan_bundle._fields(plan_dir, item_id))
            review_packet.validate_self_check(Path(plan_dir), declared)
            requested = review_packet.review_request(plan_dir, item_id)
            if requested:
                review_packet.check_request(plan_dir, item_id, selector=requested["reviewer"], effort=requested["effort"])
            selected = requested["reviewer"] if requested else declared.get("owner-review")
            if selected:
                if _historical:
                    review_packet.require_committed_green(plan_dir, item_id, selected,
                        effort=requested["effort"] if requested else None, decision=decision, result=result)
                else:
                    review_packet.require_green(plan_dir, item_id, selected,
                                                effort=requested["effort"] if requested else None)
        except plan_bundle.BundleError:
            # Historical minimal fixtures have no independently declared carrier.
            pass
        except review_packet.ReviewError as exc:
            raise TerminalPolicyError(exc.code, str(exc)) from exc
        unresolved = plan_repair.unresolved_incidents(plan_dir, item_id)
        if unresolved:
            carriers = ", ".join(command for _subject, command, _digest in unresolved)
            raise TerminalPolicyError(
                "REPAIR_POST_VALIDATION_REQUIRED",
                f"qualified repair did not complete exact original carrier: {carriers}",
            )

    exhausted = evidence["repair_exhausted"]
    if result == "closed-green":
        if exhausted is not None:
            raise TerminalPolicyError(
                "TERMINAL_EVIDENCE_INVALID", "green close does not accept repair_exhausted")
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
            "closed-deviations requires closed repair_exhausted evidence",
        )


def validate_predecessor(decision, *, result: str, plan_dir: Path, item_id: str) -> None:
    """Consume committed predecessor acceptance without re-closing live bytes.

    Review-required predecessors prove the exact close and reviewed inventory at
    their closure commit. New item close and journal append keep live validation.
    """
    validate(decision, result=result, plan_dir=plan_dir, item_id=item_id, _historical=True)


def validate_entry(entry: dict, *, plan_dir: Path | None = None,
                   _historical: bool = False) -> None:
    item_id = entry.get("item_id")
    decision = entry.get("decision")
    if isinstance(decision, dict) and decision.get("signal_class") == "producer-readiness":
        from task import plan_readiness
        declared_items = ()
        if plan_dir is not None:
            declared_items = tuple(
                spec.stem
                for phase_id in plan_layout.phase_paths(plan_dir)
                for spec in plan_layout.item_spec_paths(plan_dir, phase_id)
            )
        try:
            expected = plan_readiness.correction_decision(
                observed_mode=decision.get("observed_mode"),
                reentry=decision.get("phase_reentry"),
                fix_branch=decision.get("fix_branch"),
                declared_items=declared_items,
            )
        except plan_readiness.ReadinessError as exc:
            raise TerminalPolicyError("READINESS_DECISION_INVALID", str(exc)) from exc
        if set(decision) != set(expected) or any(
                decision.get(key) != value for key, value in expected.items()):
            raise TerminalPolicyError(
                "READINESS_DECISION_INVALID", "decision does not match reducer outcome")
        if entry.get("result") in (_CLOSE_RESULTS | _BLOCK_RESULTS):
            raise TerminalPolicyError(
                "READINESS_DECISION_NONTERMINAL",
                "producer/re-entry routing cannot directly terminalize item",
            )
    if (entry.get("command") not in _EXECUTION_COMMANDS
            or not isinstance(item_id, str) or not _ITEM_RE.fullmatch(item_id)
            or entry.get("result") not in (_CLOSE_RESULTS | _BLOCK_RESULTS)):
        return
    if plan_dir is not None and (Path(plan_dir) / "decisions").is_dir():
        from task import plan_decisions
        try:
            plan_decisions.load_decisions(plan_dir)
        except plan_decisions.DecisionError as exc:
            raise TerminalPolicyError("TERMINAL_DECISIONS_INVALID", str(exc)) from exc
    validate(
        entry.get("decision"), result=entry["result"], plan_dir=plan_dir, item_id=item_id,
        _historical=_historical)


def validate_current_entry(entry: dict, *, plan_dir: Path) -> None:
    """Lint a committed closure historically, or an uncommitted closure live.

    Only absence of a committed terminal row permits live validation. Invalid
    immutable closure evidence must never fall back to a current receipt.
    """
    try:
        validate_entry(entry, plan_dir=plan_dir, _historical=True)
    except TerminalPolicyError as exc:
        if exc.code != "REVIEW_CLOSURE_UNCOMMITTED":
            raise
        validate_entry(entry, plan_dir=plan_dir)
