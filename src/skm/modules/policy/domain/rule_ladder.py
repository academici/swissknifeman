"""Off/warn/strict rule ladder (policy §5.8; port of harness ``lifecycle_policy_core.py``).

``verdict``: ``off`` allows; otherwise the first rule whose pattern ``re.search``-es the text decides —
``deny`` under ``strict``, ``warn`` under ``warn``; no match allows. The legacy ``normalize_mode`` turned an
unknown mode into ``off``; ``parse_guard_mode`` refuses it (``SCHEMA_INVALID``), so a typo never disables a
guard.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed

__all__ = ["GuardMode", "LadderRule", "LadderVerdict", "parse_guard_mode", "verdict"]


class GuardMode(StrEnum):
    STRICT = "strict"
    WARN = "warn"
    OFF = "off"


@dataclass(frozen=True, slots=True)
class LadderRule:
    id: str
    pattern: str
    reason: str
    tier: str = ""


@dataclass(frozen=True, slots=True)
class LadderVerdict:
    mode: GuardMode
    decision: Literal["allow", "warn", "deny"]
    match: LadderRule | None = None


def parse_guard_mode(value: object) -> GuardMode:
    """The mode of a config value; anything outside the enum is a schema error, never ``off``."""
    if isinstance(value, str) and value in {mode.value for mode in GuardMode}:
        return GuardMode(value)
    raise ValidationFailed(
        ErrorCode.SCHEMA_INVALID,
        "guard mode must be strict, warn or off",
        details={"reason": "unknown_guard_mode", "value": str(value)},
    )


def verdict(text: str, *, rules: tuple[LadderRule, ...], mode: GuardMode) -> LadderVerdict:
    if mode is GuardMode.OFF:
        return LadderVerdict(mode, "allow")
    for rule in rules:
        if re.search(rule.pattern, text):
            return LadderVerdict(mode, "deny" if mode is GuardMode.STRICT else "warn", rule)
    return LadderVerdict(mode, "allow")
