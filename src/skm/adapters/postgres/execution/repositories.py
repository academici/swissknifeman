"""PostgreSQL repository adapters for ``execution`` (execution §6)."""

from __future__ import annotations

from skm.adapters.postgres.execution.acceptance import PostgresAcceptanceRepository
from skm.adapters.postgres.execution.assignments import PostgresAssignmentRepository
from skm.adapters.postgres.execution.attempts_stages import (
    PostgresAttemptRepository,
    PostgresStageRepository,
)
from skm.adapters.postgres.execution.autopilot_recovery import (
    PostgresAutopilotRepository,
    PostgresEvidenceBindingRepository,
    PostgresRecoveryRepository,
)
from skm.adapters.postgres.execution.budgets import PostgresBudgetRepository
from skm.adapters.postgres.execution.checks_reviews import (
    PostgresCheckRepository,
    PostgresReviewRepository,
)
from skm.adapters.postgres.execution.decisions_effects import (
    PostgresDecisionRepository,
    PostgresEffectRepository,
)
from skm.adapters.postgres.execution.environments_outputs import (
    PostgresEnvironmentRepository,
    PostgresOutputRepository,
)
from skm.adapters.postgres.execution.integration_slots import (
    PostgresIntegrationSlotRepository,
    PostgresReviewRequestRepository,
)
from skm.adapters.postgres.execution.runs_tasks import (
    PostgresBundleRepository,
    PostgresReadinessRepository,
    PostgresRunRepository,
)
from skm.adapters.postgres.execution.steps import PostgresStepRepository
from skm.adapters.postgres.execution.tasks import PostgresTaskRepository

__all__ = [
    "PostgresAcceptanceRepository",
    "PostgresAssignmentRepository",
    "PostgresAttemptRepository",
    "PostgresAutopilotRepository",
    "PostgresBudgetRepository",
    "PostgresBundleRepository",
    "PostgresCheckRepository",
    "PostgresDecisionRepository",
    "PostgresEffectRepository",
    "PostgresEnvironmentRepository",
    "PostgresEvidenceBindingRepository",
    "PostgresIntegrationSlotRepository",
    "PostgresOutputRepository",
    "PostgresReadinessRepository",
    "PostgresRecoveryRepository",
    "PostgresReviewRepository",
    "PostgresReviewRequestRepository",
    "PostgresRunRepository",
    "PostgresStageRepository",
    "PostgresStepRepository",
    "PostgresTaskRepository",
]
