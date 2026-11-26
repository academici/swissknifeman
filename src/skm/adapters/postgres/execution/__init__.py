"""PostgreSQL ``execution`` adapter package (execution §6, §8; DDL ``0013``-``0016``, ``0026``-``0029``)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

import psycopg

from skm.adapters.postgres.execution.queries import PostgresExecutionQueries
from skm.adapters.postgres.execution.repositories import (
    PostgresAcceptanceRepository,
    PostgresAssignmentRepository,
    PostgresAttemptRepository,
    PostgresAutopilotRepository,
    PostgresBudgetRepository,
    PostgresBundleRepository,
    PostgresCheckRepository,
    PostgresDecisionRepository,
    PostgresEffectRepository,
    PostgresEnvironmentRepository,
    PostgresEvidenceBindingRepository,
    PostgresIntegrationSlotRepository,
    PostgresOutputRepository,
    PostgresReadinessRepository,
    PostgresRecoveryRepository,
    PostgresReviewRepository,
    PostgresReviewRequestRepository,
    PostgresRunRepository,
    PostgresStageRepository,
    PostgresStepRepository,
    PostgresTaskRepository,
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

REPOSITORIES: Mapping[type, Callable[[psycopg.Connection[Any]], object]] = MappingProxyType(
    {
        RunRepository: PostgresRunRepository,
        BundleRepository: PostgresBundleRepository,
        ReadinessRepository: PostgresReadinessRepository,
        TaskRepository: PostgresTaskRepository,
        AttemptRepository: PostgresAttemptRepository,
        StageRepository: PostgresStageRepository,
        StepRepository: PostgresStepRepository,
        AssignmentRepository: PostgresAssignmentRepository,
        EnvironmentRepository: PostgresEnvironmentRepository,
        OutputRepository: PostgresOutputRepository,
        CheckRepository: PostgresCheckRepository,
        ReviewRepository: PostgresReviewRepository,
        AcceptanceRepository: PostgresAcceptanceRepository,
        BudgetRepository: PostgresBudgetRepository,
        DecisionRepository: PostgresDecisionRepository,
        EffectRepository: PostgresEffectRepository,
        IntegrationSlotRepository: PostgresIntegrationSlotRepository,
        ReviewRequestRepository: PostgresReviewRequestRepository,
        AutopilotRepository: PostgresAutopilotRepository,
        RecoveryRepository: PostgresRecoveryRepository,
        EvidenceBindingRepository: PostgresEvidenceBindingRepository,
        ExecutionQueries: PostgresExecutionQueries,
    }
)

if TYPE_CHECKING:

    def _check_ports(conn: psycopg.Connection[Any]) -> tuple[object, ...]:
        r01: RunRepository = PostgresRunRepository(conn)
        r02: BundleRepository = PostgresBundleRepository(conn)
        r03: ReadinessRepository = PostgresReadinessRepository(conn)
        r04: TaskRepository = PostgresTaskRepository(conn)
        r05: AttemptRepository = PostgresAttemptRepository(conn)
        r06: StageRepository = PostgresStageRepository(conn)
        r07: StepRepository = PostgresStepRepository(conn)
        r08: AssignmentRepository = PostgresAssignmentRepository(conn)
        r09: EnvironmentRepository = PostgresEnvironmentRepository(conn)
        r10: OutputRepository = PostgresOutputRepository(conn)
        r11: CheckRepository = PostgresCheckRepository(conn)
        r12: ReviewRepository = PostgresReviewRepository(conn)
        r13: AcceptanceRepository = PostgresAcceptanceRepository(conn)
        r14: BudgetRepository = PostgresBudgetRepository(conn)
        r15: DecisionRepository = PostgresDecisionRepository(conn)
        r16: EffectRepository = PostgresEffectRepository(conn)
        r17: IntegrationSlotRepository = PostgresIntegrationSlotRepository(conn)
        r18: ReviewRequestRepository = PostgresReviewRequestRepository(conn)
        r19: AutopilotRepository = PostgresAutopilotRepository(conn)
        r20: RecoveryRepository = PostgresRecoveryRepository(conn)
        r21: EvidenceBindingRepository = PostgresEvidenceBindingRepository(conn)
        r22: ExecutionQueries = PostgresExecutionQueries(conn)
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
