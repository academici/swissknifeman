"""Named aliases of execution payloads that travel as plain JSON objects; no behaviour lives here."""

from __future__ import annotations

from typing import Literal

from skm.kernel.json_types import JsonObject

type Ambiguous = JsonObject
type AttemptView = JsonObject
type AutonomyFactors = JsonObject
type AutopilotStatusView = JsonObject
type AvailabilityResult = JsonObject
type BeginStageResult = JsonObject
type BudgetEstimate = JsonObject
type BudgetView = JsonObject
type Cursor = str
type DecisionPayload = JsonObject
type DecisionRequestView = JsonObject
type Diagnostic = JsonObject
type EffectReconciliation = JsonObject
type EffectRecordResult = JsonObject
type EffectReport = JsonObject
type EnvironmentView = JsonObject
type EvidenceOwnerKind = Literal["attempt", "output", "check_execution", "review"]
type ExecutionPolicy = JsonObject
type Extracted = JsonObject
type GateView = JsonObject
type HealOutcome = JsonObject
type HistoryCause = JsonObject
type HistoryPage = JsonObject
type LeaseSignal = JsonObject
type Missing = JsonObject
type NotHealable = JsonObject
type OutputManifestDraft = JsonObject
type Page[T] = JsonObject
type RangeSpec = JsonObject
type ReadinessAudit = JsonObject
type RebaseResult = JsonObject
type RetainPolicy = JsonObject
type ReviewReceipt = JsonObject
type RunBudgetView = JsonObject
type RunSummary = JsonObject
type RunView = JsonObject
type SealedOutput = JsonObject
type SlotBusy = JsonObject
type SlotLease = JsonObject
type StageProgress = JsonObject
type StepView = JsonObject
type TaskContractRef = JsonObject
type TaskView = JsonObject
type TimelineEntry = JsonObject
type Vote = JsonObject
