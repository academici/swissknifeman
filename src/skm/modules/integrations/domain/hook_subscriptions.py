"""Hook subscriptions: data types, pure parser, matrix validator and routing helpers (§4.10, §5.8.1)."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Final, Literal, cast
from urllib.parse import urlsplit

from skm.kernel.json_types import JsonValue

from .contracts import ScopeLevel, SecretRef
from .hook_events import HookClass, HookEventKind

__all__ = [
    "Backoff",
    "CommandTarget",
    "EventSinkTarget",
    "ExecutionLocation",
    "FailurePolicy",
    "HookSubscription",
    "HookTarget",
    "RetrySpec",
    "SubscriptionKind",
    "Violation",
    "WebhookTarget",
    "effective_max_attempts",
    "matches",
    "next_attempt_at",
    "parse_subscriptions",
    "subscription_digest",
    "subscription_json",
    "validate_subscription",
]


class SubscriptionKind(StrEnum):
    WEBHOOK = "webhook"
    COMMAND = "command"
    EVENT_SINK = "event_sink"


class ExecutionLocation(StrEnum):
    CONTROL_PLANE = "control_plane"
    HOST = "host"


class FailurePolicy(StrEnum):
    DENY = "deny"
    WARN = "warn"
    RETRY = "retry"


@dataclass(frozen=True, slots=True)
class Backoff:
    initial_ms: int
    factor: float
    max_ms: int


@dataclass(frozen=True, slots=True)
class RetrySpec:
    max_attempts: int
    backoff: Backoff


@dataclass(frozen=True, slots=True)
class WebhookTarget:
    url: str
    secret: SecretRef
    previous_secret: SecretRef | None
    headers: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class CommandTarget:
    argv: tuple[str, ...]
    cwd: Literal["checkout", "state_dir"]
    env_allow: tuple[str, ...]
    env_refs: Mapping[str, SecretRef]


@dataclass(frozen=True, slots=True)
class EventSinkTarget:
    sink_id: str
    config: Mapping[str, JsonValue]


@dataclass(frozen=True, slots=True)
class HookSubscription:
    id: str
    enabled: bool
    hook_class: HookClass
    kind: SubscriptionKind
    execution_location: ExecutionLocation
    event_types: tuple[str, ...]
    target: HookTarget
    timeout_ms: int
    retry: RetrySpec
    failure_policy: FailurePolicy
    defined_at: ScopeLevel
    digest: str


type HookTarget = WebhookTarget | CommandTarget | EventSinkTarget


@dataclass(frozen=True, slots=True)
class Violation:
    """One defect of one subscription: ``key`` is ``hooks.subscriptions.<id>``, ``reason`` a stable code."""

    key: str
    reason: str
    message: str


@dataclass(frozen=True, slots=True)
class _Row:
    kinds: frozenset[SubscriptionKind]
    client_events: frozenset[str] | None  # None: domain events (control plane); {"*"}: any client event
    policies: tuple[FailurePolicy, ...]  # the first one is the default
    timeout_default_ms: int
    timeout_range_ms: tuple[int, int]


ID_PATTERN: Final = re.compile(r"[a-z0-9][a-z0-9_.-]{0,63}")
SECRET_REF_PATTERN: Final = re.compile(
    r"secret://(env/[A-Z_][A-Z0-9_]{0,127}|file/[^\s]{1,1024}|keyring/[A-Za-z0-9._-]{1,128}/[A-Za-z0-9._@-]{1,128})"
)
HEADER_NAME: Final = re.compile(r"[A-Za-z0-9-]{1,64}")
ENV_NAME: Final = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
DOMAIN_EXACT: Final = re.compile(r"urn:skm:[a-z][a-z0-9_-]*:event:[a-z0-9][a-z0-9._-]*:v[1-9][0-9]*")
DOMAIN_MODULE: Final = re.compile(r"urn:skm:[a-z][a-z0-9_-]*:event:\*")
CLIENT_PREFIX: Final = "client:"
FORBIDDEN_HEADERS: Final = ("authorization", "host")
FORBIDDEN_HEADER_PREFIXES: Final = ("content-", "skm-")
LOOPBACK_HOSTS: Final = frozenset({"localhost", "127.0.0.1", "::1"})
MAX_EVENT_TYPES: Final = 32
MAX_HEADERS: Final = 16
MAX_ARGV: Final = 64
MAX_ENV_ALLOW: Final = 32
HOST_TIMEOUT_CEILING_MS: Final = (
    10_000  # schema maximum of integrations.hook.timeout_ms; runtime value may be lower
)
DEFAULT_RETRY: Final = RetrySpec(5, Backoff(1000, 2.0, 300_000))
RETRY_LIMITS: Final = {"max_attempts": (1, 20), "initial_ms": (100, 600_000), "factor": (1.0, 10.0)}
MAX_BACKOFF_MS: Final = 86_400_000

_PLANE_POLICIES = (FailurePolicy.DENY, FailurePolicy.RETRY, FailurePolicy.WARN)
_WEBHOOK_SINK = frozenset({SubscriptionKind.WEBHOOK, SubscriptionKind.EVENT_SINK})
MATRIX: Final[Mapping[tuple[HookClass, ExecutionLocation], _Row]] = {
    (HookClass.ENFORCEMENT, ExecutionLocation.HOST): _Row(
        frozenset({SubscriptionKind.COMMAND}),
        frozenset({"pre_shell", "pre_tool", "user_prompt", "permission_request", "stop"}),
        (FailurePolicy.DENY, FailurePolicy.WARN),
        1000,
        (50, HOST_TIMEOUT_CEILING_MS),
    ),
    (HookClass.WORKFLOW, ExecutionLocation.CONTROL_PLANE): _Row(
        _WEBHOOK_SINK, None, _PLANE_POLICIES, 5000, (100, 30_000)
    ),
    (HookClass.WORKFLOW, ExecutionLocation.HOST): _Row(
        frozenset({SubscriptionKind.COMMAND}),
        frozenset({"session_start", "subagent_stop", "stop", "post_tool"}),
        (FailurePolicy.WARN,),
        1000,
        (50, HOST_TIMEOUT_CEILING_MS),
    ),
    (HookClass.OBSERVATION, ExecutionLocation.CONTROL_PLANE): _Row(
        _WEBHOOK_SINK, None, (FailurePolicy.RETRY, FailurePolicy.WARN), 5000, (100, 30_000)
    ),
    (HookClass.OBSERVATION, ExecutionLocation.HOST): _Row(
        frozenset({SubscriptionKind.COMMAND}),
        frozenset({"*"}),
        (FailurePolicy.WARN, FailurePolicy.RETRY),
        1000,
        (50, HOST_TIMEOUT_CEILING_MS),
    ),
}


class _Malformed(Exception):
    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _enum[E: StrEnum](kind: type[E], value: object, name: str) -> E:
    try:
        return kind(value)
    except ValueError:
        allowed = ", ".join(member.value for member in kind)
        raise _Malformed(f"invalid_{name}", f"{name} {value!r} is not one of {allowed}") from None


def _mapping(value: object, name: str) -> Mapping[str, JsonValue]:
    if not isinstance(value, Mapping):
        raise _Malformed("invalid_shape", f"{name} must be an object")
    return cast("Mapping[str, JsonValue]", value)


def _strings(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in cast("list[object]", value)):
        raise _Malformed("invalid_shape", f"{name} must be an array of strings")
    return tuple(cast("list[str]", value))


def _secret(value: object, name: str) -> SecretRef:
    if not isinstance(value, str) or SECRET_REF_PATTERN.fullmatch(value) is None:
        raise _Malformed("secret_ref_required", f"{name} must be a secret:// reference, not a literal")
    return value


def _closed(fields: Mapping[str, JsonValue], allowed: frozenset[str], name: str) -> None:
    unknown = sorted(set(fields) - allowed)
    if unknown:
        raise _Malformed("invalid_shape", f"{name} has unknown fields {unknown}")


def _webhook(target: Mapping[str, JsonValue]) -> WebhookTarget:
    _closed(target, frozenset({"url", "secret", "previous_secret", "headers"}), "target")
    url = target.get("url")
    if not isinstance(url, str):
        raise _Malformed("invalid_shape", "target.url must be a string")
    try:
        parsed = urlsplit(url)
        if parsed.port == 0:
            raise ValueError
    except ValueError:
        raise _Malformed("webhook_url_invalid", "target.url must have a valid host and port") from None
    if "secret" not in target:
        raise _Malformed("secret_ref_required", "target.secret is required")
    previous = target.get("previous_secret")
    headers = _mapping(target.get("headers", {}), "target.headers")
    if not all(isinstance(item, str) for item in headers.values()):
        raise _Malformed("invalid_shape", "target.headers values must be strings")
    return WebhookTarget(
        url=url,
        secret=_secret(target["secret"], "target.secret"),
        previous_secret=None if previous is None else _secret(previous, "target.previous_secret"),
        headers=dict(cast("Mapping[str, str]", headers)),
    )


def _command(target: Mapping[str, JsonValue]) -> CommandTarget:
    _closed(target, frozenset({"argv", "cwd", "env_allow", "env_refs"}), "target")
    if "argv" not in target:
        raise _Malformed("invalid_shape", "target.argv is required")
    cwd = target.get("cwd", "checkout")
    if cwd not in ("checkout", "state_dir"):
        raise _Malformed("invalid_cwd", f"target.cwd {cwd!r} is not checkout or state_dir")
    refs = _mapping(target.get("env_refs", {}), "target.env_refs")
    return CommandTarget(
        argv=_strings(target["argv"], "target.argv"),
        cwd=cwd,
        env_allow=_strings(target.get("env_allow", []), "target.env_allow"),
        env_refs={name: _secret(ref, f"target.env_refs.{name}") for name, ref in refs.items()},
    )


def _sink(target: Mapping[str, JsonValue]) -> EventSinkTarget:
    _closed(target, frozenset({"sink_id", "config"}), "target")
    sink_id = target.get("sink_id")
    if not isinstance(sink_id, str):
        raise _Malformed("invalid_shape", "target.sink_id must be a string")
    return EventSinkTarget(sink_id=sink_id, config=dict(_mapping(target.get("config", {}), "target.config")))


def _retry(value: object) -> RetrySpec:
    fields = _mapping(value, "retry")
    _closed(fields, frozenset({"max_attempts", "backoff"}), "retry")
    backoff = _mapping(fields.get("backoff", {}), "retry.backoff")
    _closed(backoff, frozenset({"initial_ms", "factor", "max_ms"}), "retry.backoff")
    attempts = fields.get("max_attempts", DEFAULT_RETRY.max_attempts)
    initial = backoff.get("initial_ms", DEFAULT_RETRY.backoff.initial_ms)
    factor = backoff.get("factor", DEFAULT_RETRY.backoff.factor)
    maximum = backoff.get("max_ms", DEFAULT_RETRY.backoff.max_ms)
    if not (_is_int(attempts) and _is_int(initial) and _is_int(maximum)):
        raise _Malformed("invalid_shape", "retry counts and delays must be integers")
    if isinstance(factor, bool) or not isinstance(factor, int | float):
        raise _Malformed("invalid_shape", "retry.backoff.factor must be a number")
    return RetrySpec(
        cast("int", attempts), Backoff(cast("int", initial), float(factor), cast("int", maximum))
    )


def subscription_json(sub: HookSubscription) -> dict[str, JsonValue]:
    """Normalized config form of a subscription (defaults filled in), without ``id`` and ``defined_at``."""
    target = sub.target
    if isinstance(target, WebhookTarget):
        target_json: dict[str, JsonValue] = {
            "url": target.url,
            "secret": target.secret,
            "previous_secret": target.previous_secret,
            "headers": dict(target.headers),
        }
    elif isinstance(target, CommandTarget):
        target_json = {
            "argv": list(target.argv),
            "cwd": target.cwd,
            "env_allow": list(target.env_allow),
            "env_refs": dict(target.env_refs),
        }
    else:
        target_json = {"sink_id": target.sink_id, "config": dict(target.config)}
    return {
        "enabled": sub.enabled,
        "class": sub.hook_class.value,
        "kind": sub.kind.value,
        "execution_location": sub.execution_location.value,
        "event_types": list(sub.event_types),
        "target": target_json,
        "timeout_ms": sub.timeout_ms,
        "retry": {
            "max_attempts": sub.retry.max_attempts,
            "backoff": {
                "initial_ms": sub.retry.backoff.initial_ms,
                "factor": sub.retry.backoff.factor,
                "max_ms": sub.retry.backoff.max_ms,
            },
        },
        "failure_policy": sub.failure_policy.value,
    }


def subscription_digest(sub_json: Mapping[str, JsonValue]) -> str:
    """``sha256:`` + hex of the canonical JSON without ``enabled``; secret references enter as their text."""
    body = {name: value for name, value in sub_json.items() if name != "enabled"}
    text = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _parse_one(sub_id: str, entry: object, defined_at: ScopeLevel) -> HookSubscription:
    if ID_PATTERN.fullmatch(sub_id) is None:
        raise _Malformed("invalid_id", "subscription id must match ^[a-z0-9][a-z0-9_.-]{0,63}$")
    fields = _mapping(entry, "subscription")
    _closed(
        fields,
        frozenset(
            {"id", "enabled", "class", "kind", "execution_location", "event_types", "target", "timeout_ms"}
            | {"retry", "failure_policy"}
        ),
        "subscription",
    )
    for required in ("class", "kind", "execution_location", "event_types", "target"):
        if required not in fields:
            raise _Malformed("invalid_shape", f"{required} is required")
    enabled = fields.get("enabled", True)
    if not isinstance(enabled, bool):
        raise _Malformed("invalid_shape", "enabled must be a boolean")
    hook_class = _enum(HookClass, fields["class"], "class")
    kind = _enum(SubscriptionKind, fields["kind"], "kind")
    location = _enum(ExecutionLocation, fields["execution_location"], "execution_location")
    row = MATRIX.get((hook_class, location))
    timeout = fields.get("timeout_ms", row.timeout_default_ms if row else 1000)
    if not _is_int(timeout):
        raise _Malformed("invalid_shape", "timeout_ms must be an integer")
    policy = _enum(
        FailurePolicy,
        fields["failure_policy"] if "failure_policy" in fields else row.policies[0] if row else "warn",
        "failure_policy",
    )
    target = _mapping(fields["target"], "target")
    parsed_target: HookTarget = (
        _webhook(target)
        if kind is SubscriptionKind.WEBHOOK
        else _command(target)
        if kind is SubscriptionKind.COMMAND
        else _sink(target)
    )
    draft = HookSubscription(
        id=sub_id,
        enabled=enabled,
        hook_class=hook_class,
        kind=kind,
        execution_location=location,
        event_types=_strings(fields["event_types"], "event_types"),
        target=parsed_target,
        timeout_ms=cast("int", timeout),
        retry=_retry(fields["retry"]) if "retry" in fields else DEFAULT_RETRY,
        failure_policy=policy,
        defined_at=defined_at,
        digest="",
    )
    return _with_digest(draft)


def _with_digest(sub: HookSubscription) -> HookSubscription:
    return replace(sub, digest=subscription_digest(subscription_json(sub)))


def parse_subscriptions(
    value: Mapping[str, JsonValue], provenance: Mapping[str, ScopeLevel]
) -> tuple[tuple[HookSubscription, ...], tuple[Violation, ...]]:
    """Typed subscriptions by id and the defects of malformed entries (those are left out).

    ``provenance`` maps an id to the most specific level that contributed it; an unlisted id is ``instance``.
    """
    found: list[HookSubscription] = []
    violations: list[Violation] = []
    for sub_id in sorted(value):
        key = f"hooks.subscriptions.{sub_id}"
        try:
            found.append(_parse_one(sub_id, value[sub_id], provenance.get(sub_id, "instance")))
        except _Malformed as exc:
            violations.append(Violation(key, exc.reason, exc.message))
    return tuple(found), tuple(violations)


def _pattern_violation(
    pattern: str, location: ExecutionLocation, row: _Row, hookable_types: frozenset[str]
) -> tuple[str, str] | None:
    """``(reason, message)`` when one ``event_types`` entry is not allowed for the row, else ``None``."""
    if pattern.startswith(CLIENT_PREFIX):
        if location is not ExecutionLocation.HOST:
            return "client_event_requires_host", f"{pattern!r}: client events exist only on the host"
        name = pattern.removeprefix(CLIENT_PREFIX)
        if name != "*" and name not in {kind.value for kind in HookEventKind}:
            return "unknown_client_event", f"{pattern!r} is not a client event"
        allowed = row.client_events or frozenset()
        if "*" not in allowed and name not in allowed:
            return "event_type_not_allowed", f"{pattern!r} is not allowed for this class"
        return None
    if location is ExecutionLocation.HOST:
        return "event_type_not_allowed", f"{pattern!r}: a host subscription takes client:* events only"
    if DOMAIN_EXACT.fullmatch(pattern):
        known = pattern in hookable_types
    elif DOMAIN_MODULE.fullmatch(pattern):
        prefix = pattern.removesuffix("*")
        known = any(item.startswith(prefix) for item in hookable_types)
    else:
        return "invalid_event_pattern", f"{pattern!r} is not an event type pattern"
    return None if known else ("unknown_event_type", f"{pattern!r} matches no hookable event type")


def _argv_violations(argv: tuple[str, ...]) -> list[tuple[str, str]]:
    if not 1 <= len(argv) <= MAX_ARGV:
        return [("argv_invalid", f"argv needs 1..{MAX_ARGV} elements")]
    if not argv[0] or ("/" in argv[0] and not argv[0].startswith("/")):
        return [("argv_invalid", "argv[0] must be an absolute path or a bare PATH executable name")]
    return []


def _target_violations(sub: HookSubscription, sink_ids: frozenset[str]) -> list[tuple[str, str]]:
    target = sub.target
    found: list[tuple[str, str]] = []
    if isinstance(target, WebhookTarget):
        try:
            host = urlsplit(target.url).hostname or ""
        except ValueError:
            host = ""
        if target.url.startswith("http://"):
            if host not in LOOPBACK_HOSTS:
                found.append(("webhook_url_scheme", "http:// is allowed for loopback addresses only"))
        elif not target.url.startswith("https://") or not host:
            found.append(("webhook_url_scheme", "target.url must be an https:// URL"))
        if len(target.headers) > MAX_HEADERS:
            found.append(("headers_invalid", f"at most {MAX_HEADERS} headers"))
        for name in target.headers:
            lowered = name.lower()
            if (
                HEADER_NAME.fullmatch(name) is None
                or lowered in FORBIDDEN_HEADERS
                or lowered.startswith(FORBIDDEN_HEADER_PREFIXES)
            ):
                found.append(("headers_invalid", f"header {name!r} is not allowed"))
    elif isinstance(target, CommandTarget):
        found.extend(_argv_violations(target.argv))
        if len(target.env_allow) > MAX_ENV_ALLOW or not all(ENV_NAME.fullmatch(n) for n in target.env_allow):
            found.append(("env_invalid", f"env_allow takes at most {MAX_ENV_ALLOW} variable names"))
        if not all(ENV_NAME.fullmatch(name) for name in target.env_refs):
            found.append(("env_invalid", "env_refs names must be variable names"))
    else:
        if target.sink_id == "webhook":
            found.append(("sink_id_webhook", "sink_id 'webhook' is reserved for kind=webhook"))
        elif target.sink_id not in sink_ids:
            found.append(("sink_not_registered", f"sink {target.sink_id!r} is not registered"))
    return found


def _retry_violations(retry: RetrySpec) -> list[tuple[str, str]]:
    backoff = retry.backoff
    low, high = RETRY_LIMITS["max_attempts"]
    problems: list[str] = []
    if not low <= retry.max_attempts <= high:
        problems.append(f"max_attempts must be {int(low)}..{int(high)}")
    low, high = RETRY_LIMITS["initial_ms"]
    if not low <= backoff.initial_ms <= high:
        problems.append(f"backoff.initial_ms must be {int(low)}..{int(high)}")
    low, high = RETRY_LIMITS["factor"]
    if not low <= backoff.factor <= high:
        problems.append(f"backoff.factor must be {low}..{high}")
    if not backoff.initial_ms <= backoff.max_ms <= MAX_BACKOFF_MS:
        problems.append(f"backoff.max_ms must be initial_ms..{MAX_BACKOFF_MS}")
    return [("retry_out_of_range", text) for text in problems]


def validate_subscription(
    sub: HookSubscription, *, hookable_types: frozenset[str], sink_ids: frozenset[str]
) -> tuple[Violation, ...]:
    """Every defect of ``sub`` against the §4.10 matrix; the two sets are the known event types and sinks."""
    key = f"hooks.subscriptions.{sub.id}"
    found: list[tuple[str, str]] = []
    if (sub.execution_location is ExecutionLocation.HOST) != (sub.kind is SubscriptionKind.COMMAND):
        found.append(("location_kind_mismatch", "execution_location=host if and only if kind=command"))
    row = MATRIX.get((sub.hook_class, sub.execution_location))
    if row is None:
        found.append(
            (
                "class_location_not_allowed",
                f"class {sub.hook_class.value} cannot run at {sub.execution_location.value}",
            )
        )
    else:
        if sub.kind not in row.kinds:
            found.append(
                ("kind_not_allowed", f"kind {sub.kind.value} is not allowed for this class and location")
            )
        if sub.failure_policy not in row.policies:
            allowed = ", ".join(policy.value for policy in row.policies)
            found.append(("failure_policy_not_allowed", f"failure_policy must be one of {allowed}"))
        low, high = row.timeout_range_ms
        if not low <= sub.timeout_ms <= high:
            found.append(("timeout_out_of_range", f"timeout_ms must be {low}..{high}"))
        for pattern in sub.event_types:
            problem = _pattern_violation(pattern, sub.execution_location, row, hookable_types)
            if problem is not None:
                found.append(problem)
    if not 1 <= len(sub.event_types) <= MAX_EVENT_TYPES:
        found.append(("event_types_count", f"event_types needs 1..{MAX_EVENT_TYPES} patterns"))
    expected_target = {
        SubscriptionKind.WEBHOOK: WebhookTarget,
        SubscriptionKind.COMMAND: CommandTarget,
        SubscriptionKind.EVENT_SINK: EventSinkTarget,
    }[sub.kind]
    if isinstance(cast("object", sub.target), expected_target):
        found.extend(_target_violations(sub, sink_ids))
    else:
        found.append(("target_kind_mismatch", f"target does not describe kind {sub.kind.value}"))
    found.extend(_retry_violations(sub.retry))
    return tuple(Violation(key, reason, message) for reason, message in found)


_CLIENT_KINDS: Final = frozenset(kind.value for kind in HookEventKind)


def matches(sub: HookSubscription, event_type: str) -> bool:
    """Whether ``event_type`` matches a §5.8.1 pattern of ``sub`` (never mixing client and domain)."""
    if event_type.startswith(CLIENT_PREFIX):
        if event_type.removeprefix(CLIENT_PREFIX) not in _CLIENT_KINDS:
            return False
        return any(pattern in (event_type, "client:*") for pattern in sub.event_types)
    if DOMAIN_EXACT.fullmatch(event_type) is None:
        return False
    return any(
        pattern == event_type
        or (DOMAIN_MODULE.fullmatch(pattern) is not None and event_type.startswith(pattern[:-1]))
        for pattern in sub.event_types
    )


def effective_max_attempts(sub: HookSubscription) -> int:
    """``failure_policy=warn`` runs once; otherwise ``retry.max_attempts`` (§4.10)."""
    return 1 if sub.failure_policy is FailurePolicy.WARN else sub.retry.max_attempts


def next_attempt_at(
    retry: RetrySpec, *, attempt: int, now: datetime, jitter: float, retry_after_ms: int | None = None
) -> datetime:
    """Exponential backoff with ``jitter`` in ``[0.8, 1.2]``, capped by ``max_ms`` and ``retry_after_ms``."""
    if attempt < 1:
        raise ValueError("attempt must be >= 1")
    if not math.isfinite(jitter) or not 0.8 <= jitter <= 1.2:
        raise ValueError("jitter must be within [0.8, 1.2]")
    ceiling = float(retry.backoff.max_ms)
    base = min(ceiling, retry.backoff.initial_ms * math.pow(retry.backoff.factor, min(attempt - 1, 64)))
    delay_ms = min(ceiling, base * jitter)
    if retry_after_ms is not None:
        delay_ms = min(ceiling, max(delay_ms, float(max(retry_after_ms, 0))))
    return now + timedelta(milliseconds=delay_ms)
