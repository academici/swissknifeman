"""Host operations of the ``integrations`` module (integrations §7)."""

from __future__ import annotations

from skm.kernel.module_manifest import HostOperationSpec

from .adopt_file import SPEC as ADOPT_FILE
from .apply_projection import SPEC as APPLY_PROJECTION
from .detect_drift import SPEC as DETECT_DRIFT
from .drain_hook_spool import SPEC as DRAIN_HOOK_SPOOL
from .evaluate_hook import SPEC as EVALUATE_HOOK
from .first_turn_budget import SPEC as FIRST_TURN_BUDGET
from .plan_projection import SPEC as PLAN_PROJECTION
from .remove_projection import SPEC as REMOVE_PROJECTION
from .run_doctor import SPEC as RUN_DOCTOR
from .sync_projections import SYNC_SPEC, UNTRACK_SPEC
from .test_host_subscription import SPEC as TEST_HOST_SUBSCRIPTION
from .trust_hook_subscription import SPEC as TRUST_HOOK_SUBSCRIPTION

__all__ = ["HOST_OPERATIONS"]

HOST_OPERATIONS: tuple[HostOperationSpec, ...] = (
    PLAN_PROJECTION,
    APPLY_PROJECTION,
    DETECT_DRIFT,
    ADOPT_FILE,
    REMOVE_PROJECTION,
    RUN_DOCTOR,
    FIRST_TURN_BUDGET,
    EVALUATE_HOOK,
    TRUST_HOOK_SUBSCRIPTION,
    TEST_HOST_SUBSCRIPTION,
    DRAIN_HOOK_SPOOL,
    SYNC_SPEC,
    UNTRACK_SPEC,
)
