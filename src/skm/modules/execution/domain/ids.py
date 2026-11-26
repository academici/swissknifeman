"""Typed UUID identifiers of execution records."""

from __future__ import annotations

from typing import NewType
from uuid import UUID

ReadinessReportId = NewType("ReadinessReportId", UUID)
StageRecordId = NewType("StageRecordId", UUID)
StepId = NewType("StepId", UUID)
AssignmentId = NewType("AssignmentId", UUID)
EnvironmentId = NewType("EnvironmentId", UUID)
OutputId = NewType("OutputId", UUID)
CheckExecutionId = NewType("CheckExecutionId", UUID)
ManualVerdictId = NewType("ManualVerdictId", UUID)
ReviewId = NewType("ReviewId", UUID)
FindingId = NewType("FindingId", UUID)
FindingResolutionId = NewType("FindingResolutionId", UUID)
FixBriefId = NewType("FixBriefId", UUID)
AcceptanceDecisionId = NewType("AcceptanceDecisionId", UUID)
DeviationId = NewType("DeviationId", UUID)
BudgetReservationId = NewType("BudgetReservationId", UUID)
DecisionRequestId = NewType("DecisionRequestId", UUID)
DecisionAnswerId = NewType("DecisionAnswerId", UUID)
DecisionRecordId = NewType("DecisionRecordId", UUID)
ExternalEffectId = NewType("ExternalEffectId", UUID)
IntegrationSlotId = NewType("IntegrationSlotId", UUID)
CarryForwardId = NewType("CarryForwardId", UUID)
ReviewRequestId = NewType("ReviewRequestId", UUID)
RecoveryRecordId = NewType("RecoveryRecordId", UUID)
