"""Public facade of the ``integrations`` module (integrations §13)."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

from .domain.budget import FirstTurnSource as FirstTurnSource
from .domain.budget import FirstTurnSourceKind as FirstTurnSourceKind
from .domain.budget import FirstTurnVerdict as FirstTurnVerdict
from .domain.decisions import FileDecision as FileDecision
from .domain.decisions import FileDecisionKind as FileDecisionKind
from .domain.desired import DesiredFile as DesiredFile
from .domain.desired import DesiredProjection as DesiredProjection
from .domain.desired import HostSubscriptionEvent as HostSubscriptionEvent
from .domain.desired import ProjectionInputs as ProjectionInputs
from .domain.events import DriftedProjectionFile as DriftedProjectionFile
from .domain.events import FailedProjectionFile as FailedProjectionFile
from .domain.events import ProjectionApplied as ProjectionApplied
from .domain.events import ProjectionDriftDetected as ProjectionDriftDetected
from .domain.events import ProjectionRemoved as ProjectionRemoved
from .domain.filesystem import FileStat as FileStat
from .domain.hook_events import HookClass as HookClass
from .domain.hook_events import HookEventKind as HookEventKind
from .domain.hook_events import HookSurfaceId as HookSurfaceId
from .domain.hook_events import NormalizedHookEvent as NormalizedHookEvent
from .domain.hook_outcomes import HostCommandVerdict as HostCommandVerdict
from .domain.hook_outcomes import HostHookOutcome as HostHookOutcome
from .domain.hook_outcomes import HostOutcomeStatus as HostOutcomeStatus
from .domain.hook_rules import HookDecision as HookDecision
from .domain.hook_rules import HookMode as HookMode
from .domain.hook_rules import HookVerdict as HookVerdict
from .domain.hook_subscriptions import Backoff as Backoff
from .domain.hook_subscriptions import CommandTarget as CommandTarget
from .domain.hook_subscriptions import EventSinkTarget as EventSinkTarget
from .domain.hook_subscriptions import ExecutionLocation as ExecutionLocation
from .domain.hook_subscriptions import FailurePolicy as FailurePolicy
from .domain.hook_subscriptions import HookSubscription as HookSubscription
from .domain.hook_subscriptions import HookTarget as HookTarget
from .domain.hook_subscriptions import RetrySpec as RetrySpec
from .domain.hook_subscriptions import SubscriptionKind as SubscriptionKind
from .domain.hook_subscriptions import WebhookTarget as WebhookTarget
from .domain.merged_json import OwnedKeyPath as OwnedKeyPath
from .domain.observed import AppliedFileRecord as AppliedFileRecord
from .domain.observed import ObservedFile as ObservedFile
from .domain.ownership import ManagedBoundary as ManagedBoundary
from .domain.ownership import Ownership as Ownership
from .domain.profiles import PermissionProfile as PermissionProfile
from .domain.projection import ApplyOutcome as ApplyOutcome
from .domain.projection import PlannedWrite as PlannedWrite
from .domain.projection import Projection as Projection
from .domain.projection import ProjectionId as ProjectionId
from .domain.projection import ProjectionPlan as ProjectionPlan
from .domain.projection import ProjectionState as ProjectionState
from .domain.reports import CheckResult as CheckResult
from .domain.reports import CommandResult as CommandResult
from .domain.reports import DeliveryResult as DeliveryResult
from .domain.reports import DoctorReport as DoctorReport
from .domain.reports import FirstTurnReport as FirstTurnReport
from .domain.reports import SpoolReport as SpoolReport
from .domain.reports import TrustReport as TrustReport
from .domain.target import Surface as Surface
from .domain.target import SurfaceSupport as SurfaceSupport
from .domain.target import TargetCapabilities as TargetCapabilities
from .domain.target import TargetId as TargetId
from .generated.commands import (
    RecordDrift,
    RecordDriftFilesItem,
    RecordProjectionApplied,
    RecordProjectionAppliedDefsAppliedFileInput,
    RecordProjectionAppliedDefsOwnedKeyPath,
    RecordProjectionAppliedFailedItem,
    RemoveProjection,
    RemoveProjectionFailedItem,
)
from .generated.queries import (
    GetAppliedState,
    GetDesiredProjection,
    ListProjections,
)
from .generated.results import (
    RecordDriftResult,
    RecordProjectionAppliedResult,
    RemoveProjectionResult,
)
from .generated.settings import (
    HooksHostView,
    HooksSettings,
    IntegrationsHostView,
    IntegrationsSettings,
)
from .generated.views import (
    AppliedStateView,
    AppliedStateViewDefsAppliedFileRecord,
    AppliedStateViewDefsManagedBoundary,
    AppliedStateViewDefsOwnedKeyPath,
    DesiredProjectionView,
    DesiredProjectionViewDefsHostSubscriptionEvent,
    ProjectionSummaryView,
    ProjectionsView,
)
from .ports import ProjectionRepository as ProjectionRepository

if TYPE_CHECKING:
    from .application.queries.get_hook_policy import (
        GetHookPolicy as GetHookPolicy,
    )
    from .application.queries.get_hook_policy import (
        HookPolicyView as HookPolicyView,
    )
    from .generated.commands import (
        RetryHookDeliveries as RetryHookDeliveries,
    )
    from .generated.commands import (
        TestHookSubscription as TestHookSubscription,
    )
    from .generated.queries import (
        ListHookDeliveries as ListHookDeliveries,
    )
    from .generated.queries import (
        ListHookSubscriptions as ListHookSubscriptions,
    )
    from .generated.results import (
        ListHookSubscriptionsResult as ListHookSubscriptionsResult,
    )
    from .generated.results import (
        RetryHookDeliveriesResult as RetryHookDeliveriesResult,
    )
    from .generated.results import (
        TestHookSubscriptionResult as TestHookSubscriptionResult,
    )
    from .generated.views import HookDeliveriesView as HookDeliveriesView

_LAZY_EXPORTS: dict[str, str] = {
    **dict.fromkeys(("GetHookPolicy", "HookPolicyView"), ".application.queries.get_hook_policy"),
    **dict.fromkeys(("RetryHookDeliveries", "TestHookSubscription"), ".generated.commands"),
    **dict.fromkeys(("ListHookDeliveries", "ListHookSubscriptions"), ".generated.queries"),
    **dict.fromkeys(
        ("ListHookSubscriptionsResult", "RetryHookDeliveriesResult", "TestHookSubscriptionResult"),
        ".generated.results",
    ),
    "HookDeliveriesView": ".generated.views",
}


def __getattr__(name: str) -> object:
    module_name = _LAZY_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name, __package__), name)
    globals()[name] = value
    return value


__all__ = [
    "AppliedFileRecord",
    "AppliedStateView",
    "AppliedStateViewDefsAppliedFileRecord",
    "AppliedStateViewDefsManagedBoundary",
    "AppliedStateViewDefsOwnedKeyPath",
    "ApplyOutcome",
    "Backoff",
    "CheckResult",
    "CommandResult",
    "CommandTarget",
    "DeliveryResult",
    "DesiredFile",
    "DesiredProjection",
    "DesiredProjectionView",
    "DesiredProjectionViewDefsHostSubscriptionEvent",
    "DoctorReport",
    "DriftedProjectionFile",
    "EventSinkTarget",
    "ExecutionLocation",
    "FailedProjectionFile",
    "FailurePolicy",
    "FileDecision",
    "FileDecisionKind",
    "FileStat",
    "FirstTurnReport",
    "FirstTurnSource",
    "FirstTurnSourceKind",
    "FirstTurnVerdict",
    "GetAppliedState",
    "GetDesiredProjection",
    "GetHookPolicy",
    "HookClass",
    "HookDecision",
    "HookDeliveriesView",
    "HookEventKind",
    "HookMode",
    "HookPolicyView",
    "HookSubscription",
    "HookSurfaceId",
    "HookTarget",
    "HookVerdict",
    "HooksHostView",
    "HooksSettings",
    "HostCommandVerdict",
    "HostHookOutcome",
    "HostOutcomeStatus",
    "HostSubscriptionEvent",
    "IntegrationsHostView",
    "IntegrationsSettings",
    "ListHookDeliveries",
    "ListHookSubscriptions",
    "ListHookSubscriptionsResult",
    "ListProjections",
    "ManagedBoundary",
    "NormalizedHookEvent",
    "ObservedFile",
    "OwnedKeyPath",
    "Ownership",
    "PermissionProfile",
    "PlannedWrite",
    "Projection",
    "ProjectionApplied",
    "ProjectionDriftDetected",
    "ProjectionId",
    "ProjectionInputs",
    "ProjectionPlan",
    "ProjectionRemoved",
    "ProjectionRepository",
    "ProjectionState",
    "ProjectionSummaryView",
    "ProjectionsView",
    "RecordDrift",
    "RecordDriftFilesItem",
    "RecordDriftResult",
    "RecordProjectionApplied",
    "RecordProjectionAppliedDefsAppliedFileInput",
    "RecordProjectionAppliedDefsOwnedKeyPath",
    "RecordProjectionAppliedFailedItem",
    "RecordProjectionAppliedResult",
    "RemoveProjection",
    "RemoveProjectionFailedItem",
    "RemoveProjectionResult",
    "RetryHookDeliveries",
    "RetryHookDeliveriesResult",
    "RetrySpec",
    "SpoolReport",
    "SubscriptionKind",
    "Surface",
    "SurfaceSupport",
    "TargetCapabilities",
    "TargetId",
    "TestHookSubscription",
    "TestHookSubscriptionResult",
    "TrustReport",
    "WebhookTarget",
]
