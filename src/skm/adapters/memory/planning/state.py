"""Tables of ``skm_planning`` in the memory backend state (planning §11).

The tables live in ``MemoryBackendState.modules["planning"]``; a unit of work works on a deep copy, so a
rollback drops them. Plans and drafts are the immutable domain values themselves. A revision keeps what the
port reads back; its typed ``Specification`` holds read-only mappings a deep copy cannot take and is derived
from the same document anyway. A pin selector is plain JSON inside a frozen value: the row keeps its own copy
and answers with copies, so a published revision does not change through a selector a caller holds (I1).
"""

from copy import deepcopy
from dataclasses import dataclass, field, replace
from typing import Final, Self
from uuid import UUID

from skm.adapters.memory.core.state import MemoryBackendState, copy_tables
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import InternalError
from skm.kernel.ids import EntityId, PlanId, ProjectId, RevisionId
from skm.kernel.json_types import JsonObject
from skm.modules.planning.domain.brief import DesignBrief
from skm.modules.planning.domain.draft import Draft, DraftId
from skm.modules.planning.domain.plan import Plan
from skm.modules.planning.domain.revision import RevisionMeta
from skm.modules.planning.domain.specification import EntityKind
from skm.modules.planning.ports import AliasKind, MaterialPin

__all__ = [
    "STATE_KEY",
    "MemoryPlanningState",
    "StoredIdentity",
    "StoredRevision",
    "detached_pins",
    "planning_state",
]

STATE_KEY: Final = "planning"
_PLANNING_TABLES: Final = frozenset(
    {"plans", "aliases", "next_plan_no", "drafts", "revisions", "identities", "design_briefs"}
)


def detached_pins(pins: tuple[MaterialPin, ...]) -> tuple[MaterialPin, ...]:
    return tuple(replace(pin, selector=deepcopy(pin.selector)) for pin in pins)


@dataclass(frozen=True, slots=True)
class StoredRevision:
    meta: RevisionMeta
    document: JsonObject
    _pins: tuple[MaterialPin, ...]
    plan_relation_targets: tuple[PlanId | None, ...]

    @property
    def pins(self) -> tuple[MaterialPin, ...]:
        return detached_pins(self._pins)


@dataclass(frozen=True, slots=True)
class StoredIdentity:
    plan_id: PlanId
    kind: EntityKind


@dataclass
class MemoryPlanningState:
    plans: dict[PlanId, Plan] = field(default_factory=dict[PlanId, Plan])
    aliases: dict[tuple[ProjectId, str], tuple[PlanId, AliasKind]] = field(
        default_factory=dict[tuple[ProjectId, str], tuple[PlanId, AliasKind]]
    )
    next_plan_no: dict[ProjectId, int] = field(default_factory=dict[ProjectId, int])
    drafts: dict[DraftId, Draft] = field(default_factory=dict[DraftId, Draft])
    revisions: dict[RevisionId, StoredRevision] = field(default_factory=dict[RevisionId, StoredRevision])
    identities: dict[EntityId, StoredIdentity] = field(default_factory=dict[EntityId, StoredIdentity])

    design_briefs: dict[UUID, DesignBrief] = field(default_factory=dict[UUID, DesignBrief])

    def __deepcopy__(self, memo: dict[int, object]) -> Self:
        # Every row is immutable: plans and identities hold scalars; drafts and revisions are stored detached
        # and read back as copies (see the module docstring), so a working copy needs only its own tables.
        return copy_tables(self, memo, shared_rows=_PLANNING_TABLES)


def planning_state(state: MemoryBackendState) -> MemoryPlanningState:
    found = state.modules.get(STATE_KEY)
    if found is None:
        found = MemoryPlanningState()
        state.modules[STATE_KEY] = found
    if not isinstance(found, MemoryPlanningState):
        raise InternalError(
            ErrorCode.INTERNAL_ERROR, "planning memory state is malformed", details={"module": STATE_KEY}
        )
    return found
