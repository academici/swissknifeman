"""Model classes, efforts and roles (runtimes §4.1).

``RoleId`` has exactly seven values, the same as execution and the role-result schemas; there is no repair
role (an invalid result is healed deterministically and retried by the same role).
"""

from __future__ import annotations

from enum import StrEnum


class ModelClass(StrEnum):
    ECONOMY = "economy"
    IMPLEMENTATION = "implementation"
    FRONTIER = "frontier"


class Effort(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"


class RoleId(StrEnum):
    SCOUT = "scout"
    EXECUTOR = "executor"
    REVIEWER = "reviewer"
    TRIAGER = "triager"
    ADVISOR = "advisor"
    RESEARCHER = "researcher"
    REGISTRAR = "registrar"


MODEL_CLASS_ORDER = tuple(ModelClass)
EFFORT_ORDER = tuple(Effort)
