"""Tool intents: the proposal of an external effect and its life cycle (policy §4.6, §5.12).

``normalize_args`` is the one place that decides what an intent binds: the normalized arguments are the
digest input, so an approval is valid for exactly these arguments and for none other (``args_json`` binds
the candidate, the transport, host, port, path and ref). Arguments that must never be approved by anyone
(``force``, ``+refspec``, ref deletion, ``--mirror``) make ``propose`` return an intent that is already
``denied(forbidden_args)``. The digest is ``sha256:`` over the canonical JSON of ``{"kind", "args"}``; the
serialization is the one of ``platform.jsonc`` (domain code may not import ``platform``, a test pins both).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import timedelta
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Final, Literal, cast
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed, ValidationFailed

if TYPE_CHECKING:
    from datetime import datetime

    from skm.kernel.ids import PrincipalId, ScopeId, ToolIntentId, WorkspaceId
    from skm.kernel.json_types import JsonObject, JsonValue
    from skm.modules.policy.domain.permission_set import PermissionSet

__all__ = [
    "ACTIVE_STATES",
    "INTENT_TRANSITIONS",
    "OUTCOME_STATES",
    "DecisionSource",
    "DeniedReason",
    "EffectKind",
    "EnforcementMode",
    "ForbiddenArgs",
    "IntentOutcome",
    "IntentState",
    "RiskClass",
    "ToolDecisionRecord",
    "ToolIntent",
    "args_digest",
    "deny",
    "expire",
    "normalize_args",
    "propose",
    "transition_intent",
]


class EffectKind(StrEnum):
    GIT_COMMIT = "git_commit"
    GIT_PUSH = "git_push"
    PR_CREATE = "pr_create"
    MESSAGE = "message"
    PUBLISH = "publish"
    FS_WRITE_EXTERNAL = "fs_write_external"


class EnforcementMode(StrEnum):
    AGENT_UNATTENDED = "agent_unattended"
    INTERACTIVE = "interactive"


class RiskClass(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IntentState(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"
    EXECUTING = "executing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    OUTCOME_UNKNOWN = "outcome_unknown"


class DeniedReason(StrEnum):
    NOT_PERMITTED = "not_permitted"
    FORBIDDEN_ARGS = "forbidden_args"
    BY_APPROVER = "by_approver"
    REVOKED = "revoked"


class DecisionSource(StrEnum):
    HOOK = "hook"
    WORKER = "worker"


@dataclass(frozen=True, slots=True)
class ToolIntent:
    id: ToolIntentId
    workspace_id: WorkspaceId
    scope_id: ScopeId
    subject_ref: str
    actor_id: PrincipalId
    kind: EffectKind
    normalized_args: Mapping[str, JsonValue]
    args_digest: str
    risk: RiskClass
    reason: str
    state: IntentState
    denied_reason: str | None
    created_at: datetime
    expires_at: datetime
    row_version: int
    receipt: Mapping[str, JsonValue] | None = (
        None  # outcome receipt (DDL ``receipt``), set by ``record_outcome``
    )


@dataclass(frozen=True, slots=True)
class ToolDecisionRecord:
    """One decision of a hook or a worker: a ``decision_audit`` row (append-only, policy §11)."""

    id: UUID
    workspace_id: WorkspaceId | None
    scope_id: ScopeId
    principal_id: PrincipalId
    source: DecisionSource
    at: datetime
    tool: str
    call_summary: str
    outcome: str
    code: str | None
    rule: str | None
    operation: str | None
    recorded_at: datetime


class ForbiddenArgs(ValueError):
    """The arguments name an effect nobody may approve (``denied(forbidden_args)``)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# ------------------------------------------------------------------------------------------ transitions
INTENT_TRANSITIONS: Final[Mapping[IntentState, frozenset[IntentState]]] = MappingProxyType(
    {
        IntentState.PROPOSED: frozenset({IntentState.APPROVED, IntentState.DENIED, IntentState.EXPIRED}),
        IntentState.APPROVED: frozenset({IntentState.DENIED, IntentState.EXPIRED, IntentState.EXECUTING}),
        IntentState.EXECUTING: frozenset(
            {IntentState.SUCCEEDED, IntentState.FAILED, IntentState.OUTCOME_UNKNOWN}
        ),
        IntentState.OUTCOME_UNKNOWN: frozenset({IntentState.SUCCEEDED, IntentState.FAILED}),
        IntentState.DENIED: frozenset(),
        IntentState.EXPIRED: frozenset(),
        IntentState.SUCCEEDED: frozenset(),
        IntentState.FAILED: frozenset(),
    }
)
ACTIVE_STATES: Final = frozenset({IntentState.PROPOSED, IntentState.APPROVED, IntentState.EXECUTING})
type IntentOutcome = Literal["succeeded", "failed", "outcome_unknown"]
# The states an executed intent resolves to, each with the outcome its IntentResolved event reports.
OUTCOME_STATES: Final[Mapping[IntentState, IntentOutcome]] = MappingProxyType(
    {
        IntentState.SUCCEEDED: "succeeded",
        IntentState.FAILED: "failed",
        IntentState.OUTCOME_UNKNOWN: "outcome_unknown",
    }
)


