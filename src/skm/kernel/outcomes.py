"""Non-exception outcomes: diagnostics and waiting (kernel-platform §2.7)."""

import copy
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Final, Literal
from uuid import UUID

from .error_codes import CATALOG, ErrorCategory, ErrorCode
from .json_types import JsonValue

__all__ = ["CHECK_STATUS", "CheckStatus", "Diagnostic", "Severity", "Waiting"]

_DIAGNOSTIC_CODE: Final = re.compile(r"[A-Z][A-Z0-9_]*")


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


type CheckStatus = Literal["ok", "warn", "fail"]  # the status of a normalized doctor finding

# kernel-platform §5.2a: a doctor finding reports a severity as {info: ok, warning: warn, error: fail}
CHECK_STATUS: Final[Mapping[Severity, CheckStatus]] = MappingProxyType(
    {Severity.INFO: "ok", Severity.WARNING: "warn", Severity.ERROR: "fail"}
)


def _frozen_details(details: Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
    return MappingProxyType(copy.deepcopy(dict(details)))


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """A finding with a stable ``code``: an ``ErrorCode`` or a module finding code (UPPER_SNAKE)."""

    code: str
    message: str
    severity: Severity
    target: str | None = None  # JSON pointer, config key or entity id
    details: Mapping[str, JsonValue] = field(default_factory=dict[str, JsonValue])

    def __post_init__(self) -> None:
        if _DIAGNOSTIC_CODE.fullmatch(self.code) is None:
            raise ValueError(f"diagnostic code must be UPPER_SNAKE, got {self.code!r}")
        object.__setattr__(self, "severity", Severity(self.severity))
        object.__setattr__(self, "details", _frozen_details(self.details))


@dataclass(frozen=True, slots=True)
class Waiting:
    """Expected non-error outcome: the work waits for a human, an approval or an answer."""

    code: ErrorCode  # category waiting: MANUAL_PENDING, APPROVAL_REQUIRED, WAITING_FOR_ANSWER, ...
    message: str
    request_id: UUID | None = None
    details: Mapping[str, JsonValue] = field(default_factory=dict[str, JsonValue])

    def __post_init__(self) -> None:
        code = ErrorCode(self.code)
        if CATALOG[code].category is not ErrorCategory.WAITING:
            raise ValueError(f"Waiting needs a code of category 'waiting', got {code}")
        object.__setattr__(self, "code", code)
        object.__setattr__(self, "details", _frozen_details(self.details))
