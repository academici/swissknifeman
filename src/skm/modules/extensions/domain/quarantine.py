"""Contract declarations; behavior is implemented by the owning leaf."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from skm.kernel.ids import PrincipalId, ResourceVersionId
    from skm.kernel.json_types import JsonObject


@dataclass(frozen=True, slots=True)
class QuarantineEntry:
    version_id: ResourceVersionId
    reason: str
    report: JsonObject
    created_by: PrincipalId
    created_at: datetime