def transition_intent(
    intent: ToolIntent,
    to: IntentState,
    *,
    denied_reason: DeniedReason | None = None,
    receipt: Mapping[str, JsonValue] | None = None,
) -> ToolIntent:
    """The intent in state ``to`` with ``row_version + 1``; a move outside the table: ``INVALID_TRANSITION``.

    ``denied_reason`` is required for ``denied`` and refused for every other state (the DDL check).
    """
    source, target = IntentState(intent.state), IntentState(to)
    if target not in INTENT_TRANSITIONS[source]:
        raise PreconditionFailed(
            ErrorCode.INVALID_TRANSITION,
            f"a {source.value} intent cannot become {target.value}",
            details={"kind": "tool_intent", "from": source.value, "to": target.value},
        )
    if (target is IntentState.DENIED) != (denied_reason is not None):
        raise ValueError("denied_reason belongs to the denied state and to no other")
    return replace(
        intent,
        state=target,
        denied_reason=None if denied_reason is None else DeniedReason(denied_reason).value,
        receipt=intent.receipt if receipt is None else receipt,
        row_version=intent.row_version + 1,
    )


def deny(intent: ToolIntent, reason: DeniedReason) -> ToolIntent:
    return transition_intent(intent, IntentState.DENIED, denied_reason=reason)


def expire(intent: ToolIntent) -> ToolIntent:
    return transition_intent(intent, IntentState.EXPIRED)


# ------------------------------------------------------------------------------------------ digest
def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False)


def args_digest(kind: EffectKind, args: Mapping[str, JsonValue]) -> str:
    """``sha256:`` of the canonical JSON ``{"kind": kind, "args": args}``."""
    document = {"kind": EffectKind(kind).value, "args": dict(args)}
    return "sha256:" + hashlib.sha256(_canonical(document).encode("utf-8")).hexdigest()


# ------------------------------------------------------------------------------------------ normalization
_UUID: Final = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_DIGEST: Final = re.compile(r"sha256:[0-9a-f]{64}")
_SHA: Final = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
_HEAD: Final = re.compile(r"refs/heads/[^\s:~^?*\[\\]+")
_MAX_PORT: Final = 65535
_ABSOLUTE_FILE: Final = re.compile(
    r"^/(?:(?!\.{1,2}(?:/|$))[^/\x00-\x1f\x7f]+/)*(?!\.{1,2}$)[^/\x00-\x1f\x7f]+$"
)

type _Check = Callable[[object], JsonValue]


def _invalid(path: str, problem: str) -> ValidationFailed:
    return ValidationFailed(
        ErrorCode.SCHEMA_INVALID,
        f"intent arguments are invalid: {path} {problem}",
        details={"field": path, "reason": problem},
    )


def _text(path: str) -> _Check:
    def check(value: object) -> JsonValue:
        if not isinstance(value, str):
            raise _invalid(path, "must be a string")
        return value

    return check


def _external_path(value: object) -> JsonValue:
    if not isinstance(value, str) or _ABSOLUTE_FILE.fullmatch(value) is None:
        raise _invalid("path", "must be a canonical absolute POSIX file path")
    return value


def _uuid(path: str) -> _Check:
    def check(value: object) -> JsonValue:
        if isinstance(value, UUID):  # a typed caller; JSON carries text
            return str(value)
        if not isinstance(value, str) or _UUID.fullmatch(value.lower()) is None:
            raise _invalid(path, "must be a UUID")
        return str(UUID(value))

    return check


def _digest(path: str) -> _Check:
    def check(value: object) -> JsonValue:
        if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
            raise _invalid(path, "must be a sha256 digest")
        return value

    return check


def _sha(path: str) -> _Check:
    def check(value: object) -> JsonValue:
        if not isinstance(value, str) or _SHA.fullmatch(value) is None:
            raise _invalid(path, "must be a full commit sha")
        return value

    return check


def _branch(path: str) -> _Check:
    def check(value: object) -> JsonValue:
        if not isinstance(value, str) or _HEAD.fullmatch(value) is None:
            raise _invalid(path, "must be a full refs/heads/ name")
        return value

    return check


