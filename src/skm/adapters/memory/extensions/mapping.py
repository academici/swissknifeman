"""Tables of ``skm_extensions`` in the memory backend state (extensions §11).

The tables live in ``MemoryBackendState.modules["extensions"]``; a unit of work works on a deep copy, so a
rollback drops them. Rows are the frozen domain values; a repository hands out copies, so no caller reaches a
stored manifest.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Final

from skm.adapters.memory.core.state import MemoryBackendState
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import InternalError
from skm.kernel.ids import PrincipalId, ResourceVersionId
from skm.kernel.json_types import JsonObject
from skm.modules.extensions.domain.keys import PackId, PackVersionId, ResourceId
from skm.modules.extensions.domain.pack import Pack, PackVersion
from skm.modules.extensions.domain.resource import Resource, ResourceVersion

__all__ = ["STATE_KEY", "MemoryExtensionsState", "QuarantineRow", "extensions_state"]

STATE_KEY: Final = "extensions"


@dataclass
class QuarantineRow:
    resource_version_id: ResourceVersionId
    reason_kind: str
    reasons: list[str]
    report: JsonObject | None
    created_by: PrincipalId
    created_at: datetime
    released_by: PrincipalId | None = None
    released_at: datetime | None = None
    release_reason: str | None = None


@dataclass
class MemoryExtensionsState:
    packs: dict[PackId, Pack] = field(default_factory=dict[PackId, Pack])
    pack_versions: dict[PackVersionId, PackVersion] = field(default_factory=dict[PackVersionId, PackVersion])
    resources: dict[ResourceId, Resource] = field(default_factory=dict[ResourceId, Resource])
    versions: dict[ResourceVersionId, ResourceVersion] = field(
        default_factory=dict[ResourceVersionId, ResourceVersion]
    )
    bodies: dict[ResourceVersionId, dict[str, bytes]] = field(
        default_factory=dict[ResourceVersionId, dict[str, bytes]]
    )
    quarantine: list[QuarantineRow] = field(default_factory=list[QuarantineRow])


def extensions_state(state: MemoryBackendState) -> MemoryExtensionsState:
    found = state.modules.get(STATE_KEY)
    if found is None:
        found = MemoryExtensionsState()
        state.modules[STATE_KEY] = found
    if not isinstance(found, MemoryExtensionsState):
        raise InternalError(
            ErrorCode.INTERNAL_ERROR, "extensions memory state is malformed", details={"module": STATE_KEY}
        )
    return found
