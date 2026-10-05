"""task.plan — JSON-first plan engine (layout v3): schemas, validator, store, authoring ops, check. stdlib-only."""
from . import check, ops, store  # noqa: F401 — submodules stay reachable as task.plan.check / .ops / .store
from .check import Issue  # noqa: F401
from .model import (  # noqa: F401
    CLASS_ORDER, DECISION_ID, EFFORT_ORDER, ITEM_ID, PHASE_ID, PLAN_ID, REF, SATISFYING, SHORT_ID,
    STATUS_LABEL, TERMINAL, ItemStatus, PlanError, Ref, id_sort_key, item_phase, parse_ref, phase_status,
)
from .schema import (  # noqa: F401
    ERROR_CODES, KINDS, Registry, SchemaProfileError, ValidationIssue, load_registry, validate,
)
from .store import (  # noqa: F401
    Plan, PlanLock, append_log, canonical_dump, load_plan, open_plan, read_log, save, save_many,
)
