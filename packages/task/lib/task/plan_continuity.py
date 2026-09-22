"""Provider-neutral continuation reducer and persisted-context validation."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
from pathlib import Path
import re


WORK_ESTIMATE_SCHEMA_VERSION = "session-work-estimate/v1"
DECISION_SCHEMA_VERSION = "session-continuity-decision/v1"
OUTCOMES = ("continue-root", "isolated-child-return", "cold-start-root", "waiting-owner", "waiting-external", "terminal")
COLD_START_REASONS = (
    "context-budget",
    "capability-missing",
    "owner-pause-no-resume",
    "owner-requested-new-session",
    "whole-plan-independent-audit",
    "design-root-terminal",
)
LIFECYCLES = (
    "active",
    "scope-complete",
    "waiting-owner",
    "waiting-external",
    "owner-pause-no-resume",
    "owner-requested-new-session",
    "whole-plan-independent-audit",
    "design-root-terminal",
    "terminal",
)
CONTEXT_HEALTH = ("sufficient", "insufficient", "unavailable")
_WORK_KEYS = frozenset((
    "schema_version", "route_attested", "capabilities_attested",
    "capabilities_sufficient", "context_attested", "context_health",
    "batch_receipt_valid", "remaining_batch_digest", "loaded_inputs_reusable",
    "cold_start_cost", "lifecycle", "isolated_review", "reviewer_task", "checkpoint",
    "external_pause",
))
_DECISION_KEYS = frozenset(("schema_version", "outcome", "reason", "evidence", "runnable"))
_CONFIG_ROOT = Path(__file__).resolve().parents[2] / "configs"
_WORK_SCHEMA_PATH = _CONFIG_ROOT / "session-work-estimate-v1.schema.json"
_DECISION_SCHEMA_PATH = _CONFIG_ROOT / "session-continuity-decision-v1.schema.json"
_SHA256_RE = re.compile(r"(?:sha256:)?[0-9a-f]{64}")
_LEGACY_CONTEXTS = {
    "same-session": "continue-root",
    "fresh session": "cold-start-root: owner-pause-no-resume",
    "cold-start": "cold-start-root: owner-pause-no-resume",
}


class ContinuityError(ValueError):
    """The evidence cannot support one deterministic continuation decision."""


@dataclass(frozen=True)
class WorkEstimate:
    """Attested inputs consumed by the continuity reducer."""

    route_attested: bool
    capabilities_attested: bool
    capabilities_sufficient: bool
    context_attested: bool
    context_health: str
    batch_receipt_valid: bool
    remaining_batch_digest: str
    loaded_inputs_reusable: bool
    cold_start_cost: int
    lifecycle: str = "active"
    isolated_review: bool = False
    reviewer_task: str | None = None
    checkpoint: str | None = None
    external_pause: dict | None = None
    schema_version: str = WORK_ESTIMATE_SCHEMA_VERSION

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ContinuityDecision:
    outcome: str
    reason: str
    evidence: tuple[str, ...]
    runnable: bool
    schema_version: str = DECISION_SCHEMA_VERSION

    def as_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["evidence"] = list(self.evidence)
        return value

    @property
    def context(self) -> str:
        if self.outcome == "cold-start-root":
            return f"{self.outcome}: {self.reason}"
        return self.outcome


def _schema(path: Path, version: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContinuityError(f"CONTINUITY_SCHEMA_INVALID: {path}") from exc
    if value.get("schema_version") != version:
        raise ContinuityError(f"CONTINUITY_SCHEMA_INVALID: {path}")
    return value


def validate_contracts() -> bool:
    """Fail closed when runtime enums drift from the package-owned schemas."""
    work = _schema(_WORK_SCHEMA_PATH, WORK_ESTIMATE_SCHEMA_VERSION)
    decision = _schema(_DECISION_SCHEMA_PATH, DECISION_SCHEMA_VERSION)
    if tuple(work.get("properties", {}).get("lifecycle", {}).get("enum", ())) != LIFECYCLES:
        raise ContinuityError("CONTINUITY_SCHEMA_INVALID: lifecycle enum drift")
    if tuple(work.get("properties", {}).get("context_health", {}).get("enum", ())) != CONTEXT_HEALTH:
        raise ContinuityError("CONTINUITY_SCHEMA_INVALID: context-health enum drift")
    if tuple(decision.get("properties", {}).get("outcome", {}).get("enum", ())) != OUTCOMES:
        raise ContinuityError("CONTINUITY_SCHEMA_INVALID: outcome enum drift")
    if tuple(decision.get("cold_start_reasons", ())) != COLD_START_REASONS:
        raise ContinuityError("CONTINUITY_SCHEMA_INVALID: cold-start reason enum drift")
    return True


def validate_estimate(estimate: WorkEstimate) -> WorkEstimate:
    """Validate evidence shape and relationships before reduction."""
    validate_contracts()
    if not isinstance(estimate, WorkEstimate):
        raise ContinuityError("CONTINUITY_EVIDENCE_MISSING: work estimate")
    if estimate.schema_version != WORK_ESTIMATE_SCHEMA_VERSION:
        raise ContinuityError("CONTINUITY_SCHEMA_INVALID: work estimate version")
    if estimate.lifecycle not in LIFECYCLES or estimate.context_health not in CONTEXT_HEALTH:
        raise ContinuityError("CONTINUITY_EVIDENCE_INVALID: closed enum")
    booleans = (
        estimate.route_attested,
        estimate.capabilities_attested,
        estimate.capabilities_sufficient,
        estimate.context_attested,
        estimate.batch_receipt_valid,
        estimate.loaded_inputs_reusable,
        estimate.isolated_review,
    )
    if not all(isinstance(value, bool) for value in booleans):
        raise ContinuityError("CONTINUITY_EVIDENCE_INVALID: boolean field")
    if not _SHA256_RE.fullmatch(estimate.remaining_batch_digest):
        raise ContinuityError("CONTINUITY_EVIDENCE_MISSING: remaining batch digest")
    if not isinstance(estimate.cold_start_cost, int) or isinstance(estimate.cold_start_cost, bool) \
            or estimate.cold_start_cost < 0:
        raise ContinuityError("CONTINUITY_EVIDENCE_INVALID: cold-start cost")
    if estimate.context_health == "unavailable" and estimate.context_attested:
        raise ContinuityError("CONTINUITY_EVIDENCE_INVALID: unavailable context is not attested")
    if estimate.context_health != "unavailable" and not estimate.context_attested:
        raise ContinuityError("CONTINUITY_EVIDENCE_MISSING: context health attestation")
    if estimate.isolated_review and not estimate.reviewer_task:
        raise ContinuityError("CONTINUITY_EVIDENCE_MISSING: bounded reviewer task")
    if estimate.lifecycle == "waiting-external" or estimate.external_pause is not None:
        _validate_external_pause(estimate.external_pause)
        if not estimate.checkpoint:
            raise ContinuityError("CONTINUITY_EVIDENCE_MISSING: external durable checkpoint")
    return estimate


def _validate_external_pause(value: dict) -> dict:
    keys = {"reason", "started_at", "resume_at", "observed_at", "fingerprint",
            "runnable_after", "predicate_satisfied", "continuation"}
    if (not isinstance(value, dict) or set(value) != keys
            or any(not isinstance(value[key], str) or not value[key].strip()
                   for key in keys - {"predicate_satisfied"})
            or not isinstance(value["predicate_satisfied"], bool)
            or not _SHA256_RE.fullmatch(value["fingerprint"])):
        raise ContinuityError("CONTINUITY_EVIDENCE_INVALID: external checkpoint")
    try:
        times = [datetime.fromisoformat(value[key].replace("Z", "+00:00"))
                 for key in ("started_at", "resume_at", "observed_at")]
        if any(time.tzinfo is None for time in times) or times[1] <= times[0] or times[2] < times[0]:
            raise ValueError("observation window")
    except (ValueError, TypeError) as exc:
        raise ContinuityError("CONTINUITY_EVIDENCE_INVALID: external observation times") from exc
    return value


def reduce(estimate: WorkEstimate) -> ContinuityDecision:
    """Choose continuity once; adapters may verify this result but never re-choose it."""
    estimate = validate_estimate(estimate)
    evidence = (
        f"batch:{estimate.remaining_batch_digest}",
        f"loaded-inputs:{'reusable' if estimate.loaded_inputs_reusable else 'not-reusable'}",
        f"cold-start-cost:{estimate.cold_start_cost}",
    )
    if estimate.lifecycle == "waiting-owner":
        return ContinuityDecision("waiting-owner", "owner-wait", evidence, False)
    if estimate.external_pause is not None:
        pause = estimate.external_pause
        evidence += tuple(f"{key}:{pause[key]}" for key in
                          ("reason", "started_at", "resume_at", "observed_at", "fingerprint",
                           "runnable_after", "continuation")) + (f"checkpoint:{estimate.checkpoint}",)
        observed = datetime.fromisoformat(pause["observed_at"].replace("Z", "+00:00"))
        resume = datetime.fromisoformat(pause["resume_at"].replace("Z", "+00:00"))
        if observed < resume or not pause["predicate_satisfied"]:
            return ContinuityDecision("waiting-external", "external-wait", evidence, False)
    if estimate.lifecycle == "terminal":
        return ContinuityDecision("terminal", "terminal-evidence", evidence, False)
    if not estimate.route_attested or not estimate.batch_receipt_valid:
        raise ContinuityError("CONTINUITY_EVIDENCE_MISSING: route or batch receipt")
    if not estimate.capabilities_attested:
        raise ContinuityError("CONTINUITY_EVIDENCE_MISSING: capability attestation")

    reason = None
    if estimate.lifecycle in COLD_START_REASONS:
        reason = estimate.lifecycle
    elif not estimate.capabilities_sufficient:
        reason = "capability-missing"
    elif estimate.context_health == "insufficient":
        reason = "context-budget"
    if reason is not None:
        if not estimate.checkpoint:
            raise ContinuityError("CONTINUITY_EVIDENCE_MISSING: durable checkpoint")
        return ContinuityDecision(
            "cold-start-root", reason, evidence + (f"checkpoint:{estimate.checkpoint}",), True)
    if estimate.lifecycle == "scope-complete":
        if not estimate.checkpoint:
            raise ContinuityError("CONTINUITY_EVIDENCE_MISSING: durable checkpoint")
        return ContinuityDecision("continue-root", "authorized-scope-complete",
                                  evidence + ("lifecycle:scope-complete", f"checkpoint:{estimate.checkpoint}"), True)
    if estimate.isolated_review:
        return ContinuityDecision(
            "isolated-child-return", "independent-review",
            evidence + (f"reviewer:{estimate.reviewer_task}",), True)
    return ContinuityDecision(
        "continue-root",
        ("context-telemetry-unavailable" if estimate.context_health == "unavailable"
         else "compatible-active-work"),
        evidence,
        True,
    )


def estimate_from_dict(value: dict) -> WorkEstimate:
    """Load one exact JSON-compatible work-estimate carrier."""
    if not isinstance(value, dict) or set(value) not in (_WORK_KEYS, _WORK_KEYS - {"external_pause"}):
        raise ContinuityError("CONTINUITY_EVIDENCE_INVALID: work estimate shape")
    try:
        estimate = WorkEstimate(**value)
    except TypeError as exc:
        raise ContinuityError("CONTINUITY_EVIDENCE_INVALID: work estimate shape") from exc
    return validate_estimate(estimate)


def validate_decision(decision: ContinuityDecision) -> ContinuityDecision:
    """Validate a reducer result at renderer/delivery adapter boundaries."""
    validate_contracts()
    if not isinstance(decision, ContinuityDecision) or decision.outcome not in OUTCOMES:
        raise ContinuityError("CONTINUITY_DECISION_INVALID: outcome")
    if decision.schema_version != DECISION_SCHEMA_VERSION or not decision.reason:
        raise ContinuityError("CONTINUITY_DECISION_INVALID: shape")
    if (not isinstance(decision.evidence, tuple)
            or not all(isinstance(value, str) and value for value in decision.evidence)
            or not isinstance(decision.runnable, bool)):
        raise ContinuityError("CONTINUITY_DECISION_INVALID: evidence")
    if decision.outcome == "cold-start-root":
        if (decision.reason not in COLD_START_REASONS
                or not any(value.startswith("checkpoint:")
                           or value.startswith("persisted-context:")
                           for value in decision.evidence)):
            raise ContinuityError("CONTINUITY_DECISION_INVALID: cold-start evidence")
    elif decision.reason in COLD_START_REASONS:
        raise ContinuityError("CONTINUITY_DECISION_INVALID: reason/outcome mismatch")
    if decision.reason == "authorized-scope-complete":
        if (decision.outcome != "continue-root"
                or "lifecycle:scope-complete" not in decision.evidence
                or not any(value.startswith("checkpoint:") for value in decision.evidence)):
            raise ContinuityError("CONTINUITY_DECISION_INVALID: scope completion evidence")
    if decision.outcome == "waiting-external":
        if not all(any(value.startswith(prefix + ":") for value in decision.evidence)
                   for prefix in ("reason", "started_at", "resume_at", "observed_at", "fingerprint",
                                  "runnable_after", "continuation", "checkpoint")):
            raise ContinuityError("CONTINUITY_DECISION_INVALID: external checkpoint missing")
    if decision.outcome in {"waiting-owner", "waiting-external", "terminal"} and decision.runnable:
        raise ContinuityError("CONTINUITY_DECISION_INVALID: non-runnable outcome is runnable")
    if decision.outcome not in {"waiting-owner", "waiting-external", "terminal"} and not decision.runnable:
        raise ContinuityError("CONTINUITY_DECISION_INVALID: runnable outcome suppressed")
    return decision


def decision_from_dict(value: dict) -> ContinuityDecision:
    if (not isinstance(value, dict) or set(value) != _DECISION_KEYS
            or not isinstance(value.get("evidence"), list)):
        raise ContinuityError("CONTINUITY_DECISION_INVALID: shape")
    try:
        decision = ContinuityDecision(
            outcome=value["outcome"], reason=value["reason"],
            evidence=tuple(value["evidence"]), runnable=value["runnable"],
            schema_version=value["schema_version"],
        )
    except (KeyError, TypeError) as exc:
        raise ContinuityError("CONTINUITY_DECISION_INVALID: shape") from exc
    return validate_decision(decision)


def parse_context(value: str, *, allow_legacy: bool = False) -> ContinuityDecision:
    """Validate the compact Context carrier persisted in a handoff."""
    if not isinstance(value, str):
        raise ContinuityError("CONTINUITY_CONTEXT_INVALID")
    raw = value.strip().strip("`")
    if allow_legacy:
        raw = _LEGACY_CONTEXTS.get(raw, raw)
    outcome, separator, reason = raw.partition(":")
    outcome, reason = outcome.strip(), reason.strip()
    if outcome == "cold-start-root":
        if not separator or reason not in COLD_START_REASONS:
            raise ContinuityError("CONTINUITY_CONTEXT_INVALID: cold start requires one reason")
        return validate_decision(ContinuityDecision(
            outcome, reason, (f"persisted-context:{reason}",), True))
    if outcome == "terminal":
        if separator:
            raise ContinuityError("CONTINUITY_CONTEXT_INVALID: terminal has no suffix")
        return validate_decision(ContinuityDecision(
            outcome, "terminal-evidence", ("persisted-context:terminal",), False))
    if separator or outcome not in {"continue-root", "isolated-child-return"}:
        raise ContinuityError("CONTINUITY_CONTEXT_INVALID")
    return validate_decision(ContinuityDecision(
        outcome,
        "compatible-active-work" if outcome == "continue-root" else "independent-review",
        (f"persisted-context:{outcome}",),
        True,
    ))


def evaluate(*, route_attested: bool, context_attested: bool | None,
             batch_receipt_valid: bool, waiting_owner: bool = False,
             isolated_review: bool = False, boundary: str | None = None,
             checkpoint: str | None = None) -> ContinuityDecision:
    """Compatibility facade for callers predating ``WorkEstimate``."""
    if boundary is not None and boundary not in COLD_START_REASONS:
        raise ContinuityError("CONTINUITY_EVIDENCE_INVALID: cold-start reason")
    lifecycle = (
        boundary if boundary not in {"context-budget", "capability-missing"}
        else "active"
    ) or ("waiting-owner" if waiting_owner else "active")
    health = (
        "insufficient" if boundary == "context-budget"
        else "unavailable" if context_attested is None
        else "sufficient" if context_attested
        else "insufficient"
    )
    estimate = WorkEstimate(
        route_attested=route_attested,
        capabilities_attested=True,
        capabilities_sufficient=boundary != "capability-missing",
        context_attested=context_attested is not None,
        context_health=health,
        batch_receipt_valid=batch_receipt_valid,
        remaining_batch_digest="0" * 64,
        loaded_inputs_reusable=True,
        cold_start_cost=0,
        lifecycle=lifecycle,
        isolated_review=isolated_review,
        reviewer_task="compatibility-review" if isolated_review else None,
        checkpoint=checkpoint,
    )
    return reduce(estimate)
