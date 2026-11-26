"""Immutable checkpoint overlay value; persistence belongs to BundleRepository."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from skm.kernel.ids import PrincipalId, RunId
from skm.kernel.json_types import JsonObject


@dataclass(frozen=True, slots=True)
class ReconfigurationRecord:
    """Append-only overlay row of ``skm_execution.run_reconfigurations`` (execution §6.1, §7)."""

    id: UUID
    run_id: RunId
    changes: JsonObject
    reason: str
    changed_by: PrincipalId
    changed_at: datetime
