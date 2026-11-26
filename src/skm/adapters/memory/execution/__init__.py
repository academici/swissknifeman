"""Memory adapters of the execution repository and query ports (execution §6)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import TYPE_CHECKING

from skm.adapters.memory.core.state import MemoryBackendState
from skm.adapters.memory.execution.queries import MemoryExecutionQueries
from skm.adapters.memory.execution.repositories import (
    MemoryAcceptanceRepository,
    MemoryAssignmentRepository,
    MemoryAttemptRepository,
    MemoryAutopilotRepository,
    MemoryBudgetRepository,
    MemoryBundleRepository,
    MemoryCheckRepository,
    MemoryDecisionRepository,
    MemoryEffectRepository,
    MemoryEnvironmentRepository,
    MemoryEvidenceBindingRepository,
    MemoryIntegrationSlotRepository,
    MemoryOutputRepository,
    MemoryReadinessRepository,
    MemoryRecoveryRepository,
    MemoryReviewRepository,
    MemoryReviewRequestRepository,
    MemoryRunRepository,
    MemoryStageRepository,
    MemoryStepRepository,
    MemoryTaskRepository,
)
from skm.modules.execution.ports import (
    AcceptanceRepository,
    AssignmentRepository,
    AttemptRepository,
    AutopilotRepository,
    BudgetRepository,
    BundleRepository,
    CheckRepository,
    DecisionRepository,
    EffectRepository,
    EnvironmentRepository,
    EvidenceBindingRepository,
    ExecutionQueries,
    IntegrationSlotRepository,
    OutputRepository,
    ReadinessRepository,
    RecoveryRepository,
    ReviewRepository,
    ReviewRequestRepository,
    RunRepository,
    StageRepository,
    StepRepository,
    TaskRepository,
)

__all__ = ["REPOSITORIES"]

REPOSITORIES: Mapping[type, Callable[[MemoryBackendState], object]] = MappingProxyType(
    {
        RunRepository: MemoryRunRepository,
        BundleRepository: MemoryBundleRepository,
        ReadinessRepository: MemoryReadinessRepository,
        TaskRepository: MemoryTaskRepository,
        AttemptRepository: MemoryAttemptRepository,
        StageRepository: MemoryStageRepository,
        StepRepository: MemoryStepRepository,
        AssignmentRepository: MemoryAssignmentRepository,
        EnvironmentRepository: MemoryEnvironmentRepository,
        OutputRepository: MemoryOutputRepository,
        CheckRepository: MemoryCheckRepository,
        ReviewRepository: MemoryReviewRepository,
        AcceptanceRepository: MemoryAcceptanceRepository,
        BudgetRepository: MemoryBudgetRepository,
        DecisionRepository: MemoryDecisionRepository,
        EffectRepository: MemoryEffectRepository,
        IntegrationSlotRepository: MemoryIntegrationSlotRepository,
        ReviewRequestRepository: MemoryReviewRequestRepository,
        AutopilotRepository: MemoryAutopilotRepository,
        RecoveryRepository: MemoryRecoveryRepository,
        EvidenceBindingRepository: MemoryEvidenceBindingRepository,
        ExecutionQueries: MemoryExecutionQueries,
    }
)

if TYPE_CHECKING:

    def _check_ports(state: MemoryBackendState) -> tuple[object, ...]:
        r01: RunRepository = MemoryRunRepository(state)
        r02: BundleRepository = MemoryBundleRepository(state)
        r03: ReadinessRepository = MemoryReadinessRepository(state)
        r04: TaskRepository = MemoryTaskRepository(state)
        r05: AttemptRepository = MemoryAttemptRepository(state)
        r06: StageRepository = MemoryStageRepository(state)
        r07: StepRepository = MemoryStepRepository(state)
        r08: AssignmentRepository = MemoryAssignmentRepository(state)
        r09: EnvironmentRepository = MemoryEnvironmentRepository(state)
        r10: OutputRepository = MemoryOutputRepository(state)
        r11: CheckRepository = MemoryCheckRepository(state)
        r12: ReviewRepository = MemoryReviewRepository(state)
        r13: AcceptanceRepository = MemoryAcceptanceRepository(state)
        r14: BudgetRepository = MemoryBudgetRepository(state)
        r15: DecisionRepository = MemoryDecisionRepository(state)
        r16: EffectRepository = MemoryEffectRepository(state)
        r17: IntegrationSlotRepository = MemoryIntegrationSlotRepository(state)
        r18: ReviewRequestRepository = MemoryReviewRequestRepository(state)
        r19: AutopilotRepository = MemoryAutopilotRepository(state)
        r20: RecoveryRepository = MemoryRecoveryRepository(state)
        r21: EvidenceBindingRepository = MemoryEvidenceBindingRepository(state)
        r22: ExecutionQueries = MemoryExecutionQueries(state)
        return (
            r01,
            r02,
            r03,
            r04,
            r05,
            r06,
            r07,
            r08,
            r09,
            r10,
            r11,
            r12,
            r13,
            r14,
            r15,
            r16,
            r17,
            r18,
            r19,
            r20,
            r21,
            r22,
        )

    _ = _check_ports
