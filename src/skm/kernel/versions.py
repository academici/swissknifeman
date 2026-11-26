"""Version and sequence number types (kernel-platform §2.3)."""

from dataclasses import dataclass
from typing import Final, NewType

from .error_codes import ErrorCode
from .errors import Conflict

__all__ = [
    "MIN_VERSION",
    "ExpectedVersion",
    "RevisionNo",
    "RowVersion",
    "SchemaVersion",
    "StreamSeq",
    "check_expected",
    "expected_version_from",
]

MIN_VERSION: Final = 1

RowVersion = NewType("RowVersion", int)  # >= 1, optimistic concurrency
SchemaVersion = NewType("SchemaVersion", int)  # >= 1, document format version
RevisionNo = NewType("RevisionNo", int)  # >= 1, plan revision number
StreamSeq = NewType("StreamSeq", int)  # >= 1, event order inside a stream


@dataclass(frozen=True, slots=True)
class ExpectedVersion:
    """Version a command expects; a mismatch is ``Conflict(VERSION_CONFLICT)``."""

    value: int  # >= 1

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, int):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError(f"ExpectedVersion.value must be int, got {type(self.value).__name__}")
        if self.value < MIN_VERSION:
            raise ValueError(f"ExpectedVersion.value must be >= {MIN_VERSION}, got {self.value}")


def expected_version_from(value: int | None) -> ExpectedVersion | None:
    """Wrap a nullable ``expected_*`` request field; ``None`` means the command checks nothing."""
    return None if value is None else ExpectedVersion(value)


def check_expected(actual: int, expected: ExpectedVersion | None) -> None:
    """Optimistic concurrency check: ``None`` checks nothing, a different version is ``VERSION_CONFLICT``.

    The error keeps both numbers in ``details`` as ``{"expected", "actual"}``.
    """
    if expected is None or actual == expected.value:
        return
    raise Conflict(
        ErrorCode.VERSION_CONFLICT,
        f"version conflict: expected {expected.value}, actual {actual}",
        details={"expected": expected.value, "actual": actual},
    )