def _port(path: str) -> _Check:
    def check(value: object) -> JsonValue:
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= _MAX_PORT:
            raise _invalid(path, "must be a port number")
        return value

    return check


def _object(path: str, fields: Mapping[str, _Check]) -> _Check:
    def check(value: object) -> JsonValue:
        return _fields(path, value, fields)

    return check


def _fields(path: str, value: object, fields: Mapping[str, _Check]) -> dict[str, JsonValue]:
    if not isinstance(value, Mapping):
        raise _invalid(path or "args", "must be an object")
    document = cast("Mapping[str, object]", value)
    prefix = f"{path}." if path else ""
    unknown = sorted(set(document) - set(fields))
    if unknown:
        raise _invalid(f"{prefix}{unknown[0]}", "is not a known argument")
    missing = [name for name in fields if name not in document]
    if missing:
        raise _invalid(f"{prefix}{missing[0]}", "is required")
    return {name: check(document[name]) for name, check in fields.items()}


def _strings(path: str) -> Callable[[object], list[str]]:
    def check(value: object) -> list[str]:
        if not isinstance(value, list) or not all(
            isinstance(item, str) for item in cast("list[object]", value)
        ):
            raise _invalid(path, "must be a list of strings")
        return list(cast("list[str]", value))

    return check


_ENDPOINT: Final = {
    "transport": _text("endpoint.transport"),
    "hostname": _text("endpoint.hostname"),
    "effective_port": _port("endpoint.effective_port"),
    "repository_path": _text("endpoint.repository_path"),
}
_BINDING: Final = {
    "binding_id": _uuid("binding_identity.binding_id"),
    "host_id": _uuid("binding_identity.host_id"),
    "repository_id": _uuid("binding_identity.repository_id"),
    "locator_digest": _digest("binding_identity.locator_digest"),
}
_SHAPES: Final[Mapping[EffectKind, Mapping[str, _Check]]] = MappingProxyType(
    {
        EffectKind.GIT_COMMIT: {
            "repository_id": _uuid("repository_id"),
            "branch": _branch("branch"),
            "parent_commit": _sha("parent_commit"),
            "tree_digest": _digest("tree_digest"),
        },
        EffectKind.GIT_PUSH: {
            "repository_id": _uuid("repository_id"),
            "remote": _text("remote"),
            "endpoint": _object("endpoint", _ENDPOINT),
            "binding_identity": _object("binding_identity", _BINDING),
            "target_ref": _branch("target_ref"),
            "before_sha": _sha("before_sha"),
            "after_sha": _sha("after_sha"),
        },
        EffectKind.PR_CREATE: {
            "repository_id": _uuid("repository_id"),
            "endpoint": _object("endpoint", _ENDPOINT),
            "binding_identity": _object("binding_identity", _BINDING),
            "base": _text("base"),
            "head": _text("head"),
            "title_digest": _digest("title_digest"),
            "body_digest": _digest("body_digest"),
        },
        EffectKind.MESSAGE: {
            "channel": _text("channel"),
            "body_digest": _digest("body_digest"),
        },
        EffectKind.PUBLISH: {
            "target": _text("target"),
            "artifact_digest": _digest("artifact_digest"),
            "version": _text("version"),
        },
        EffectKind.FS_WRITE_EXTERNAL: {
            "host_id": _uuid("host_id"),
            "path": _external_path,
            "content_digest": _digest("content_digest"),
        },
    }
)
_PUSH_FIELDS: Final = frozenset({*_SHAPES[EffectKind.GIT_PUSH], "refspecs", "force"})


def _plain(value: object) -> JsonValue:
    """A deep, JSON-only copy: the intent keeps no reference to a caller's mutable value."""
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in cast("Mapping[object, object]", value).items()}
    if isinstance(value, list | tuple):
        return [_plain(item) for item in cast("list[object]", value)]
    if value is None or isinstance(value, bool | int | float | str):
        return value
    raise _invalid("args", "holds a value that is not JSON")


def _forbidden_push(raw: Mapping[str, object]) -> str | None:
    if raw.get("force") not in (None, False):
        return "force_push"
    if raw.get("mirror") not in (None, False):
        return "mirror_push"
    refspecs = raw.get("refspecs")
    if isinstance(refspecs, list):
        for item in cast("list[object]", refspecs):
            if not isinstance(item, str):
                continue
            if item.startswith("--mirror") or item == "--mirror":
                return "mirror_push"
            if item.startswith("+"):
                return "force_refspec"
            source, separator, target = item.partition(":")
            if separator and not source:
                return "ref_deletion"
            if target.startswith("+"):
                return "force_refspec"
    return None


