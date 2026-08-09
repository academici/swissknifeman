"""Deterministic, fail-closed authority resolution for executable plans.

The module implements the frozen P5.1 decision-request and P5.2 authority-frame
contracts.  It intentionally has no model or network client: callers supply a
typed request, while this module validates the frame, derives the predicates, and
returns one of the closed verdicts.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


FRAME_ENV = "TASK_AUTHORITY_FRAME"
FRAME_RELATIVE_PATH = "packages/task/configs/authority-frame.json"
KIND_VALUES = ("clarification", "authorization")
VERDICT_VALUES = ("delegated", "approval_required", "denied")
AUTO_ANSWER_CLASSES = {
    "plan_carrier": "plan",
    "repository_config": "repository_config",
    "frozen_contract": "frozen_contract",
    "git_revision": "git",
}
REQUIRED_PREDICATES = (
    "within_declared_scope",
    "no_frozen_contract_change",
    "no_closed_set_extension",
    "reversible",
    "decision_recorded",
)


class AuthorityFrameError(ValueError):
    """An absent or malformed authority instance; never a delegation default."""


class AuthorityRequestError(ValueError):
    """A malformed request which resolves to a structured denial at the boundary."""


@dataclass(frozen=True)
class Verdict:
    """The only policy outcome exposed to adapters; deliberately not a bool."""

    verdict: str
    reason_code: str
    policy_digest: str | None
    material_fields: tuple[str, ...] = ()
    affected_surfaces: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.verdict not in VERDICT_VALUES:
            raise ValueError(f"unknown authority verdict {self.verdict!r}")


class CommitmentStore:
    """Item-lifetime aggregation for previously delegated requests.

    Persistence belongs to P5.4.  P5.3 keeps this small in-memory representation
    so every adapter can supply the same prior commitments deterministically.
    """

    def __init__(self) -> None:
        self._commitments: dict[tuple[str, str, str], list[dict[str, Any]]] = {}

    def for_request(self, request: dict[str, Any]) -> list[dict[str, Any]]:
        return list(self._commitments.get(_aggregation_key(request), ()))

    def record(self, request: dict[str, Any], verdict: Verdict) -> None:
        if verdict.verdict != "delegated":
            return
        self._commitments.setdefault(_aggregation_key(request), []).append(
            _commitment(request))


class ResponseStore:
    """Single-use response registry. Durable storage is intentionally P5.4."""

    def __init__(self) -> None:
        self._used: set[tuple[str, int, str]] = set()

    def use(self, decision_id: str, action_version: int, action_digest: str) -> bool:
        key = (decision_id, action_version, action_digest)
        if key in self._used:
            return False
        self._used.add(key)
        return True


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def default_frame_path() -> Path:
    return Path(os.environ.get(FRAME_ENV, _repo_root() / FRAME_RELATIVE_PATH))


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def load_frame(path: str | Path | None = None) -> dict[str, Any]:
    """Load and validate the owner-authored instance, with no literal fallback."""
    frame_path = Path(path) if path is not None else default_frame_path()
    try:
        raw = frame_path.read_bytes()
    except OSError as exc:
        raise AuthorityFrameError(f"authority-frame не найден: {frame_path}") from exc
    try:
        frame = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AuthorityFrameError(f"authority-frame invalid JSON: {frame_path}: {exc.msg}") from exc
    if not isinstance(frame, dict) or frame.get("version") != "authority-frame-v1":
        raise AuthorityFrameError(f"authority-frame invalid version: {frame_path}")
    if frame.get("default") != "reserved" or not isinstance(frame.get("decision_classes"), dict):
        raise AuthorityFrameError(f"authority-frame invalid deny-by-default form: {frame_path}")
    aggregation = frame.get("aggregation")
    if not isinstance(aggregation, dict) or aggregation.get("key") != [
            "plan_id", "item_id", "decision_class"]:
        raise AuthorityFrameError(f"authority-frame invalid aggregation: {frame_path}")
    for name, definition in frame["decision_classes"].items():
        if not isinstance(name, str) or not isinstance(definition, dict):
            raise AuthorityFrameError(f"authority-frame invalid decision class: {frame_path}")
        required = {"material_fields", "verdict", "action_class", "attention", "on_timeout"}
        if not required.issubset(definition) or definition["verdict"] not in ("delegated", "reserved"):
            raise AuthorityFrameError(f"authority-frame incomplete class {name!r}: {frame_path}")
    frame["_policy_digest"] = hashlib.sha256(raw).hexdigest()
    return frame


def policy_digest(frame: dict[str, Any]) -> str:
    digest = frame.get("_policy_digest")
    if not isinstance(digest, str):
        raise AuthorityFrameError("authority-frame has no pinned policy digest")
    return digest


def classify(request: dict[str, Any]) -> str:
    """Classify the canonical intent; facts that imply an action become approval."""
    kind = request.get("kind")
    if kind not in KIND_VALUES:
        raise AuthorityRequestError("P5_DECISION_UNCLASSIFIED_KIND")
    action = request.get("action")
    if isinstance(action, dict) and action.get("requires_authorization") is True:
        return "authorization"
    conditions = action.get("requires_authorization_when") if isinstance(action, dict) else None
    if isinstance(conditions, dict) and any(action.get(field) == value
                                            for field, value in conditions.items()):
        return "authorization"
    return kind


def canonical_action(request: dict[str, Any], frame: dict[str, Any]) -> dict[str, Any]:
    """Reconstruct the frozen material tuple; callers never supply its authority."""
    subject = request.get("subject")
    continuation = request.get("continuation")
    if not isinstance(subject, dict) or not isinstance(continuation, dict):
        raise AuthorityRequestError("P5_DECISION_REJECTED")
    target = continuation.get("target")
    capabilities = continuation.get("capabilities")
    if not isinstance(target, dict) or not isinstance(capabilities, dict):
        raise AuthorityRequestError("P5_DECISION_REJECTED")
    required_subject = ("plan_id", "phase_id", "item_id")
    if any(not isinstance(subject.get(key), str) or not subject[key] for key in required_subject):
        raise AuthorityRequestError("P5_DECISION_REJECTED")
    for name in ("action", "options", "default_option"):
        if name not in request:
            raise AuthorityRequestError("P5_DECISION_REJECTED")
    return {
        "contract_version": "v1",
        "kind": classify(request),
        "decision_class": request.get("decision_class"),
        "subject": subject,
        "action": request["action"],
        "options": request["options"],
        "default_option": request["default_option"],
        "continuation.target": target,
        "continuation.capabilities": capabilities,
        "policy_digest": policy_digest(frame),
    }


def action_digest(request: dict[str, Any], frame: dict[str, Any]) -> str:
    return _sha256(canonical_action(request, frame))


def _aggregation_key(request: dict[str, Any]) -> tuple[str, str, str]:
    subject = request.get("subject") or {}
    return (str(subject.get("plan_id", "")), str(subject.get("item_id", "")),
            str(request.get("decision_class", "")))


def _action(request: dict[str, Any]) -> dict[str, Any]:
    action = request.get("action")
    if not isinstance(action, dict):
        raise AuthorityRequestError("P5_DECISION_REJECTED")
    return action


def _surfaces(action: dict[str, Any]) -> set[str]:
    surfaces = action.get("affected_surfaces")
    if not isinstance(surfaces, list) or not all(isinstance(value, str) and value for value in surfaces):
        raise AuthorityRequestError("P5_DECISION_REJECTED")
    return set(surfaces)


def _commitment(request: dict[str, Any]) -> dict[str, Any]:
    action = _action(request)
    return {
        "affected_surfaces": sorted(_surfaces(action)),
        "declared_scope": sorted(set(action.get("declared_scope", ()))),
    }


def _constructive_predicates(request: dict[str, Any], commitments: list[dict[str, Any]]) -> tuple[bool, set[str]]:
    action = _action(request)
    surfaces = _surfaces(action)
    declared_scope = action.get("declared_scope")
    if not isinstance(declared_scope, list) or not all(isinstance(value, str) and value for value in declared_scope):
        raise AuthorityRequestError("P5_DECISION_REJECTED")
    prior_surfaces: set[str] = set()
    scope = set(declared_scope)
    for previous in commitments:
        prior_surfaces.update(previous["affected_surfaces"])
        # The first committed scope is the item-lifetime envelope. A later request
        # cannot widen it by naming another one.
        scope &= set(previous["declared_scope"])
    predicates = {
        "within_declared_scope": (surfaces | prior_surfaces).issubset(scope),
        "no_frozen_contract_change": action.get("frozen_contract_change") is False,
        "no_closed_set_extension": action.get("closed_set_extension") is False,
        "reversible": action.get("reversible") is True,
        "decision_recorded": action.get("decision_recorded") is True,
    }
    return all(predicates[name] for name in REQUIRED_PREDICATES), surfaces | prior_surfaces


def evaluate(request: dict[str, Any], *, frame: dict[str, Any] | None = None,
             commitments: list[dict[str, Any]] | None = None) -> Verdict:
    """Evaluate a request without committing it. Every error returns non-delegated."""
    try:
        active = frame if frame is not None else load_frame()
        expected_digest = policy_digest(active)
        if request.get("policy_digest") not in (None, expected_digest):
            return Verdict("denied", "P5_DECISION_POLICY_ERROR", expected_digest)
        decision_class = request.get("decision_class")
        definition = active["decision_classes"].get(decision_class)
        request_kind = classify(request)
        if request_kind not in KIND_VALUES or not isinstance(definition, dict):
            return Verdict("denied", "P5_DECISION_UNCLASSIFIED_KIND", expected_digest)
        canonical_action(request, active)
        # A raw clarification is never authorization.  Only the closed,
        # provenance-carrying auto-answer path below may supply its missing fact.
        if request_kind == "clarification":
            return Verdict("approval_required", "P5_DECISION_ESCALATED", expected_digest)
        if definition["verdict"] != "delegated":
            return Verdict("approval_required", "P5_DECISION_ESCALATED", expected_digest)
        if decision_class != "constructive":
            return Verdict("denied", "P5_DECISION_POLICY_ERROR", expected_digest)
        allowed, surfaces = _constructive_predicates(request, commitments or [])
        if not allowed:
            return Verdict("approval_required", "P5_DECISION_ESCALATED", expected_digest,
                           affected_surfaces=tuple(sorted(surfaces)))
        return Verdict("delegated", "P5_DECISION_POLICY_APPROVED", expected_digest,
                       material_fields=tuple(definition["material_fields"]),
                       affected_surfaces=tuple(sorted(surfaces)))
    except (AuthorityFrameError, AuthorityRequestError, KeyError, TypeError, ValueError):
        return Verdict("denied", "P5_DECISION_POLICY_ERROR", None)


def authorize(request: dict[str, Any], *, store: CommitmentStore | None = None,
              frame: dict[str, Any] | None = None, shadow: bool = False) -> Verdict | dict[str, Any]:
    """The mandatory adapter boundary.  Only this function records delegation."""
    commitments = store.for_request(request) if store is not None else []
    verdict = evaluate(request, frame=frame, commitments=commitments)
    if shadow:
        return {"enforced": False, "would_verdict": verdict.verdict,
                "reason_code": verdict.reason_code, "policy_digest": verdict.policy_digest}
    if store is not None:
        store.record(request, verdict)
    return verdict


def auto_answer_clarification(request: dict[str, Any], *, question_class: str,
                              field: str, sources: dict[str, dict[str, Any]],
                              frame: dict[str, Any] | None = None) -> dict[str, Any] | Verdict:
    """Resolve an allowlisted fact and force a fresh classification afterwards."""
    active = frame if frame is not None else load_frame()
    if classify(request) != "clarification" or question_class not in AUTO_ANSWER_CLASSES:
        return Verdict("approval_required", "P5_DECISION_ESCALATED", policy_digest(active))
    missing = request.get("missing_fields")
    source = sources.get(question_class)
    if not isinstance(missing, list) or field not in missing or not isinstance(source, dict):
        return Verdict("approval_required", "P5_DECISION_ESCALATED", policy_digest(active))
    required = ("value", "record_id", "record_version")
    if any(not source.get(name) for name in required):
        return Verdict("approval_required", "P5_DECISION_ESCALATED", policy_digest(active))
    before = action_digest(request, active)
    updated = copy.deepcopy(request)
    updated.setdefault("action", {})[field] = source["value"]
    updated["missing_fields"] = [name for name in missing if name != field]
    reclassified_to = classify(updated)
    after = action_digest(updated, active)
    return {
        "request": updated,
        "response": {
            "decision_id": request.get("decision_id"), "action_version": request.get("action_version"),
            "selected_option": "apply", "resolver": "policy",
            "resolver_id": f"{AUTO_ANSWER_CLASSES[question_class]}:{question_class}",
            "policy_digest": policy_digest(active), "action_digest": after,
            "reason_code": "P5_DECISION_AUTO_CLARIFIED", "reclassified_to": reclassified_to,
            "provenance": {"source_system": AUTO_ANSWER_CLASSES[question_class],
                           "record_id": source["record_id"], "record_version": source["record_version"],
                           "verified": True}, "at": source.get("at", "deterministic"),
        },
        "event": {"decision_id": request.get("decision_id"), "question_class": question_class,
                  "resolver_id": f"{AUTO_ANSWER_CLASSES[question_class]}:{question_class}",
                  "source_system": AUTO_ANSWER_CLASSES[question_class],
                  "source_record_id": source["record_id"], "source_record_version": source["record_version"],
                  "before_digest": before, "after_digest": after, "provenance_verified": True,
                  "policy_digest": policy_digest(active), "reclassified_action_digest": after,
                  "reclassified_to": reclassified_to},
    }


def apply_response(request: dict[str, Any], response: dict[str, Any], *,
                   store: ResponseStore | None = None, frame: dict[str, Any] | None = None) -> Verdict | dict[str, Any]:
    """Apply exactly one response only when its current bytes and policy still match."""
    active = frame if frame is not None else load_frame()
    try:
        current_digest = action_digest(request, active)
    except (AuthorityRequestError, AuthorityFrameError):
        return Verdict("denied", "P5_DECISION_POLICY_ERROR", None)
    if response.get("policy_digest") != policy_digest(active):
        return Verdict("denied", "P5_DECISION_POLICY_ERROR", policy_digest(active))
    option_ids = {option.get("id") for option in request.get("options", ())
                  if isinstance(option, dict)}
    if response.get("selected_option") not in option_ids:
        return Verdict("denied", "P5_DECISION_UNKNOWN_OPTION", policy_digest(active))
    if response.get("action_digest") != current_digest:
        updated = copy.deepcopy(request)
        updated["action_version"] = int(request.get("action_version", 0)) + 1
        updated["action_digest"] = current_digest
        return {"verdict": Verdict("denied", "P5_DECISION_DIGEST_MISMATCH", policy_digest(active)),
                "new_request": updated}
    if classify(request) == "clarification":
        provenance = response.get("provenance")
        if response.get("reclassified_to") not in KIND_VALUES or not isinstance(provenance, dict) or \
                provenance.get("verified") is not True:
            return Verdict("denied", "P5_DECISION_RECLASSIFICATION_REQUIRED", policy_digest(active))
    decision_id = request.get("decision_id")
    version = request.get("action_version")
    if not isinstance(decision_id, str) or not isinstance(version, int):
        return Verdict("denied", "P5_DECISION_REJECTED", policy_digest(active))
    registry = store if store is not None else ResponseStore()
    if not registry.use(decision_id, version, current_digest):
        return Verdict("denied", "P5_DECISION_RESPONSE_REUSED", policy_digest(active))
    return {"verdict": "applied", "action_digest": current_digest,
            "reclassified_to": response.get("reclassified_to")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Детерминированный резолвер полномочий P5")
    parser.add_argument("--shadow", action="store_true", help="записать would-verdict без принуждения")
    args = parser.parse_args(argv)
    try:
        request = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(f"P5_DECISION_POLICY_ERROR: invalid JSON: {exc.msg}", file=sys.stderr)
        return 2
    result = authorize(request, shadow=args.shadow)
    print(json.dumps(result.__dict__ if isinstance(result, Verdict) else result,
                     ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
