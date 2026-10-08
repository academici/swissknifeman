"""Normalized provider failures (the ``error/v1`` contract) and rule-based classification.

Classification is data-driven: the rules live in ``configs/provider-errors.json`` and match provider and
output text; no consumer carries its own text markers. The raw provider text is never copied into a
record. This module neither waits nor repeats anything: retry policy belongs to the run engine.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import functools
import json
from pathlib import Path
import re
from typing import Optional, Sequence

from .data import config_path

RULES_FILE = "provider-errors.json"
RULES_SCHEMA_VERSION = "provider-errors/v1"
_CODE_RE = re.compile(r"[A-Z][A-Z0-9_]*")
_PROVIDER_RE = re.compile(r"[a-z][a-z0-9-]*")


class ErrorClass(str, Enum):
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
    UNKNOWN = "unknown"


class ErrorScope(str, Enum):
    REQUEST = "request"
    SESSION = "session"
    ACCOUNT = "account"
    PROVIDER = "provider"


# A repeat can help only for failures that are transient on the provider side. quota is False on purpose:
# it can be retried only after retry_after_s, and the run policy decides that. context_limit is False:
# neither a repeat nor another provider helps, the plan has to change.
DEFAULT_RETRYABLE = {
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
    ErrorClass.UNKNOWN: False,
}

DEFAULT_SAFE_MESSAGE = {
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
    ErrorClass.UNKNOWN: "failure could not be classified",
}


@dataclass(frozen=True)
class ProviderError:
    """One normalized failure; ``to_dict`` is a valid ``error/v1`` document."""

    error_class: ErrorClass
    code: str
    retryable: bool
    safe_message: str
    retry_after_s: Optional[int] = None
    scope: Optional[ErrorScope] = None
    provider: Optional[str] = None
    request_id: Optional[str] = None
    diagnostic_ref: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.error_class, ErrorClass):
            raise TypeError("error_class must be ErrorClass")
        if not isinstance(self.code, str) or not _CODE_RE.fullmatch(self.code):
            raise ValueError("code must be an upper-case identifier")
        if not isinstance(self.retryable, bool):
            raise TypeError("retryable must be bool")
        _require_text(self.safe_message, "safe_message")
        if self.retry_after_s is not None and (
                isinstance(self.retry_after_s, bool) or not isinstance(self.retry_after_s, int)):
            raise TypeError("retry_after_s must be an integer")
        if self.scope is not None and not isinstance(self.scope, ErrorScope):
            raise TypeError("scope must be ErrorScope")
        if self.provider is not None and (
                not isinstance(self.provider, str) or not _PROVIDER_RE.fullmatch(self.provider)):
            raise ValueError("provider must be a provider id")
        for label in ("request_id", "diagnostic_ref"):
            if getattr(self, label) is not None:
                _require_text(getattr(self, label), label)

    def to_dict(self) -> dict:
        value = {"class": self.error_class.value, "code": self.code, "retryable": self.retryable,
                 "safe_message": self.safe_message}
        if self.retry_after_s is not None:
            value["retry_after_s"] = self.retry_after_s
        if self.scope is not None:
            value["scope"] = self.scope.value
        for label in ("provider", "request_id", "diagnostic_ref"):
            if getattr(self, label) is not None:
                value[label] = getattr(self, label)
        return value


@dataclass(frozen=True)
class ErrorRule:
    """One classification rule; a rule matches when every condition of ``match`` holds."""

    provider: str
    error_class: ErrorClass
    code: str
    text_contains_any: tuple = ()
    exit_code_any: tuple = ()
    scope: Optional[ErrorScope] = None
    safe_message: Optional[str] = None
    retryable: Optional[bool] = None

    def matches(self, text: str, exit_code: Optional[int]) -> bool:
        if self.text_contains_any:
            lowered = text.lower()
            if not any(marker in lowered for marker in self.text_contains_any):
                return False
        if self.exit_code_any and exit_code not in self.exit_code_any:
            return False
        return True


def default_rules_path() -> Path:
    return config_path(RULES_FILE)


def load_error_rules(path: Optional[Path] = None) -> tuple:
    """Load and validate the classification rules; ``None`` reads the packaged file."""
    if path is None:
        return _default_rules()
    return _parse_rules(Path(path))


@functools.lru_cache(maxsize=1)
def _default_rules() -> tuple:
    return _parse_rules(default_rules_path())


def classify_failure(provider_id: str, *, text: str = "", exit_code: Optional[int] = None,
                     rules: Optional[Sequence[ErrorRule]] = None) -> Optional[ProviderError]:
    """Return the failure of the first rule that matches, or ``None`` when no rule does.

    The caller decides what an unclassified failure means. ``text`` is only compared, never copied.
    """
    if not isinstance(text, str):
        raise TypeError("text must be str")
    active = load_error_rules() if rules is None else tuple(rules)
    for rule in active:
        if rule.provider == provider_id and rule.matches(text, exit_code):
            return ProviderError(
                error_class=rule.error_class, code=rule.code,
                retryable=DEFAULT_RETRYABLE[rule.error_class] if rule.retryable is None else rule.retryable,
                safe_message=rule.safe_message or DEFAULT_SAFE_MESSAGE[rule.error_class],
                scope=rule.scope, provider=rule.provider)
    return None


def _parse_rules(path: Path) -> tuple:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"{path.name}: cannot load: {exc}") from exc
    _require_keys(doc, {"schema_version", "rules"}, {"schema_version", "rules"}, path.name)
    if doc["schema_version"] != RULES_SCHEMA_VERSION:
        raise ValueError(f"{path.name}: schema_version must be {RULES_SCHEMA_VERSION}")
    if not isinstance(doc["rules"], list):
        raise ValueError(f"{path.name}: rules must be a list")
    return tuple(_parse_rule(item, f"{path.name}: rules[{index}]") for index, item in enumerate(doc["rules"]))


def _parse_rule(item: object, where: str) -> ErrorRule:
    _require_keys(item, {"provider", "class", "code", "match"},
                  {"provider", "class", "code", "match", "scope", "safe_message", "retryable"}, where)
    match = item["match"]
    _require_keys(match, set(), {"text_contains_any", "exit_code_any"}, f"{where}.match")
    if not match:
        raise ValueError(f"{where}.match: needs at least one condition")
    markers = _list_of(match.get("text_contains_any", ()), str, f"{where}.match.text_contains_any")
    codes = _list_of(match.get("exit_code_any", ()), int, f"{where}.match.exit_code_any")
    if any(not marker for marker in markers):
        raise ValueError(f"{where}.match.text_contains_any: markers must not be empty")
    try:
        error_class = ErrorClass(item["class"])
        scope = ErrorScope(item["scope"]) if "scope" in item else None
    except ValueError as exc:
        raise ValueError(f"{where}: {exc}") from exc
    if not isinstance(item["provider"], str) or not _PROVIDER_RE.fullmatch(item["provider"]):
        raise ValueError(f"{where}.provider: must be a provider id")
    if not isinstance(item["code"], str) or not _CODE_RE.fullmatch(item["code"]):
        raise ValueError(f"{where}.code: must be an upper-case identifier")
    if "safe_message" in item:
        _require_text(item["safe_message"], f"{where}.safe_message")
    if "retryable" in item and not isinstance(item["retryable"], bool):
        raise ValueError(f"{where}.retryable: must be a boolean")
    return ErrorRule(provider=item["provider"], error_class=error_class, code=item["code"],
                     text_contains_any=tuple(marker.lower() for marker in markers),
                     exit_code_any=tuple(codes), scope=scope, safe_message=item.get("safe_message"),
                     retryable=item.get("retryable"))


def _require_keys(value: object, required: set, allowed: set, where: str) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{where}: must be an object")
    missing, unknown = required - set(value), set(value) - allowed
    if missing or unknown:
        raise ValueError(f"{where}: missing {sorted(missing)}, unknown {sorted(unknown)}")


def _list_of(value: object, kind: type, where: str) -> list:
    if not isinstance(value, (list, tuple)) or not all(
            isinstance(item, kind) and not isinstance(item, bool) for item in value):
        raise ValueError(f"{where}: must be a list of {kind.__name__}")
    return list(value)


def _require_text(value: object, label: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