def forbidden_reason(kind: EffectKind, raw: Mapping[str, object]) -> str | None:
    """Why ``raw`` can never be approved; ``None``: nothing forbidden (a bad shape is another question)."""
    return _forbidden_push(raw) if EffectKind(kind) is EffectKind.GIT_PUSH else None


def _refspecs(value: object) -> list[JsonValue]:
    items = _strings("refspecs")(value)
    if not items:
        raise _invalid("refspecs", "needs at least one refspec")
    for item in items:
        source, separator, target = item.partition(":")
        if not separator or _HEAD.fullmatch(source) is None or _HEAD.fullmatch(target) is None:
            raise _invalid("refspecs", "holds a refspec that is not a full refs/heads/ src:dst pair")
    return cast("list[JsonValue]", sorted(set(items)))


def normalize_args(kind: EffectKind, raw: Mapping[str, object]) -> Mapping[str, JsonValue]:
    """The arguments an approval binds, by the schema ``intent-args-<kind>``.

    ``ForbiddenArgs`` for an effect nobody may approve; ``SCHEMA_INVALID`` for an unknown or missing field or
    a value of the wrong shape. The output is canonical: lists sorted, UUIDs lowercase, nothing added.
    """
    kind = EffectKind(kind)
    if not isinstance(raw, Mapping):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise _invalid("args", "must be an object")
    reason = forbidden_reason(kind, raw)
    if reason is not None:
        raise ForbiddenArgs(reason)
    shape = dict(_SHAPES[kind])
    if kind is EffectKind.GIT_PUSH:
        unknown = sorted(set(raw) - _PUSH_FIELDS)
        if unknown:
            raise _invalid(unknown[0], "is not a known argument")
        for name in ("refspecs", "force"):
            if name not in raw:
                raise _invalid(name, "is required")
        body = _fields("", {name: raw[name] for name in shape if name in raw}, shape)
        body["refspecs"] = _refspecs(raw["refspecs"])
        body["force"] = False
        return dict(sorted(body.items()))
    if kind is EffectKind.MESSAGE:
        if "recipients" not in raw:
            raise _invalid("recipients", "is required")
        known = {name: raw[name] for name in raw if name != "recipients"}
        body = _fields("", known, shape)
        body["recipients"] = cast("list[JsonValue]", sorted(set(_strings("recipients")(raw["recipients"]))))
        return dict(sorted(body.items()))
    return dict(sorted(_fields("", raw, shape).items()))


# ------------------------------------------------------------------------------------------ propose
def propose(  # noqa: PLR0913 -- the identity of the intent is data, not behavior
    kind: EffectKind,
    raw_args: Mapping[str, object],
    perms: PermissionSet,
    now: datetime,
    ttl: timedelta,
    *,
    intent_id: ToolIntentId,
    workspace_id: WorkspaceId,
    scope_id: ScopeId,
    subject_ref: str,
    actor_id: PrincipalId,
    risk: RiskClass,
    reason: str,
    mode: EnforcementMode = EnforcementMode.INTERACTIVE,
) -> ToolIntent:
    """A new intent: ``proposed``, or already ``denied`` when its kind or its arguments are not allowed.

    ``forbidden_args`` wins over ``not_permitted`` (it is the property of the arguments, whatever the ceiling
    says). A denied intent keeps the arguments as they were asked for, so the refusal can be shown.
    """
    kind = EffectKind(kind)
    denied: DeniedReason | None = None
    try:
        arguments = normalize_args(kind, raw_args)
    except ForbiddenArgs:
        arguments = cast("Mapping[str, JsonValue]", _plain(raw_args))
        denied = DeniedReason.FORBIDDEN_ARGS
    if denied is None and (
        kind not in perms.external_effects
        or (kind is EffectKind.FS_WRITE_EXTERNAL and mode is EnforcementMode.AGENT_UNATTENDED)
    ):
        denied = DeniedReason.NOT_PERMITTED
    if ttl <= timedelta(0):
        raise ValueError("an intent lives for a positive time")
    return ToolIntent(
        id=intent_id,
        workspace_id=workspace_id,
        scope_id=scope_id,
        subject_ref=subject_ref,
        actor_id=actor_id,
        kind=kind,
        normalized_args=arguments,
        args_digest=args_digest(kind, arguments),
        risk=RiskClass(risk),
        reason=reason,
        state=IntentState.PROPOSED if denied is None else IntentState.DENIED,
        denied_reason=None if denied is None else denied.value,
        created_at=now,
        expires_at=now + ttl,
        row_version=1,
    )


def plain_args(args: Mapping[str, object]) -> JsonObject:
    """``args`` as a plain JSON object (a deep copy)."""
    return cast("JsonObject", _plain(args))
