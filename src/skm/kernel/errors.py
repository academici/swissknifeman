"""Structured errors (kernel-platform §2.6).

Every error carries a catalog ``code``, a human ``message`` and JSON-only ``details``.
A cause is attached with the standard ``raise ... from cause``. Messages and details must not contain secrets.
``details`` accepts only
JSON values, so arbitrary objects (and their ``repr``) never reach logs or problem documents.
"""

import copy
import math
from collections.abc import Mapping
from types import MappingProxyType
from typing import ClassVar, cast, override

from .error_codes import CATALOG, ErrorCategory, ErrorCode
from .json_types import JsonObject, JsonValue

__all__ = [
    "BackendUnavailable",
    "CapabilityUnavailable",
    "Conflict",
    "Forbidden",
    "InternalError",
    "NotFound",
    "OutcomeUnknown",
    "PreconditionFailed",
    "SkmError",
    "Unauthenticated",
    "ValidationFailed",
    "error_for",
]


def _check_json(value: object, path: str) -> None:
    if value is None or isinstance(value, bool | int | str):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError(f"{path}: non-finite float is not JSON")
        return
    if isinstance(value, list):
        for index, item in enumerate(cast("list[object]", value)):
            _check_json(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in cast("dict[object, object]", value).items():
            if not isinstance(key, str):
                raise TypeError(f"{path}: object keys must be strings")
            _check_json(item, f"{path}.{key}")
        return
    raise TypeError(f"{path}: {type(value).__name__} is not a JSON value")


class SkmError(Exception):
    """Base of all SKM errors. Use a category subclass (or ``error_for``); the base itself is abstract."""

    category: ClassVar[ErrorCategory]

    code: ErrorCode
    message: str
    details: Mapping[str, JsonValue]
    retryable: bool

    @override
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        details: Mapping[str, JsonValue] | None = None,
        retryable: bool | None = None,
    ) -> None:
        declared = getattr(type(self), "category", None)
        if declared is None:
            raise TypeError(f"{type(self).__name__} has no error category; use a subclass or error_for()")
        info = CATALOG[ErrorCode(code)]
        if info.category is not declared:
            raise TypeError(
                f"{info.code} belongs to category {info.category.value!r}, not {declared.value!r} "
                f"({type(self).__name__})"
            )
        copied: dict[str, JsonValue] = {}
        if details is not None:
            _check_json(dict(details), "details")
            copied = copy.deepcopy(dict(details))
        super().__init__(info.code, message)
        self.code = info.code
        self.message = message
        self.details = MappingProxyType(copied)
        self.retryable = info.retryable if retryable is None else retryable

    @override
    def __str__(self) -> str:
        return f"{self.code}: {self.message}"

    def to_problem(self) -> JsonObject:
        """The wire form ``{"code", "message", "details", "retryable"}``; ``details`` is a fresh copy."""
        return {
            "code": self.code.value,
            "message": self.message,
            "details": copy.deepcopy(dict(self.details)),
            "retryable": self.retryable,
        }

    def add_secondary(self, note: str) -> None:
        """Record a secondary failure (cleanup, rollback) without losing the primary error."""
        self.add_note(note)


class NotFound(SkmError):
    category = ErrorCategory.NOT_FOUND


class ValidationFailed(SkmError):
    category = ErrorCategory.VALIDATION


class Conflict(SkmError):
    category = ErrorCategory.CONFLICT


class PreconditionFailed(SkmError):
    category = ErrorCategory.PRECONDITION


class Forbidden(SkmError):
    category = ErrorCategory.FORBIDDEN


class Unauthenticated(SkmError):
    category = ErrorCategory.UNAUTHENTICATED


class CapabilityUnavailable(SkmError):
    category = ErrorCategory.CAPABILITY


class BackendUnavailable(SkmError):
    category = ErrorCategory.BACKEND


class OutcomeUnknown(SkmError):
    category = ErrorCategory.OUTCOME_UNKNOWN


class InternalError(SkmError):
    category = ErrorCategory.INTERNAL


_CLASSES: tuple[type[SkmError], ...] = (
    NotFound,
    ValidationFailed,
    Conflict,
    PreconditionFailed,
    Forbidden,
    Unauthenticated,
    CapabilityUnavailable,
    BackendUnavailable,
    OutcomeUnknown,
    InternalError,
)
_BY_CATEGORY: Mapping[ErrorCategory, type[SkmError]] = MappingProxyType(
    {cls.category: cls for cls in _CLASSES}
)


def error_for(
    code: ErrorCode,
    message: str,
    *,
    details: Mapping[str, JsonValue] | None = None,
    retryable: bool | None = None,
) -> SkmError:
    """Build the subclass that matches the catalog category of ``code``.

    ``waiting`` codes are outcomes, not exceptions (``outcomes.Waiting``): they raise ``TypeError``.
    """
    category = CATALOG[ErrorCode(code)].category
    cls = _BY_CATEGORY.get(category)
    if cls is None:
        raise TypeError(f"{code} has category {category.value!r}, which is an outcome and not an exception")
    return cls(code, message, details=details, retryable=retryable)
