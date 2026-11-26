"""Module manifest of the ``execution`` module (execution §2, §6, §8)."""

from __future__ import annotations

from skm.kernel.module_manifest import ModuleManifest
from skm.kernel.ports_uow import Surface

from .application._events import EVENTS
from .application.registry import COMMANDS, QUERIES
from .application.subscribers import SUBSCRIBERS
from .host.registry import operations
from .permissions import PERMISSIONS
from .ports import (
    AcceptanceRepository,
    AssignmentRepository,
    AttemptRepository,
    AutopilotRepository,
    BudgetRepository,
    BundleRepository,
    CheckRepository,
    CheckRunner,
    CheckRunnerRegistry,
    DecisionRepository,
    EffectRepository,
    EnvironmentRepository,
    EvidenceBindingRepository,
    ExecutionEnvironmentManager,
    ExecutionQueries,
    IntegrationSlotRepository,
    Isolation,
    IsolationRegistry,
    OutputRepository,
    ReadinessRepository,
    RecoveryRepository,
    ReviewCheckoutPathResolver,
    ReviewRepository,
    ReviewRequestRepository,
    RunRepository,
    StageRepository,
    StepRepository,
    TaskRepository,
    Vcs,
)

MODULE = ModuleManifest(
    id="execution",
    depends_on=(
        "access",
        "workspace",
        "artifacts",
        "extensions",
        "policy",
        "runtimes",
        "planning",
        "context",
    ),
    optional=False,
    db_schema="skm_execution",
    settings_sections=("execution", "budgets", "worker", "checks"),
    permissions=PERMISSIONS,
    repository_ports=(
        RunRepository,
        BundleRepository,
        ReadinessRepository,
        TaskRepository,
        AttemptRepository,
        StageRepository,
        StepRepository,
        AssignmentRepository,
        EnvironmentRepository,
        OutputRepository,
        CheckRepository,
        ReviewRepository,
        AcceptanceRepository,
        BudgetRepository,
        DecisionRepository,
        EffectRepository,
        IntegrationSlotRepository,
        ReviewRequestRepository,
        AutopilotRepository,
        RecoveryRepository,
        EvidenceBindingRepository,
        ExecutionQueries,
    ),
    gateway_ports=(
        ReviewCheckoutPathResolver,
        ExecutionEnvironmentManager,
        Vcs,
        CheckRunner,
        CheckRunnerRegistry,
        IsolationRegistry,
        Isolation,
    ),
    commands=COMMANDS,
    queries=QUERIES,
    subscribers=SUBSCRIBERS,
    host_operations=operations(Surface.CLI, Surface.HOOK),
    events=EVENTS,
)
