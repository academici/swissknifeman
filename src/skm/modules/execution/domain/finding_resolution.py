"""Finding resolutions: append-only reasons why a finding stopped asking for a fix (execution §4.13).

``fixed`` names the output whose change resolved it; a resolution never removes the finding or its
history.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from skm.modules.execution.domain.ids import FindingId, FindingResolutionId, OutputId

__all__ = ["FindingResolution", "ResolutionKind"]


class ResolutionKind(StrEnum):
    FIXED = "fixed"
    REJECTED_BY_TRIAGE = "rejected_by_triage"
    WAIVED = "waived"
    SUPERSEDED = "superseded"


@dataclass(frozen=True, slots=True)
class FindingResolution:
    id: FindingResolutionId
    finding_id: FindingId
    resolution_kind: ResolutionKind
    target_output_id: OutputId | None
    comment: str
    resolved_by: UUID
    at: datetime

    def __post_init__(self) -> None:
        if self.resolution_kind is ResolutionKind.FIXED and self.target_output_id is None:
            raise error_for(
                ErrorCode.SCHEMA_INVALID,
                "a fixed resolution names the output that fixed the finding",
                details={"finding_resolution_id": str(self.id)},
            )
