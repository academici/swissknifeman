"""Provider failure classification (runtimes §4.9; port of legacy ``aicore/provider/errors.py``).

Rules are data (``error_rules.toml`` next to an adapter's ``capabilities.toml``,
``urn:skm:runtimes:error-rules:v1``) matched in file order against normalized signals; the first match for
the runtime wins. Process outcomes (cancel, timeout, stream incomplete, ...) are set by the adapter session
without rules: ``process_failure``.
Raw provider text is only compared, never copied into a failure.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, fields
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Final, Literal, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.json_types import JsonScalar

from .ids import is_runtime_id

if TYPE_CHECKING:
    from skm.kernel.json_types import JsonObject, JsonValue
    from skm.modules.runtimes.domain.ids import RuntimeId

__all__ = [
    "CANCEL_CODES",
    "CLASS_CODES",
    "DEFAULT_RETRYABLE",
    "DEFAULT_SAFE_MESSAGE",
    "ErrorClass",
    "ErrorRule",
    "ErrorScope",
    "ProcessOutcome",
    "ProviderFailure",
    "RuntimeSignals",
    "classify",
    "failure_from_json",
    "failure_to_json",
    "parse_error_rules",
    "process_failure",
]


class ErrorClass(StrEnum):
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    QUOTA = "quota"
    RATE_LIMIT = "rate_limit"
    INVALID_REQUEST = "invalid_request"
    MODEL_UNAVAILABLE = "model_unavailable"
    CONTENT_POLICY = "content_policy"
    TRANSPORT = "transport"
    PROVIDER_INTERNAL = "provider_internal"
    TIMEOUT = "timeout"
    CONTEXT_LIMIT = "context_limit"
    CRASH = "crash"
    CANCELLED = "cancelled"  # process outcomes only; no rule yields it
    UNKNOWN = "unknown"


class ErrorScope(StrEnum):
    REQUEST = "request"
    SESSION = "session"
    ACCOUNT = "account"
    PROVIDER = "provider"


# Legacy DEFAULT_RETRYABLE (errors.py:63-76) plus crash/cancelled. quota waits for retry_after and the
# decision of execution; context_limit is not helped by a repeat.
DEFAULT_RETRYABLE: Final[Mapping[ErrorClass, bool]] = MappingProxyType(
    {
        ErrorClass.AUTHENTICATION: False,
        ErrorClass.AUTHORIZATION: False,
        ErrorClass.QUOTA: False,
        ErrorClass.RATE_LIMIT: True,
        ErrorClass.INVALID_REQUEST: False,
        ErrorClass.MODEL_UNAVAILABLE: False,
        ErrorClass.CONTENT_POLICY: False,
        ErrorClass.TRANSPORT: True,
        ErrorClass.PROVIDER_INTERNAL: True,
        ErrorClass.TIMEOUT: True,
        ErrorClass.CONTEXT_LIMIT: False,
        ErrorClass.CRASH: True,
        ErrorClass.CANCELLED: False,
        ErrorClass.UNKNOWN: False,
    }
)

DEFAULT_SAFE_MESSAGE: Final[Mapping[ErrorClass, str]] = MappingProxyType(
    {
        ErrorClass.AUTHENTICATION: "provider rejected the credentials",
        ErrorClass.AUTHORIZATION: "provider denied the operation",
        ErrorClass.QUOTA: "provider quota exhausted",
        ErrorClass.RATE_LIMIT: "provider rate limit reached",
        ErrorClass.INVALID_REQUEST: "provider rejected the request",
        ErrorClass.MODEL_UNAVAILABLE: "model is not available",
        ErrorClass.CONTENT_POLICY: "request refused by provider policy",
        ErrorClass.TRANSPORT: "connection to the provider failed",
        ErrorClass.PROVIDER_INTERNAL: "provider-side failure",
        ErrorClass.TIMEOUT: "provider did not answer in time",
        ErrorClass.CONTEXT_LIMIT: "context limit reached",
        ErrorClass.CRASH: "runtime process failed",
        ErrorClass.CANCELLED: "session was cancelled",
        ErrorClass.UNKNOWN: "failure could not be classified",
    }
)

# Class -> v2 error code (§4.9 mapping table).
CLASS_CODES: Final[Mapping[ErrorClass, ErrorCode]] = MappingProxyType(
    {
        ErrorClass.AUTHENTICATION: ErrorCode.RUNTIME_AUTH_EXPIRED,
        ErrorClass.AUTHORIZATION: ErrorCode.RUNTIME_FORBIDDEN,
        ErrorClass.QUOTA: ErrorCode.QUOTA_EXHAUSTED,
        ErrorClass.RATE_LIMIT: ErrorCode.RATE_LIMITED,
        ErrorClass.INVALID_REQUEST: ErrorCode.RUNTIME_INVALID_REQUEST,
        ErrorClass.MODEL_UNAVAILABLE: ErrorCode.MODEL_UNAVAILABLE,
        ErrorClass.CONTENT_POLICY: ErrorCode.CONTENT_REFUSED,
        ErrorClass.TRANSPORT: ErrorCode.RUNTIME_TRANSPORT,
        ErrorClass.PROVIDER_INTERNAL: ErrorCode.RUNTIME_OVERLOADED,
        ErrorClass.TIMEOUT: ErrorCode.RUNTIME_TIMEOUT,
        ErrorClass.CONTEXT_LIMIT: ErrorCode.CONTEXT_OVERFLOW,
        ErrorClass.CRASH: ErrorCode.RUNTIME_CRASHED,
        ErrorClass.UNKNOWN: ErrorCode.RUNTIME_FAILURE_UNCLASSIFIED,
    }
)

CANCEL_CODES: Final = frozenset({ErrorCode.SESSION_CANCELLED, ErrorCode.CANCEL_IGNORED})

_TEXT_SIGNALS: Final = ("fatal_text", "stderr_tail")
_DETAIL_TEXT_MAX: Final = 500
_SAFE_MESSAGE_MAX: Final = 500


@dataclass(frozen=True, slots=True)
class RuntimeSignals:
    """Normalized signals of a failed session (legacy SIGNAL_TYPES, errors.py:29-32); all optional."""

    exit_code: int | None = None
    fatal_text: str | None = None
    stderr_tail: str | None = None
    is_error: bool | None = None
    http_status: int | None = None
    retry_category: str | None = None
    api_retries: int | None = None
    limit_status: str | None = None
    limit_window: str | None = None
    limit_resets_at: int | None = None
    terminal: bool | None = None

    def present(self) -> Mapping[str, JsonScalar]:
        return {
            item.name: getattr(self, item.name)
            for item in fields(self)
            if getattr(self, item.name) is not None
        }


_SIGNAL_TYPES: Final[Mapping[str, type]] = MappingProxyType(
    {
        "exit_code": int,
        "fatal_text": str,
        "stderr_tail": str,
        "is_error": bool,
        "http_status": int,
        "retry_category": str,
        "api_retries": int,
        "limit_status": str,
        "limit_window": str,
        "limit_resets_at": int,
        "terminal": bool,
    }
)


def _fold(text: str) -> str:
    """Case-insensitive form; the typographic apostrophe equals the ASCII one (legacy ``_fold``)."""
    return text.casefold().replace("\u2019", "'")


def _member(value: object, values: Sequence[object]) -> bool:
    """Membership keeping ``True`` apart from ``1`` (JSON booleans are not numbers here)."""
    return any(type(value) is type(item) and value == item for item in values)


@dataclass(frozen=True, slots=True)
class ErrorRule:
    runtime_id: RuntimeId
    error_class: ErrorClass
    code: ErrorCode
    scope: ErrorScope
    signal_any: Mapping[str, tuple[JsonScalar, ...]]  # every key present with one of the values
    signal_not_in: Mapping[str, tuple[JsonScalar, ...]]  # every key present with none of the values
    text_contains_any: tuple[str, ...]  # one marker in fatal_text or stderr_tail (casefold)
    retryable: bool | None
    safe_message: str | None
    retry_after_from: Literal["limit_resets_at"] | None

    def __post_init__(self) -> None:
        if not is_runtime_id(self.runtime_id):
            raise ValueError(f"not a runtime id: {self.runtime_id!r}")
        object.__setattr__(self, "error_class", ErrorClass(self.error_class))
        object.__setattr__(self, "code", ErrorCode(self.code))
        object.__setattr__(self, "scope", ErrorScope(self.scope))
        if self.error_class is ErrorClass.CANCELLED:
            raise ValueError("cancelled is a process outcome, not a rule class")
        for name in (*self.signal_any, *self.signal_not_in):
            if name not in _SIGNAL_TYPES:
                raise ValueError(f"unknown signal {name!r}")
        if not (self.signal_any or self.signal_not_in or self.text_contains_any):
            raise ValueError("a rule needs at least one condition")
        object.__setattr__(
            self, "text_contains_any", tuple(_fold(marker) for marker in self.text_contains_any)
        )
        object.__setattr__(self, "signal_any", MappingProxyType(dict(self.signal_any)))
        object.__setattr__(self, "signal_not_in", MappingProxyType(dict(self.signal_not_in)))

    @property
    def evidence(self) -> Literal["structured", "text"]:
        """``text`` when the rule rests on output text only, else ``structured``."""
        return (
            "text" if self.text_contains_any and not (self.signal_any or self.signal_not_in) else "structured"
        )

    def matches(self, signals: RuntimeSignals) -> bool:
        """Legacy ``ErrorRule.matches`` (errors.py:171-186): every condition must hold."""
        values = signals.present()
        if self.text_contains_any:
            # Each text signal on its own: a marker never spans the end of one and the start of the next.
            texts = [_fold(cast("str", values[name])) for name in _TEXT_SIGNALS if name in values]
            if not any(marker in text for marker in self.text_contains_any for text in texts):
                return False
        for name, allowed in self.signal_any.items():
            if name not in values or not _member(values[name], allowed):
                return False
        for name, refused in self.signal_not_in.items():
            # A value of the wrong type is not this signal: it neither passes nor fails the condition.
            if type(values.get(name)) is not _SIGNAL_TYPES[name] or _member(values[name], refused):
                return False
        return True


@dataclass(frozen=True, slots=True)
class ProviderFailure:
    error_class: ErrorClass
    code: ErrorCode
    retryable: bool
    safe_message: str
    retry_after_seconds: int | None
    scope: ErrorScope | None
    evidence: Literal["structured", "text", "process"]
    details: Mapping[str, JsonScalar] = field(default_factory=dict[str, JsonScalar])

    def __post_init__(self) -> None:
        object.__setattr__(self, "error_class", ErrorClass(self.error_class))
        object.__setattr__(self, "code", ErrorCode(self.code))
        if self.scope is not None:
            object.__setattr__(self, "scope", ErrorScope(self.scope))
        if not isinstance(self.retryable, bool):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError("retryable must be bool")
        if not isinstance(self.safe_message, str) or len(self.safe_message) > _SAFE_MESSAGE_MAX:  # pyright: ignore[reportUnnecessaryIsInstance]
            raise ValueError("safe_message must be a string of at most 500 characters")
        after = self.retry_after_seconds
        if after is not None and (isinstance(after, bool) or not isinstance(after, int) or after < 0):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise ValueError("retry_after_seconds must be a non-negative int or None")
        if self.evidence not in ("structured", "text", "process"):
            raise ValueError(f"unknown evidence {self.evidence!r}")
        if (self.error_class is ErrorClass.CANCELLED) != (self.code in CANCEL_CODES):
            raise ValueError("error class cancelled goes with exactly SESSION_CANCELLED or CANCEL_IGNORED")
        details: dict[str, JsonScalar] = {}
        for key, value in self.details.items():
            if isinstance(value, float):
                raise TypeError(f"details.{key}: floats are not safe details")
            if isinstance(value, str) and len(value) > _DETAIL_TEXT_MAX:
                raise ValueError(f"details.{key} exceeds 500 characters")
            details[key] = value
        object.__setattr__(self, "details", MappingProxyType(details))

    @property
    def cancelled(self) -> bool:
        return self.code in CANCEL_CODES


def classify(
    runtime_id: RuntimeId, signals: RuntimeSignals, rules: Sequence[ErrorRule], *, now_unix: int
) -> ProviderFailure:
    """The failure of the first rule of ``runtime_id`` matching ``signals`` (errors.py:215-241).

    Nothing matched: a non-zero exit code (negative: killed by a signal) is ``crash``, otherwise ``unknown``.
    A missing native terminal and an adapter timeout are process outcomes (``process_failure``), not this.
    """
    for rule in rules:
        if rule.runtime_id == runtime_id and rule.matches(signals):
            retry_after = None
            if rule.retry_after_from is not None and signals.limit_resets_at is not None:
                retry_after = max(0, signals.limit_resets_at - now_unix)
            return ProviderFailure(
                error_class=rule.error_class,
                code=rule.code,
                retryable=DEFAULT_RETRYABLE[rule.error_class] if rule.retryable is None else rule.retryable,
                safe_message=rule.safe_message or DEFAULT_SAFE_MESSAGE[rule.error_class],
                retry_after_seconds=retry_after,
                scope=rule.scope,
                evidence=rule.evidence,
                details={},
            )
    error_class = ErrorClass.CRASH if signals.exit_code not in (None, 0) else ErrorClass.UNKNOWN
    return ProviderFailure(
        error_class=error_class,
        code=CLASS_CODES[error_class],
        retryable=DEFAULT_RETRYABLE[error_class],
        safe_message=DEFAULT_SAFE_MESSAGE[error_class],
        retry_after_seconds=None,
        scope=None,
        evidence="process" if error_class is ErrorClass.CRASH else "structured",
        details={} if signals.exit_code is None else {"exit_code": signals.exit_code},
    )


class ProcessOutcome(StrEnum):
    """Process outcomes set by the adapter session without ``classify`` (§4.9 table; adapters add none)."""

    NOT_INSTALLED = "not_installed"
    CANCELLED = "cancelled"
    CANCEL_IGNORED = "cancel_ignored"
    WALL_TIMEOUT = "wall_timeout"
    STREAM_TOO_LARGE = "stream_too_large"
    CLEANUP_UNCONFIRMED = "cleanup_unconfirmed"
    STREAM_INCOMPLETE = "stream_incomplete"
    EMPTY_OUTPUT = "empty_output"


_PROCESS: Final[Mapping[ProcessOutcome, tuple[ErrorCode, ErrorClass, bool, ErrorScope, JsonObject]]] = (
    MappingProxyType(
        {
            ProcessOutcome.NOT_INSTALLED: (
                ErrorCode.RUNTIME_NOT_INSTALLED,
                ErrorClass.CRASH,
                False,
                ErrorScope.REQUEST,
                {},
            ),
            ProcessOutcome.CANCELLED: (
                ErrorCode.SESSION_CANCELLED,
                ErrorClass.CANCELLED,
                False,
                ErrorScope.SESSION,
                {},
            ),
            ProcessOutcome.CANCEL_IGNORED: (
                ErrorCode.CANCEL_IGNORED,
                ErrorClass.CANCELLED,
                False,
                ErrorScope.SESSION,
                {},
            ),
            ProcessOutcome.WALL_TIMEOUT: (
                ErrorCode.RUNTIME_TIMEOUT,
                ErrorClass.TIMEOUT,
                True,
                ErrorScope.SESSION,
                {"kind": "wall_timeout"},
            ),
            ProcessOutcome.STREAM_TOO_LARGE: (
                ErrorCode.RUNTIME_CRASHED,
                ErrorClass.CRASH,
                False,
                ErrorScope.SESSION,
                {"reason": "stream_too_large"},
            ),
            ProcessOutcome.CLEANUP_UNCONFIRMED: (
                ErrorCode.RUNTIME_CRASHED,
                ErrorClass.CRASH,
                False,
                ErrorScope.SESSION,
                {"reason": "cleanup_unconfirmed"},
            ),
            ProcessOutcome.STREAM_INCOMPLETE: (
                ErrorCode.RUNTIME_STREAM_INCOMPLETE,
                ErrorClass.TRANSPORT,
                True,
                ErrorScope.SESSION,
                {},
            ),
            ProcessOutcome.EMPTY_OUTPUT: (
                ErrorCode.RESULT_INVALID,
                ErrorClass.UNKNOWN,
                False,
                ErrorScope.REQUEST,
                {"reason": "empty_output"},
            ),
        }
    )
)


def process_failure(
    outcome: ProcessOutcome, *, details: Mapping[str, JsonScalar] | None = None
) -> ProviderFailure:
    """``evidence = process`` failure of one row of the §4.9 outcome table; ``details`` adds safe scalars
    (``exit_code``, ``last_event_type``) to the fixed ones."""
    code, error_class, retryable, scope, fixed = _PROCESS[ProcessOutcome(outcome)]
    merged: dict[str, JsonScalar] = {**cast("Mapping[str, JsonScalar]", fixed), **(details or {})}
    return ProviderFailure(
        error_class=error_class,
        code=code,
        retryable=retryable,
        safe_message=DEFAULT_SAFE_MESSAGE[error_class],
        retry_after_seconds=None,
        scope=scope,
        evidence="process",
        details=merged,
    )


def failure_to_json(failure: ProviderFailure) -> JsonObject:
    return {
        "error_class": failure.error_class.value,
        "code": failure.code.value,
        "retryable": failure.retryable,
        "safe_message": failure.safe_message,
        "retry_after_seconds": failure.retry_after_seconds,
        "scope": None if failure.scope is None else failure.scope.value,
        "evidence": failure.evidence,
        "details": dict(failure.details),
    }


def failure_from_json(data: Mapping[str, JsonValue]) -> ProviderFailure:
    scope = data["scope"]
    details = data.get("details") or {}
    if not isinstance(details, Mapping):
        raise TypeError("details must be an object")
    return ProviderFailure(
        error_class=ErrorClass(cast("str", data["error_class"])),
        code=ErrorCode(cast("str", data["code"])),
        retryable=cast("bool", data["retryable"]),
        safe_message=cast("str", data["safe_message"]),
        retry_after_seconds=cast("int | None", data["retry_after_seconds"]),
        scope=None if scope is None else ErrorScope(cast("str", scope)),
        evidence=cast("Literal['structured', 'text', 'process']", data["evidence"]),
        details=cast("Mapping[str, JsonScalar]", details),
    )


def _scalars(value: JsonValue, where: str) -> Mapping[str, tuple[JsonScalar, ...]]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{where} must be an object")
    result: dict[str, tuple[JsonScalar, ...]] = {}
    for name, items in value.items():
        if not isinstance(items, list):
            raise TypeError(f"{where}.{name} must be a list")
        result[name] = tuple(cast("list[JsonScalar]", items))
    return result


_CODE: Final = re.compile(r"[A-Z][A-Z0-9_]*")


def parse_error_rules(document: Mapping[str, JsonValue]) -> tuple[ErrorRule, ...]:
    """Rules of an ``urn:skm:runtimes:error-rules:v1`` document (already schema-valid), in file order."""
    rules = document["rules"]
    if not isinstance(rules, list):
        raise TypeError("rules must be a list")
    parsed: list[ErrorRule] = []
    for index, item in enumerate(rules):
        if not isinstance(item, Mapping):
            raise TypeError(f"rules[{index}] must be an object")
        code = item["code"]
        if not isinstance(code, str) or _CODE.fullmatch(code) is None:
            raise ValueError(f"rules[{index}].code must be an error code")
        markers = item["text_contains_any"]
        if not isinstance(markers, list) or not all(isinstance(marker, str) for marker in markers):
            raise TypeError(f"rules[{index}].text_contains_any must be a list of strings")
        retry_after = item["retry_after_from"]
        parsed.append(
            ErrorRule(
                runtime_id=cast("str", item["runtime_id"]),
                error_class=ErrorClass(cast("str", item["error_class"])),
                code=ErrorCode(code),
                scope=ErrorScope(cast("str", item["scope"])),
                signal_any=_scalars(item["signal_any"], f"rules[{index}].signal_any"),
                signal_not_in=_scalars(item["signal_not_in"], f"rules[{index}].signal_not_in"),
                text_contains_any=tuple(cast("list[str]", markers)),
                retryable=cast("bool | None", item["retryable"]),
                safe_message=cast("str | None", item["safe_message"]),
                retry_after_from=None if retry_after is None else "limit_resets_at",
            )
        )
    return tuple(parsed)
