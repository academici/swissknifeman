# Contract inventory, part 2

| Признак | Control plane (bus handlers, подписчики) | Host operations |
|---|---|---|
| `src/skm/adapters/runtimes/_cli_session/binding.py` | verified_probe, pin_executable, bind_observation | P08.03 → P11.Z |
| `src/skm/modules/artifacts/host/__init__.py` | package boundary | P00.04.b |
| `src/skm/modules/artifacts/host/materialize_files.py` | SPEC, MaterializeFilesOperation, run | P00.04.b → P06.05 |
| `src/skm/modules/artifacts/host/registry.py` | HOST_OPERATIONS | P00.04.b → P06.05 |
| `src/skm/modules/artifacts/host/upload_file.py` | SPEC, UploadFileOperation, UploadSourceInfo, UploadSourceReader, run | P00.04.b → P06.05 |
| `src/skm/modules/artifacts/module.py` | MODULE | P00.04.b → P06.03.a → P06.05 |
| `src/skm/modules/artifacts/permissions.py` | PERMISSIONS | P00.04.b → P06.03.a |
| `src/skm/modules/artifacts/ports.py` | BlobLocationRef, StagingHandle, BlobObjectStat, BlobStore, BlobContentReader, StagedBlobRepository, BlobRepository, FileRepository, FileVersionRepository, AccessGrantRepository, MaterialWriter, BlobCoordination, BlobDigestLock | P00.04.b → P06.01.a → P06.02 → P06.03.c → P06.03.d |
| `src/skm/modules/artifacts/public.py` | FileId, register_file_version, require_ready_versions, file_id_of_version, get_file_version, consume_staged_blob, grant_access, revoke_grants, extend_grants, scan_document, build_safety_rules, latest_ready_version, read_text_content | P00.04.b → P06.01.a → P06.03.a → P06.03.c → P06.04.a |
| `src/skm/modules/artifacts/settings.py` | SECTION_URNS, SECTION_URN | P00.04.b → P02.02 |
| `src/skm/modules/context/__init__.py` | package boundary | P00.04.d |
| `src/skm/modules/context/application/__init__.py` | package boundary | P00.04.d |
| `src/skm/modules/context/application/_skills.py` | emit_skills, resolves and selects skills for context drafts | P15.02.a |
| `src/skm/modules/context/application/assemble_draft.py` | assemble_draft, admitted frozen render snapshot, and HOST_PRIVATE memory filtering | P09.04.a → P09.04.d → I-09.4 |
| `src/skm/modules/context/application/commands/__init__.py` | package boundary | P00.04.d |
| `src/skm/modules/context/application/commands/finalize_manifest.py` | SPEC, handle, scope_of_manifest; atomic guarded finalization | P09.04.d |
| `src/skm/modules/context/application/queries/__init__.py` | package boundary | P00.04.d |
| `src/skm/modules/context/application/queries/explain_context.py` | SPEC, handle, scope_of | P09.04.c |
| `src/skm/modules/context/application/queries/diff_contexts.py` | SPEC, handle, scope_of | P09.04.c |
| `src/skm/modules/context/application/queries/get_context_text.py` | SPEC, handle, scope_of | P09.04.c |
| `src/skm/modules/context/application/registry.py` | COMMANDS, QUERIES | P00.04.d → P09.04.c → P09.04.d → P09.09.a |
| `src/skm/modules/context/application/subscribers.py` | SUBSCRIBERS | P00.04.d → P09.04.a |
| `src/skm/modules/context/domain/__init__.py` | package boundary | P00.04.d |
| `src/skm/modules/context/domain/blocks.py` | BlockType, BudgetClass, TrustLevel, Mandatory, BlockSpec, BLOCK_SPECS, ROUND_TYPES | P00.04.d → P09.04.a |
| `src/skm/modules/context/domain/budget.py` | apply_budget | P00.04.d → P09.04.a |
| `src/skm/modules/context/domain/candidates.py` | discover | P00.04.d → P09.04.b |
| `src/skm/modules/context/domain/carriers.py` | instruction_carrier_dirs, static_prefix | P00.04.d → P09.04.c |
| `src/skm/modules/context/domain/compatibility.py` | check_compatibility | P00.04.d → P09.04.b |
| `src/skm/modules/context/domain/contracts.py` | Candidate, Compatible, Diagnostic, Digest, DraftMeta, FindingItem, HostFactsMeta, MemoryHit, Page, RouteRecord, Selected, SelfLoadView, SkillSelectionTrace, SnapshotBlock, StoredResearchResult, Validated | P00.04.d → P01.05.a → P09.04.a → P09.04.d → P09.09.a |
| `src/skm/modules/context/domain/decide.py` | Selection, decide | P00.04.d → P09.04.a |
| `src/skm/modules/context/domain/delegation_compiler.py` | DelegationCompiler, render the target model delegation brief | P09.04.a (I-06.2) |
| `src/skm/modules/context/domain/deps.py` | project_deps | P00.04.d → P09.04.c |
| `src/skm/modules/context/domain/digests.py` | task_digest, prompt_digest | P00.04.d → P09.04.b |
| `src/skm/modules/context/domain/draft.py` | DraftBlock, ConditionalBlock, BudgetPolicy, ContextDraft, build_draft | P00.04.d → P09.04.a |
| `src/skm/modules/context/domain/events.py` | EVENT_TYPES | P00.04.d → P09.04.a |
| `src/skm/modules/context/domain/explain.py` | explain_rows, diff_manifests | P00.04.d → P09.04.b |
| `src/skm/modules/context/domain/finalize.py` | FinalizedContext, finalize | P00.04.d → P09.04.a |
| `src/skm/modules/context/domain/globs.py` | glob_regex, path_matches | P00.04.d → P09.04.c |
| `src/skm/modules/context/domain/host_inputs.py` | HostInputKind, HostReadStatus, HostSelector, HostInputRequest, HostBlock, HostBlockMeta, HostFacts, plan_host_inputs | P00.04.d → P09.04.c |
| `src/skm/modules/context/domain/manifest.py` | ManifestState, ClassUsage, ManifestBlock, ContextManifest, build_manifest | P00.04.d → P09.04.a |
| `src/skm/modules/context/domain/payload_compiler.py` | PayloadCompiler, runtime notes and model compatibility checks | P09.04.a (I-06.2) |
| `src/skm/modules/context/domain/policy.py` | RepoInstructionsMode, SkillsMode, ContextPolicySpec, ContextPolicy, effective_policy | P00.04.d → P09.04.b |
| `src/skm/modules/context/domain/prefix_compiler.py` | PrefixStablePromptCompiler, PrefixStablePrompt | P09.04.a (I-06.3) |
| `src/skm/modules/context/domain/reasons.py` | IncludeReason, ExcludeReason | P00.04.d → P09.04.b |
| `src/skm/modules/context/domain/render.py` | render, substitute, fence | P00.04.d → P09.04.a |
| `src/skm/modules/context/domain/request.py` | StepPurpose, RuntimeTarget, PermissionsSummary, RunParams, ExecutionBlocks, ResumeInfo, ContextRequest, AnswerItem, PreviousAttemptSummary, CandidateRef, ContextMapItem, HistoryItem | P00.04.d → P09.04.a |
| `src/skm/modules/context/domain/research.py` | ResearchTier, SourceCapability, DocumentTrust, ResearchError, ResearchSourceConfig, ResearchQuerySpec, SourceQuery, RawDocument, RawSourceReply, ResearchDocument, Claim, Citation, ResearchUsage, ResearchResult, ResearchBatch, ResearchItem, RESEARCH_LADDER | P00.04.d → P09.09.a |
| `src/skm/modules/context/domain/research_render.py` | render_research, render_research_item | P00.04.d → P09.09.a |
| `src/skm/modules/context/domain/research_rules.py` | normalize_query, query_digest, cache_key, source_config_digest, checkout_digest, source_config, plan_sources, plan_limitations, ladder_stop, normalize_reply, validate_result, url_allowed, url_problem, document_urls_allowed | P00.04.d → P09.09.a |
| `src/skm/modules/context/domain/sections.py` | extract_sections | P00.04.d → P09.04.c |
| `src/skm/modules/context/domain/selection.py` | select | P00.04.d → P09.04.b |
| `src/skm/modules/context/domain/skill_selection.py` | select_skills, SkillEntry, SkillRequest | P00.04.d → P09.04.b |
| `src/skm/modules/context/domain/snapshot.py` | snapshot | P00.04.d → P09.04.b |
| `src/skm/modules/context/domain/steering_selection.py` | select_steering | P00.04.d → P09.04.b → P09.07 |
| `src/skm/modules/context/domain/validation.py` | validate | P00.04.d → P09.04.b |
| `src/skm/modules/context/host/__init__.py` | package boundary | P00.04.d |
| `src/skm/modules/context/host/collect_host_blocks.py` | owner declarations | P00.04.d → P09.04.c |
| `src/skm/modules/context/host/registry.py` | HOST_OPERATIONS, HOST_OPERATION_NAMES | P00.04.d → P09.04.c → P09.09.b |
| `src/skm/modules/context/host/research_query.py` | ResearchQueryOperation, research_query, run; injected clock/ids, durable replay and authorized mount resolution | P00.04.d → P09.09.b |
| `src/skm/modules/context/host/codegraph.py` | Resolve an active project checkout binding and dispatch native index maintenance through CodeGraphIndex | P09.09.b → I-09.3 |
| `src/skm/modules/context/module.py` | MODULE, RESEARCH_SPEC; canonical finalize-manifest registration and research descriptor | P00.04.d → P09.04.a → P09.04.d → P09.09.b |
| `src/skm/modules/context/permissions.py` | PERMISSIONS | P00.04.d → P09.04.a |
| `src/skm/modules/context/ports.py` | ContextOwnerClaim, ContextOwnerGuard, ContextRepository, TextStore, MemoryRetriever, CheckoutReader, ResearchSource, ResearchSourceRegistry, ResearchRepository, ReadOutcome | P00.04.d → P09.04.a → P09.04.d → P09.09.a |
| `src/skm/modules/context/public.py` | assemble_draft, get_manifest, require_final, research_documents, research_batches_for_step, collect_host_blocks, finalize, finalize_command, task_research_query, RecordResearchResult, FindResearchCache, GetResearchQuery, HostInputKind, PrefixStablePromptCompiler, PrefixStablePrompt | P00.04.d → P09.04.a → P09.09.a → P09.04.a (I-06.3) |
| `src/skm/modules/context/settings.py` | SECTION_URN, SECTION_URNS | P00.04.d → P02.02 |
| `src/skm/modules/execution/__init__.py` | package boundary | P00.04.d |
| `src/skm/modules/execution/application/__init__.py` | package boundary | P00.04.d |
| `src/skm/modules/execution/application/commands/__init__.py` | package boundary | P00.04.d |
| `src/skm/modules/execution/application/export_report.py` | Structural run metrics for the exports facade | P13.04.a |
| `src/skm/modules/execution/application/loaders.py` | cross-module read facades (get_run_summary, get_attempt_summary, get_run_report_data, get_attempt_activity, list_task_attempts_for_learning, load_check_executions, latest_run_outcome) and bundle policy loaders | P07.05.a → P13.03.c |
| `src/skm/modules/execution/application/queries/__init__.py` | package boundary | P00.04.d → P07.05.a |
| `src/skm/modules/execution/application/queries/get_attempt.py` | SPEC, handle (`execution.get_attempt`) | P07.05.a |
| `src/skm/modules/execution/application/queries/get_fix_brief.py` | SPEC, handle, GetFixBrief, FixBriefView (`execution.get_fix_brief`) | P08.10 |
| `src/skm/modules/execution/application/queries/get_readiness_report.py` | SPEC, handle (`execution.get_readiness_report`) | P07.05.a |
| `src/skm/modules/execution/application/queries/get_run.py` | SPEC, handle (`execution.get_run`) | P07.05.a |
| `src/skm/modules/execution/application/queries/get_execution_detail.py` | SPEC, handle (`execution.get_execution_detail`) | P12.05.a |
| `src/skm/modules/execution/generated/detail.py` | Generated execution detail query and view | P12.05.a |
| `src/skm/modules/execution/application/queries/get_run_budget.py` | SPEC, handle (`execution.get_run_budget`) | P07.05.a |
| `src/skm/modules/execution/application/queries/get_review_roi.py` | SPEC, handle (`execution.get_review_roi`) | P07.05.a → I-12.3 |
| `src/skm/modules/execution/application/queries/get_run_health.py` | SPEC, handle (`execution.get_run_health`) | P07.05.a |
| `src/skm/modules/execution/application/queries/get_run_history.py` | SPEC, handle, actor/scope-bound cursors (`execution.get_run_history`) | P07.05.a |
| `src/skm/modules/execution/application/queries/get_run_timeline.py` | SPEC, handle (`execution.get_run_timeline`) | P07.05.a |
| `src/skm/modules/execution/application/queries/get_step.py` | SPEC, handle (`execution.get_step`) | P07.05.a |
| `src/skm/modules/execution/application/queries/verify_stage_access.py` | Live assignment and fence for stage tools | P07.05.a, W03 |
| `src/skm/modules/execution/application/queries/get_task.py` | SPEC, handle (`execution.get_task`) | P07.05.a |
| `src/skm/modules/execution/application/queries/list_decision_requests.py` | SPEC, handle (`execution.list_decision_requests`) | P07.05.a |
| `src/skm/modules/execution/application/queries/list_execution_environments.py` | SPEC, handle (`execution.list_execution_environments`) | P07.05.a |
| `src/skm/modules/execution/application/queries/list_runs.py` | SPEC, handle (`execution.list_runs`) | P07.05.a |
| `src/skm/modules/execution/application/queries/list_task_attempts.py` | SPEC, handle (`execution.list_task_attempts`) | P07.05.a |
| `src/skm/modules/execution/application/queries/list_tasks.py` | SPEC, handle (`execution.list_tasks`) | P07.05.a |
| `src/skm/modules/execution/application/registry.py` | COMMANDS, QUERIES | P00.04.d → P07.05.a → P07.05.b → P07.05.c → P07.06 → P07.08.a → P07.08.b → P09.10 |
| `src/skm/modules/execution/application/subscribers.py` | SUBSCRIBERS | P00.04.d → P07.05.b → P10.08.a |
| `src/skm/modules/execution/domain/__init__.py` | package boundary | P00.04.d |
| `src/skm/modules/execution/domain/acceptance.py` | AcceptanceDecision, decide_acceptance, AcceptanceBasis, AcceptanceReason, Accepted, NotAcceptable | P00.04.d → P07.03.a |
| `src/skm/modules/execution/domain/assignment.py` | AssignmentState, WorkerRequirements, Assignment, StageInstruction, WorkerOffer | P00.04.d → P07.02 |
| `src/skm/modules/execution/domain/attempt.py` | AttemptState, Attempt, DeferredTrigger, SelectedStage, StageContinuation, AdvanceContinuation, PendingContinuation, ATTEMPT_TRANSITIONS | P00.04.d → P07.02 |
| `src/skm/modules/execution/domain/autonomy.py` | decide_audience, AuthorityEnvelope | P00.04.d → P07.03.a |
| `src/skm/modules/execution/domain/autopilot.py` | AutopilotStateKind, AutopilotState, classify_outcome, stop_conditions, AutopilotPolicy, AUTOPILOT_TRANSITIONS | P00.04.d → P08.12 |
| `src/skm/modules/execution/domain/blocking_reason.py` | BlockingCode, ResolverRole, AllowedAction, BlockingReason | P00.04.d → P07.02 |
| `src/skm/modules/execution/domain/budget.py` | BudgetDimension, BudgetAccount, BudgetReservation, reserve, settle, release | P00.04.d → P07.03.b |
| `src/skm/modules/execution/domain/carry_forward.py` | CarryForward, compatibility_digest | P00.04.d → P07.02 |
| `src/skm/modules/execution/domain/check_execution.py` | CheckKind, CheckState, CheckExecution, classify_check_result | P00.04.d → P07.03.a |
| `src/skm/modules/execution/domain/consilium.py` | aggregate | P00.04.d → P08.08 |
| `src/skm/modules/execution/domain/contract_digest.py` | task_contract_digest, scout_reuse_key | P00.04.d → P07.03.b |
| `src/skm/modules/execution/domain/contracts.py` | Ambiguous, AttemptView, AutonomyFactors, AutopilotStatusView, AvailabilityResult, BeginStageResult, BudgetEstimate, BudgetView, Cursor, DecisionPayload, DecisionRequestView, Diagnostic, EffectReconciliation, EffectRecordResult, EffectReport, EnvironmentView, ExecutionPolicy, Extracted, GateView, HealOutcome, HistoryCause, HistoryPage, LeaseSignal, Missing, NotHealable, OutputManifestDraft, Page, RangeSpec, ReadinessAudit, RebaseResult, RetainPolicy, ReviewReceipt, RunBudgetView, RunSummary, RunView, SealedOutput, SlotBusy, SlotLease, StageProgress, StepView, TaskContractRef, TaskView, TimelineEntry, Vote | P00.04.d → P01.05.a → P07.05.a → P07.08.a → P07.05.c |
| `src/skm/modules/execution/domain/decision_record.py` | QuestionCategory, DecisionRecord, classify_question | P00.04.d → P07.03.a |
| `src/skm/modules/execution/domain/decision_request.py` | DecisionKind, Audience, DecisionState, DecisionRequest, DecisionAnswer, question_key, question_digest | P00.04.d → P07.03.a |
| `src/skm/modules/execution/domain/deviation.py` | DeviationAcceptance | P00.04.d → P07.03.a |
| `src/skm/modules/execution/domain/environment.py` | EnvironmentKind, EnvironmentState, BaselineEntry, ExecutionEnvironment | P00.04.d → P07.02 |
| `src/skm/modules/execution/domain/events.py` | EVENT_TYPES | P00.04.d → P07.02 |
| `src/skm/modules/execution/domain/execution_bundle.py` | ResourcePin, ResourcePins, ExecutionBundle, SatisfiedTask, RunSelection | P00.04.d → P07.02 |
| `src/skm/modules/execution/domain/external_effect.py` | EffectKind, EffectState, ExternalEffect, GitCommitRequest, GitCommitReceipt | P00.04.d → P07.08.b |
| `src/skm/modules/execution/application/commands/reconcile_external_effect.py` | Bound administrative reconciliation command and worker guards | P07.08.b |
| `src/skm/modules/execution/domain/finding.py` | Severity, FindingState, Finding, finding_key | P00.04.d → P07.03.a |
| `src/skm/modules/execution/domain/finding_resolution.py` | ResolutionKind, FindingResolution | P00.04.d → P07.03.a |
| `src/skm/modules/execution/domain/fix_brief.py` | FixBrief, build_fix_brief, FixBriefItem | P00.04.d → P07.03.a |
| `src/skm/modules/execution/domain/gates.py` | decide_gate, decide_plan_acceptance, RequirementCoverage, CriterionCoverage, CoverageReport | P00.04.d → P07.11 |
| `src/skm/modules/execution/domain/health.py` | HealthClass, classify_run_health | P00.04.d → P07.06 |
| `src/skm/modules/execution/domain/history.py` | build_history | P00.04.d → P07.05.a |
| `src/skm/modules/execution/domain/ids.py` | owner declarations | P00.04.d → P07.02 |
| `src/skm/modules/execution/domain/integration.py` | IntegrationStrategy, CommitMode, IntegrationSlot, IntegrationHost, commit_trailers, commit_plan, excluded_paths | P00.04.d → P07.08.a |
| `src/skm/modules/execution/domain/lease.py` | WorkerClaim, Lease, verify_fence, next_fencing_token, ProcessIdentity | P00.04.d → P07.02 |
| `src/skm/modules/execution/domain/manual_verdict.py` | ManualVerdict, current_verdict | P00.04.d → P07.03.a |
| `src/skm/modules/execution/domain/output.py` | OutputSource, ChangedPath, OutputMount, DiffStats, OutputManifest, Output, manifest_digest | P00.04.d → P07.02 |
| `src/skm/modules/execution/domain/readiness.py` | ReadinessStatus, ReadinessInputs, ReadinessScope, ReadinessFinding, ReadinessCheckResult, ReadinessReport, readiness_inputs_digest, evaluate_readiness, freshness, write_scope_overlaps | P00.04.d → P07.05.b |
| `src/skm/modules/execution/domain/recovery.py` | RecoveryRecord, plan_recovery, breaker_open, RecoveryStep | P00.04.d → P08.08 |
| `src/skm/modules/execution/domain/repair.py` | extract_result, heal, schema_error_hint | P00.04.d → P07.03.b |
| `src/skm/modules/execution/domain/retry.py` | RetryAction, decide_retry, RetryInputs, RetryDecision | P00.04.d → P07.03.b |
| `src/skm/modules/execution/domain/review.py` | ReviewState, Verdict, Freshness, ReviewerKind, Review, freshness_of, choose_review_profile, ReviewClearance | P00.04.d → P07.03.a |
| `src/skm/modules/execution/domain/review_grouping.py` | ReviewGrouping, choose_grouping | P00.04.d → P07.03.a |
| `src/skm/modules/execution/domain/review_request.py` | ReviewRequest, ReviewTarget, target_digest, ReviewReceipt.fresh_for, RequestReview wire identity | P00.04.d → P09.10 |
| `src/skm/modules/execution/domain/review_strategy.py` | ReviewDecision, decide_review, rereview_scope, followup_findings, INTENSITIES, DEFAULT_FOLLOWUPS_MAX | P00.04.d → P07.03.a |
| `src/skm/modules/execution/domain/risk.py` | score, RiskFacts, RiskFeature, RiskScore | P00.04.d → P07.03.a |
| `src/skm/modules/execution/domain/role_contracts.py` | RoleContract, ROLE_CONTRACTS | P00.04.d → P07.04.a |
| `src/skm/modules/execution/domain/read_documents.py` | build_task_doc, build_attempt_detail_doc, build_step_view_doc, build_budget_view_doc, AttemptDetailParts | P07.05.a |
| `src/skm/modules/execution/domain/frozen_json.py` | thaw_json | P07.05.a |
| `src/skm/modules/execution/domain/stored_payloads.py` | validate_step_payloads, validate_continuation_payload, validate_step_note, validate_readiness_report, config_snapshot_document, work_policies_document, check_binding_role, EVIDENCE_BINDING_ROLES, canonical_bytes, store error factories | P07.05.a |
| `src/skm/modules/execution/domain/reaping.py` | reap_barrier_satisfied, reap_receipt, timeout_cancel_outcome, timeout_cancel_requested | P07.06 |
| `src/skm/modules/execution/domain/run.py` | RunKind, RunStatus, Run, RUN_TRANSITIONS, start, pause, resume, cancel, finish | P00.04.d → P00.04.f → P07.02 |
| `src/skm/modules/execution/domain/scheduling.py` | select_assignable, SchedulingInput | P00.04.d → P07.06 |
| `src/skm/modules/execution/domain/semantics.py` | outcome_key, drift | P00.04.d → P07.03.b |
| `src/skm/modules/execution/domain/session.py` | RouteRef, SessionFingerprint, decide_session, SessionFacts, Resume, Fresh | P00.04.d → P07.04.b |
| `src/skm/modules/execution/domain/stage_record.py` | StageState, StageOutcomeKind, StageRecord | P00.04.d → P07.02 |
| `src/skm/modules/execution/domain/step.py` | RoleId, StepPurpose, StepState, AttemptStep | P00.04.d → P07.02 |
| `src/skm/modules/execution/domain/step_note.py` | NoteKind, Urgency, StepNote | P00.04.d → P07.03.a |
| `src/skm/modules/execution/domain/task.py` | TaskKind, TaskStatus, ReviewMode, TaskOrigin, PathPattern, Task, WORK_KINDS, GATE_KINDS, TASK_TRANSITIONS, transition | P00.04.d → P00.04.f → P07.02 → P07.11 |
| `src/skm/modules/execution/domain/task_graph.py` | EdgeKind, TaskEdge, compile_run_tasks, ready_task_ids, gate_members | P00.04.d → P07.02 → P07.11 |
| `src/skm/modules/execution/domain/transitions.py` | TransitionDeclaration | P00.04.d → P07.02 |
| `src/skm/modules/execution/domain/triage.py` | reverify_decision, trivial_command | P00.04.d → P08.06 |
| `src/skm/modules/execution/domain/work_policy.py` | Intensity, RoleIntensities, EffectiveWorkPolicy, resolve_work_policy | P00.04.d → P07.02 |
| `src/skm/modules/execution/domain/workflow/__init__.py` | package boundary | P00.04.d |
| `src/skm/modules/execution/domain/workflow/actions.py` | RunStage, WaitFor, Accept, Rework, CreateFollowups, NewAttempt, Escalate, Fail, Integrate, Done, Noop, NextAction | P00.04.d → P07.04.a → P07.04.b |
| `src/skm/modules/execution/domain/workflow/action_builders.py` | advance-engine action builders: accept, consult, triage, question routing, recheck, escalations | P07.04.b |
| `src/skm/modules/execution/domain/workflow/definition.py` | StageType, OnOutcome, StageDefinition, WorkflowDefinition, applies_to_kind | P00.04.d → P07.04.a → P07.11 |
| `src/skm/modules/execution/domain/workflow/engine.py` | ActionDecision, TaskState, advance, decide_advance | P00.04.d → P07.04.b → P07.11 |
| `src/skm/modules/execution/domain/workflow/history.py` | StageEntry, StageHistory | P00.04.d → P07.04.a |
| `src/skm/modules/execution/domain/workflow/predicates.py` | PredicateKind, Predicate, evaluate, AllPredicates, AnyPredicates, Condition | P00.04.d → P07.04.a → P07.04.b |
| `src/skm/modules/execution/domain/workflow/task_facts.py` | task-state facts of the advance engine: findings, checks, commits, budgets, retries, question routes, history causes | P07.04.b |
| `src/skm/modules/execution/domain/workflow/stage_inputs.py` | StageMode, FeedbackRefs | P00.04.d → P07.04.a |
| `src/skm/modules/execution/host/__init__.py` | package boundary | P00.04.d |
| `src/skm/modules/execution/host/checks.py` | CheckRequest, CheckDeps, CheckResult | P00.04.d → P07.07.a |
| `src/skm/modules/execution/host/clean_environments.py` | CleanEnvironmentsOperation | P00.04.d → P07.07.a |
| `src/skm/modules/execution/host/context.py` | build_stage_deps | P00.04.d → P07.07.b |
| `src/skm/modules/execution/host/environment.py` | EnvironmentMount, EnvironmentSpec, PreparedEnvironment, RemovedEnvironment | P00.04.d → P07.07.a → P07.08.a |
| `src/skm/modules/execution/host/evidence.py` | EvidenceOperation, EvidenceFile, BlobUploader | P00.04.d → P07.07.a |
| `src/skm/modules/execution/host/heartbeat.py` | HeartbeatOperation | P00.04.d → P07.07.b |
| `src/skm/modules/execution/host/isolation.py` | IsolationSpec, WrappedCommand | P00.04.d → P08.07.a |
| `src/skm/modules/execution/host/recovery.py` | RecoveryOperation | P00.04.d → P08.08 |
| `src/skm/modules/execution/host/registry.py` | HOST_OPERATIONS, HOST_OPERATION_NAMES | P00.04.d → P07.07.a → P07.07.b → P09.05 → P09.09.b → P11.04.b → P08.08 → P08.06 → P09.10 → P07.08.a → P07.08.b |
| `src/skm/modules/execution/host/request_review.py` | request_review.run, registry.operations; immutable target dispatch and patch upload | P00.04.d → P09.10 |
| `src/skm/modules/execution/host/stage_client.py` | owner declarations | P00.04.d → P07.07.b |
| `src/skm/modules/execution/host/stages/__init__.py` | package boundary | P00.04.d |
| `src/skm/modules/execution/host/stages/advisor_consult.py` | AdvisorConsultStage | P00.04.d → P08.08 |
| `src/skm/modules/execution/host/stages/agent_review.py` | AgentReviewStage | P00.04.d → P07.07.b → P08.06 |
| `src/skm/modules/execution/host/stages/agent_step.py` | AgentStepStage | P00.04.d → P07.07.b → P08.06 |
| `src/skm/modules/execution/host/stages/base.py` | StageRequest, StageOutcome | P00.04.d → P07.07.b |
| `src/skm/modules/execution/host/stages/integrate.py` | IntegrateStage | P00.04.d → P07.08.a → P07.08.b |
| `src/skm/modules/execution/host/stages/prepare_environment.py` | PrepareEnvironmentStage | P00.04.d → P07.07.a |
| `src/skm/modules/execution/host/stages/run_checks.py` | RunChecksStage | P00.04.d → P07.07.a → P07.08.a |
| `src/skm/modules/execution/host/worker_loop.py` | WorkerLoopOperation | P00.04.d → P07.07.b |
| `src/skm/modules/execution/module.py` | MODULE | P00.04.d → P07.05.a → P10.08.a |
| `src/skm/modules/execution/permissions.py` | PERMISSIONS | P00.04.d → P07.05.a |
| `src/skm/modules/execution/ports.py` | RunRepository, BundleRepository, ReadinessRepository, TaskRepository, AttemptRepository, StageRepository, StepRepository, AssignmentRepository, EnvironmentRepository, OutputRepository, CheckRepository, ReviewRepository, AcceptanceRepository, BudgetRepository, DecisionRepository, EffectRepository, IntegrationSlotRepository, ReviewRequestRepository, AutopilotRepository, RecoveryRepository, EvidenceBindingRepository, ExecutionQueries, ExecutionEnvironmentManager, Vcs, CheckRunner, StageHandler, StageClient, StageDeps, CheckRunnerRegistry, IsolationRegistry, Isolation | P00.04.d → P07.05.a → P07.08.a |
| `src/skm/modules/execution/public.py` | require_research_step_scope, require_research_assignment, require_current_context_owner, get_run_summary, get_attempt_summary, get_run_report_data, latest_run_outcome, get_attempt_activity, list_task_attempts_for_learning, list_check_executions | P00.04.d → P07.05.a → P07.05.c → P09.09.a → P13.03.c |
| `src/skm/modules/execution/settings.py` | SECTION_URNS | P00.04.d → P02.02 |
| `src/skm/modules/exports/__init__.py` | package boundary | P00.04.e |
| `src/skm/modules/exports/application/__init__.py` | package boundary | P00.04.e |
| `src/skm/modules/exports/application/commands/__init__.py` | package boundary | P00.04.e |
| `src/skm/modules/exports/application/commands/purge_notes.py` | SPEC | P13.04.a |
| `src/skm/modules/exports/application/commands/record_note_written.py` | SPEC | P13.04.a |
| `src/skm/modules/exports/application/commands/requeue_note.py` | SPEC | P13.04.a |
| `src/skm/modules/exports/application/queries/__init__.py` | package boundary | P00.04.e |
| `src/skm/modules/exports/application/queries/list_pending_notes.py` | SPEC | P13.04.a |
| `src/skm/modules/exports/application/queries/list_vault_notes.py` | SPEC | P13.04.a |
| `src/skm/modules/exports/application/queries/render_plan_markdown.py` | SPEC | P13.04.a |
| `src/skm/modules/exports/application/queries/render_run_report.py` | SPEC | P13.04.a |
| `src/skm/modules/exports/application/registry.py` | COMMANDS, QUERIES | P00.04.e → P13.04.a |
| `src/skm/modules/exports/application/subscribers.py` | SUBSCRIBERS | P00.04.e → P13.04.a |
| `src/skm/modules/exports/domain/__init__.py` | package boundary | P00.04.e |
| `src/skm/modules/exports/domain/contracts.py` | CandidatePage, ScanBudget, VaultNoteListItem | P00.04.e → P01.05.a → P13.04.a |
| `src/skm/modules/exports/domain/docs_push.py` | safe_pattern, matches, sensitive, destination | P13.04.c |
| `src/skm/modules/exports/domain/events.py` | EVENT_TYPES | P00.04.e → P13.04.a |
| `src/skm/modules/exports/domain/frontmatter.py` | Fields, FrontmatterValue, render, read | P13.04.a |
| `src/skm/modules/exports/domain/markdown.py` | FrontmatterValue, MarkdownDoc | P00.04.e → P13.04.a |
| `src/skm/modules/exports/domain/note.py` | NoteKind, VaultNoteState, VaultNote, VaultNoteWrite | P00.04.e → P13.04.a |
| `src/skm/modules/exports/domain/plan_markdown.py` | PlanExportView, render_plan, render_plan_note | P13.04.a |
| `src/skm/modules/exports/domain/run_report.py` | RunReportMetrics | P00.04.e → P13.04.a |
| `src/skm/modules/exports/domain/vault.py` | VaultIdentity, VaultLocation | P00.04.e → P13.04.b → P13.04.c |
| `src/skm/modules/exports/domain/vault_catalog.py` | VaultProjectMatch | P00.04.e → P13.04.a |
| `src/skm/modules/exports/host/__init__.py` | package boundary | P00.04.e |
| `src/skm/modules/exports/host/locate_vault.py` | run | P00.04.e → P13.04.b |
| `src/skm/modules/exports/host/push_vault_docs.py` | DocsCheckoutFs, push_vault_docs, run | P00.04.e → P13.04.c |
| `src/skm/modules/exports/host/push_vault_notes.py` | run | P00.04.e → P13.04.b |
| `src/skm/modules/exports/host/registry.py` | operations | P00.04.e → P13.04.b → P13.04.c |
| `src/skm/modules/exports/module.py` | MODULE | P00.04.e → P13.04.a → P13.04.b → P13.04.c |
| `src/skm/modules/exports/permissions.py` | PERMISSIONS | P00.04.e → P13.04.a |
| `src/skm/modules/exports/ports.py` | CandidatePage, Cursor, VaultNoteRepository, VaultFs | P00.04.e → P13.04.a |
| `src/skm/modules/exports/public.py` | owner declarations | P00.04.e → P13.04.a |
| `src/skm/modules/exports/settings.py` | SECTION_URN, SECTION_URNS | P00.04.e → P02.02 → P13.04.a |
| `src/skm/modules/extensions/__init__.py` | package boundary | P00.04.c |
| `src/skm/modules/extensions/application/__init__.py` | package boundary | P00.04.c → P09.01.a |
| `src/skm/modules/extensions/application/candidate.py` | PackCandidate, ResourceCandidate, build_candidate, parse_text_resource, schema_registry | P09.01.a |
| `src/skm/modules/extensions/application/commands/__init__.py` | package boundary | P00.04.c → P09.01.a |
| `src/skm/modules/extensions/application/commands/install_pack.py` | SPEC, handle | P09.01.a |
| `src/skm/modules/extensions/application/commands/quarantine_resource.py` | SPEC, handle | P09.01.a |
| `src/skm/modules/extensions/application/commands/release_quarantine.py` | SPEC, handle | P09.01.a |
| `src/skm/modules/extensions/application/commands/sync_builtin_packs.py` | SPEC, handle | P09.01.a |
| `src/skm/modules/extensions/application/commands/uninstall_pack_version.py` | SPEC, handle | P09.01.a |
| `src/skm/modules/extensions/application/install.py` | install_candidate, product_version | P09.01.a |
| `src/skm/modules/extensions/application/permission_proof.py` | profile_violations | P09.01.a |
| `src/skm/modules/extensions/application/queries/__init__.py` | package boundary | P00.04.c → P09.01.a |
| `src/skm/modules/extensions/application/queries/get_pack.py` | SPEC, handle | P09.01.a |
| `src/skm/modules/extensions/application/queries/get_resource_version.py` | SPEC, handle | P09.01.a |
| `src/skm/modules/extensions/application/queries/list_packs.py` | SPEC, handle | P09.01.a |
| `src/skm/modules/extensions/application/queries/list_resources.py` | SPEC, handle | P09.01.a |
| `src/skm/modules/extensions/application/queries/resolve_resource.py` | SPEC, handle | P09.01.a |
| `src/skm/modules/extensions/application/registry.py` | COMMANDS, QUERIES | P00.04.c → P09.01.a → P09.01.b |
| `src/skm/modules/extensions/application/resolving.py` | active_decision, chosen_pack_versions, decide, resolved_keys, resource_version_view, selected_packs, version_view | P09.01.a |
| `src/skm/modules/extensions/application/subscribers.py` | SUBSCRIBERS | P00.04.c → P09.01.a |
| `src/skm/modules/extensions/domain/__init__.py` | package boundary | P00.04.c |
| `src/skm/modules/extensions/domain/agent_profile.py` | AgentProfile, PromptPlan, RoleLimits, AgentPermissions, ContextPolicySpec | P00.04.c → P09.01.a |
| `src/skm/modules/extensions/domain/compat.py` | CompatCheckId, CompatStatus, CompatVerdict, CompatCheck, CompatReport | P00.04.c → P09.01.b |
| `src/skm/modules/extensions/domain/digest_rules.py` | file_digest, is_excluded, pack_digest, resource_digest | P09.01.a |
| `src/skm/modules/extensions/domain/events.py` | EVENT_TYPES | P00.04.c → P09.01.a |
| `src/skm/modules/extensions/domain/keys.py` | PackSlug, ResourceKey, SemVer, VersionConstraint | P00.04.c → P09.01.a |
| `src/skm/modules/extensions/domain/kinds.py` | ResourceKind, KindSpec, RESOURCE_KINDS | P00.04.c → P09.01.a |
| `src/skm/modules/extensions/domain/override_rules.py` | OverrideDecision | P00.04.c → P09.01.b → P09.03 |
| `src/skm/modules/extensions/domain/pack.py` | Digest, PackTrust, TRUST_RANK, PackState, ExclusiveGroup, PackOverride, PackManifest, Pack, PackVersion, PackPins | P00.04.c → P09.01.a |
| `src/skm/modules/extensions/domain/payload.py` | PayloadFile, PackPayload | P00.04.c → P09.01.b |
| `src/skm/modules/extensions/domain/permission_guard.py` | permission_request, widens_permissions | P09.01.a |
| `src/skm/modules/extensions/domain/plan_template.py` | PlanTemplateManifest | P00.04.c → P09.08 |
| `src/skm/modules/extensions/domain/prompt_block.py` | PromptBlockManifest | P00.04.c → P09.01.b |
| `src/skm/modules/extensions/domain/provenance.py` | ProvenanceSource, UpstreamStrategy, UpstreamFile, Provenance, CompatAcceptance | P00.04.c → P09.01.b |
| `src/skm/modules/extensions/domain/quarantine.py` | QuarantineEntry | P00.04.c → P09.01.a |
| `src/skm/modules/extensions/domain/requires.py` | RequiresNode, RequiresDiagnostic | P00.04.c → P09.01.b |
| `src/skm/modules/extensions/domain/resolution.py` | PackChoice, ResolutionDecision | P00.04.c → P09.01.a → P09.03 |
| `src/skm/modules/extensions/domain/resource.py` | Digest, Resource, ResourceFile, ResourceVersion, ResourceRef | P00.04.c → P09.01.a |
| `src/skm/modules/extensions/domain/skill.py` | SelectionKind, SkillTriggers, SkillManifest, SkillFrontmatter | P00.04.c → P09.01.b |
| `src/skm/modules/extensions/domain/steering.py` | SteeringScope, SteeringManifest | P00.04.c → P09.07 |
| `src/skm/modules/extensions/domain/upstream.py` | UpstreamItem | P00.04.c → P09.01.c |
| `src/skm/modules/extensions/host/__init__.py` | package boundary | P00.04.c |
| `src/skm/modules/extensions/host/check_upstream.py` | CheckUpstreamOperation | P00.04.c → P09.01.c |
| `src/skm/modules/extensions/host/install_pack.py` | InstallPackOperation | P00.04.c → P09.01.b |
| `src/skm/modules/extensions/host/registry.py` | HOST_OPERATIONS | P00.04.c → P09.01.c → P09.01.b |
| `src/skm/modules/extensions/module.py` | MODULE | P00.04.c → P09.01.a |
| `src/skm/modules/extensions/permissions.py` | PERMISSIONS | P00.04.c → P09.01.a |
| `src/skm/modules/extensions/ports.py` | PackReader, BuiltinPacks, UpstreamFetcher, PackRepository, ResourceRepository, QuarantineRepository, RuntimeCatalogSeeder | P00.04.c → P09.01.a |
| `src/skm/modules/extensions/public.py` | resolve_resource, get_resource_version, known_keys, list_resolved, pinned_pack_versions, load_agent_profile, select_agent_profile, default_profile_key, load_skill, load_text_resource, exclusive_groups, pack_config_fragments, runtime_catalog, publish_runtime_catalog_snapshot | P00.04.c → P09.01.a → I-05.2 |
| `src/skm/modules/extensions/settings.py` | SECTION_URN, SECTION_URNS | P00.04.c → P02.02 |
| `src/skm/modules/integrations/__init__.py` | package boundary | P00.04.e |
| `src/skm/modules/integrations/application/__init__.py` | package boundary | P00.04.e → P10.01.b |
| `src/skm/modules/integrations/application/commands/__init__.py` | package boundary | P00.04.e → P10.01.b |
| `src/skm/modules/integrations/application/commands/record_drift.py` | SPEC, handle | P10.01.b |
| `src/skm/modules/integrations/application/commands/record_projection_applied.py` | SPEC, handle | P10.01.b |
| `src/skm/modules/integrations/application/commands/remove_projection.py` | SPEC, handle | P10.01.b |
| `src/skm/modules/integrations/application/projection_views.py` | host_map_for_project, project_scope, require_safe_relative_path, require_tagged_digest, resolve_project_binding_host, to_applied_file_view, to_projection_summary_view | P10.01.b |
| `src/skm/modules/integrations/application/queries/__init__.py` | package boundary | P00.04.e → P10.01.b |
| `src/skm/modules/integrations/application/queries/get_applied_state.py` | SPEC, handle | P10.01.b |
| `src/skm/modules/integrations/application/queries/get_desired_projection.py` | SPEC, handle | P10.01.b → P10.06 |
| `src/skm/modules/integrations/application/queries/list_projections.py` | SPEC, handle | P10.01.b |
| `src/skm/modules/integrations/application/registry.py` | COMMANDS, QUERIES | P00.04.e → P10.01.b → P10.08.a |
| `src/skm/modules/integrations/application/subscribers.py` | SUBSCRIBERS | P00.04.e → P10.01.b → P10.08.a |
| `src/skm/modules/integrations/domain/__init__.py` | package boundary | P00.04.e |
| `src/skm/modules/integrations/domain/budget.py` | FirstTurnSourceKind, FirstTurnSource, FirstTurnVerdict | P00.04.e → P10.07 |
| `src/skm/modules/integrations/domain/checks/__init__.py` | DoctorContext, run_checks, summarize | P10.07 |
| `src/skm/modules/integrations/domain/checks/context.py` | DoctorContext, effective_settings, finding, mapping, strings | P10.07 |
| `src/skm/modules/integrations/domain/checks/claude.py` | CHECKS, hook_commands | P10.07 |
| `src/skm/modules/integrations/domain/checks/clients.py` | CODEX_CHECKS, CURSOR_CHECKS | P10.07 |
| `src/skm/modules/integrations/domain/checks/projections.py` | CHECKS, local_settings_gitignored | P10.07 |
| `src/skm/modules/integrations/host/doctor.py` | budget_settings, doctor_context, native_inputs, read_layers, read_text | P10.07 |
| `src/skm/entrypoints/cli/commands/doctor.py` | GROUP, add_parser, register, run_host_operation | P10.07 |
| `src/skm/entrypoints/cli/commands/budget.py` | GROUP, add_parser, register | P10.07 |
| `src/skm/modules/integrations/domain/bundle.py` | BUNDLE_SCHEMA_URN, BundleAgent, BundleAsset, BundleAssetSurface, BundleSkill, IntegrationBundleManifest, merge_and_render_bundle_assets, normalize_desired_json, normalize_desired_map, parse_bundle_manifest, resolve_bundle_asset_path, validate_bundle_source_path, validate_pack_prefix | P10.06 |
| `src/skm/modules/integrations/domain/conflict_names.py` | DEFAULT_CONFLICT_SUFFIX, conflict_path, is_conflict_path, original_path | P10.01.a |
| `src/skm/modules/integrations/domain/contracts.py` | AdoptOutcome, AgentPayload, ClientLayer, Diagnostic, DriftReport, HookBinding, HookOutput, InstructionBlock, McpServerSpec, NormalizedPermissions, SkillPayload, SourceRef, SecretRef, ScopeLevel | P00.04.e → P01.05.a → P10.01.b |
| `src/skm/modules/integrations/domain/decisions.py` | FileDecisionKind, FileDecision, decide_file, is_safe_relative_path | P00.04.e → P10.01.a |
| `src/skm/modules/integrations/domain/desired.py` | DesiredFile, DesiredProjection, HostSubscriptionEvent, ProjectionInputs | P00.04.e → P10.01.a |
| `src/skm/modules/integrations/domain/desired_inputs.py` | BundleTargetAccumulator, build_agent_doc, build_core_instruction_block, build_project_instruction_block, collect_host_subscription_events, empty_instruction_block, encode_inputs_digest_bytes, extract_bundle_source_bytes, format_diagnostic, skill_matches_target, skill_requires, steering_matches_project, steering_priority, tool_admits | P10.06 |
| `src/skm/modules/integrations/domain/events.py` | EVENT_TYPES, EVENTS, FailedProjectionFile, DriftedProjectionFile, ProjectionApplied, ProjectionDriftDetected, ProjectionRemoved | P00.04.e → P10.01.b |
| `src/skm/modules/integrations/domain/filesystem.py` | FileStat | P00.04.e → P10.01.c |
| `src/skm/modules/integrations/domain/hook_events.py` | HookSurfaceId, HookClass, HookEventKind, NormalizedHookEvent | P00.04.e → P10.05.a |
| `src/skm/modules/integrations/domain/hook_outcomes.py` | HostCommandVerdict, HostOutcomeStatus, HostHookOutcome | P00.04.e → P10.08.a |
| `src/skm/modules/integrations/domain/hook_rules.py` | HookMode, HookVerdict, HookDecision | P00.04.e → P10.05.a |
| `src/skm/modules/integrations/domain/hook_subscriptions.py` | SubscriptionKind, ExecutionLocation, FailurePolicy, Backoff, RetrySpec, WebhookTarget, CommandTarget, EventSinkTarget, HookSubscription, HookTarget | P00.04.e → P02.02 → P10.08.a |
| `src/skm/modules/integrations/domain/managed_block.py` | BlockMarker, extract_blocks, is_valid_block_id, parse_markers, render_block, replace_blocks | P10.01.a |
| `src/skm/modules/integrations/domain/merged_json.py` | HOOK_COMMAND_PREFIX, OwnedKeyPath, dumps_merged_json, dumps_merged_json_bytes, ensure_mapping, extract_owned, extract_owned_json, has_jsonc_comments, is_tagged_item, lookup_owned_path, merge_owned, merge_owned_json, parse_json_document | P00.04.e → P10.01.a |
| `src/skm/modules/integrations/domain/merged_toml.py` | dumps_merged_toml, dumps_merged_toml_bytes, extract_owned_toml, format_toml_document, format_toml_inline_table, format_toml_key, format_toml_table, format_toml_value, merge_owned_toml, parse_toml | P10.01.a |
| `src/skm/modules/integrations/domain/observed.py` | FileKind, ObservedFile, AppliedFileRecord, extract_managed_bytes, extract_managed_digest, observe_bytes | P00.04.e → P10.01.a |
| `src/skm/modules/integrations/domain/ownership.py` | Ownership, ManagedBoundary, empty_managed_digest, sha256_tagged | P00.04.e → P10.01.a |
| `src/skm/modules/integrations/domain/permission_docs.py` | build_permission_request_doc, serialize_permission_set | P10.06 |
| `src/skm/modules/integrations/domain/profiles.py` | PROFILE_ORDER, PermissionProfile, ProfileResolution, is_at_most_profile, narrow_profile, resolve_profile | P00.04.e → P10.01.a |
| `src/skm/modules/integrations/domain/projection.py` | PROJECTION_TRANSITIONS, ProjectionId, ProjectionState, Projection, ProjectionPlan, PlannedWrite, ApplyOutcome, build_planned_write, can_transition_projection, next_state_after_apply | P00.04.e → P10.01.a |
| `src/skm/modules/integrations/domain/reports.py` | CheckResult, DoctorReport, FirstTurnReport, TrustReport, SpoolReport, CommandResult, DeliveryResult | P00.04.e → P10.07 → P10.08.a → P10.08.b |
| `src/skm/modules/integrations/domain/target.py` | TargetId, Surface, SurfaceSupport, TargetCapabilities | P00.04.e → P10.01.a |
| `src/skm/modules/integrations/host/__init__.py` | package boundary | P00.04.e |
| `src/skm/modules/integrations/host/adopt_file.py` | AdoptFileOperation | P00.04.e → P10.01.c |
| `src/skm/modules/integrations/host/apply_projection.py` | ApplyProjectionOperation | P00.04.e → P10.01.c |
| `src/skm/modules/integrations/host/detect_drift.py` | DetectDriftOperation | P00.04.e → P10.01.c |
| `src/skm/modules/integrations/host/drain_hook_spool.py` | DrainHookSpoolOperation | P00.04.e → P10.08.b |
| `src/skm/modules/integrations/host/evaluate_hook.py` | EvaluateHookOperation | P00.04.e → P10.05.a → P13.03.c |
| `src/skm/modules/integrations/host/first_turn_budget.py` | FirstTurnBudgetOperation | P00.04.e → P10.07 |
| `src/skm/modules/integrations/host/observe.py` | observe, observe_path, CheckoutFs binding/lock/journal/pre-image helpers | P10.01.c |
| `src/skm/modules/integrations/host/plan_projection.py` | PlanProjectionOperation | P00.04.e → P10.01.c |
| `src/skm/modules/integrations/host/sync_projections.py` | sync, untrack; sync and untrack host operation specs | P10.01.c → I-09.1 |
| `src/skm/modules/integrations/host/registry.py` | HOST_OPERATIONS | P00.04.e → P10.01.c → P10.07 → P10.08.b → P10.05.a → P13.03.c |
| `src/skm/modules/integrations/host/remove_projection.py` | RemoveProjectionOperation | P00.04.e → P10.01.c |
| `src/skm/modules/integrations/host/run_doctor.py` | RunDoctorOperation | P00.04.e → P10.07 |
| `src/skm/modules/integrations/host/test_host_subscription.py` | TestHostSubscriptionOperation | P00.04.e → P10.08.b |
| `src/skm/modules/integrations/host/trust_hook_subscription.py` | TrustHookSubscriptionOperation | P00.04.e → P10.08.b |
| `src/skm/modules/integrations/module.py` | MODULE | P00.04.e → P10.01.b → P10.01.c |
| `src/skm/modules/integrations/permissions.py` | PERMISSIONS | P00.04.e → P10.01.b |
| `src/skm/modules/integrations/ports.py` | Cursor, Page, ProjectionRepository, IntegrationTarget, IntegrationTargetRegistry, CheckoutFs, CheckoutGitExcludes, ProjectionConfig, LocalCheckoutProjections, UserHomeReader, HostCommandRunner | P00.04.e → P10.01.b |
| `src/skm/modules/integrations/public.py` | owner declarations | P00.04.e → P10.01.b |
| `src/skm/modules/integrations/settings.py` | SECTION_URN, SECTION_URNS | P00.04.e → P02.02 → P10.08.a |
| `src/skm/modules/knowledge/__init__.py` | package boundary | P00.04.e |
| `src/skm/modules/knowledge/application/__init__.py` | package boundary | P00.04.e → P13.01.b |
| `src/skm/modules/knowledge/application/commands/__init__.py` | package boundary | P00.04.e → P13.01.b |
| `src/skm/modules/knowledge/application/commands/deprecate_lesson.py` | SPEC, handle | P13.01.b |
| `src/skm/modules/knowledge/application/commands/expire_memory.py` | SPEC, handle | P13.01.b |
| `src/skm/modules/knowledge/application/commands/forget.py` | SPEC, handle | P13.01.b |
| `src/skm/modules/knowledge/application/commands/import_graph.py` | SPEC, handle | P13.02.a |
| `src/skm/modules/knowledge/application/commands/remember.py` | SPEC, handle | P13.01.b |
| `src/skm/modules/knowledge/application/lesson_operations.py` | require_lesson, promote, deprecate_in_uow | P13.01.b |
| `src/skm/modules/knowledge/application/queries/__init__.py` | package boundary | P00.04.e → P13.01.b |
| `src/skm/modules/knowledge/application/queries/get_lesson.py` | SPEC, handle | P13.01.b |
| `src/skm/modules/knowledge/application/queries/graph_indexes.py` | SPEC, handle | P13.02.b |
| `src/skm/modules/knowledge/application/queries/graph_neighbors.py` | SPEC, handle, project_visible, graph_visibility, require_root, read_neighborhood, answer | P13.02.a |
| `src/skm/modules/knowledge/application/queries/graph_path.py` | SPEC, handle | P13.02.a |
| `src/skm/modules/knowledge/application/queries/graph_stats.py` | SPEC, handle | P13.02.a |
| `src/skm/modules/knowledge/application/queries/graph_subgraph.py` | SPEC, handle, project_graph | P13.02.b |
| `src/skm/modules/knowledge/application/queries/list_lessons.py` | SPEC, handle | P13.01.b |
| `src/skm/modules/knowledge/application/queries/list_memory.py` | SPEC, handle | P13.01.b |
| `src/skm/modules/knowledge/application/queries/search_memory.py` | SPEC, handle, search | P13.01.b |
| `src/skm/modules/knowledge/application/registry.py` | COMMANDS, QUERIES | P00.04.e → P13.01.b → P13.02.b |
| `src/skm/modules/knowledge/application/scopes.py` | project_ref, workspace_ref, project_memory_scope, requested_scope, require_instance_write | P13.01.b |
| `src/skm/modules/knowledge/application/subscribers.py` | SUBSCRIBERS | P00.04.e → P13.01.b |
| `src/skm/modules/knowledge/application/views.py` | memory_view, lesson_view, validate_lesson_storage | P13.01.b |
| `src/skm/modules/knowledge/domain/__init__.py` | package boundary | P00.04.e |
| `src/skm/modules/knowledge/domain/contracts.py` | Adjacency, CandidateId, GraphQueryEcho, GraphStats, LessonView, MemoryEntryView, ReplaceStats | P00.04.e → P01.05.a → P13.01.b → P13.03.b |
| `src/skm/modules/knowledge/domain/events.py` | EVENTS, EVENT_TYPES, MemoryRemembered, MemoryForgotten, LessonPromoted, LessonDeprecated, GraphImported | P00.04.e → P13.01.a |
| `src/skm/modules/knowledge/domain/evidence.py` | EvidenceRef | P00.04.e → P13.01.a → P13.03.b |
| `src/skm/modules/knowledge/domain/graph.py` | GraphEdgeId, GraphNodeId, NodeType, EdgeType, GraphNode, GraphEdge, node_key, parse_node_key, EdgeIdentity, edge_identity, source_payload_matches, project_reference | P00.04.e → P13.02.a |
| `src/skm/modules/knowledge/domain/graph_algorithms.py` | Direction, Traversal, DEFAULT_TRAVERSAL, SubgraphView, Neighborhood, NeighborHit, neighbors, shortest_path, subgraph, components, stats, bounded_neighborhood, node_from_row | P13.02.a |
| `src/skm/modules/knowledge/domain/graph_answer.py` | GraphAnswer, IndexKey, index_keys, build_answer | P00.04.e → P13.02.a |
| `src/skm/modules/knowledge/domain/graph_carriers.py` | Freshness, GraphSourceRef, AnswerNode, AnswerEdge | P00.04.e → P13.02.a |
| `src/skm/modules/knowledge/domain/graph_index.py` | GraphBasis, Completeness, FreshnessState, LimitationCode, Limitation, GraphIndex, next_generation | P00.04.e → P13.02.a |
| `src/skm/modules/knowledge/domain/graph_namespaces.py` | shares, link_allowed | P13.02.a |
| `src/skm/modules/knowledge/domain/lesson.py` | LessonId, LessonKind, LessonState, ConfidenceTier, Lesson, LessonApplicability, LessonFreshness, new_lesson_from_candidate, deprecate, flag_decay, evaluate_freshness, potential_conflict_ids | P00.04.e → P13.01.a |
| `src/skm/modules/knowledge/domain/memory_entry.py` | MemoryEntryId, MemorySource, MemoryState, MemoryEntry, new_entry, expire, forget, supersede | P00.04.e → P13.01.a |
| `src/skm/modules/knowledge/domain/memory_kind.py` | MemoryKind, REJECTED_JOURNAL_KINDS | P00.04.e → P13.01.a |
| `src/skm/modules/knowledge/domain/memory_policy.py` | MemoryPolicySettings, REPOSITORY_COPY_RE, rejection_reason, validate_memory_write, ttl_for, is_live, check_limits, check_handoff_replacement | P13.01.a |
| `src/skm/modules/knowledge/domain/memory_scope.py` | MemoryScopeKind, MemoryScope, allowed_scopes, recall_scopes, require_project_scope, ensure_scope_allowed, scope_lock_key | P00.04.e → P13.01.a |
| `src/skm/modules/knowledge/domain/promotion.py` | CandidateForPromotion, LessonRef | P00.04.e → P13.03.b |
| `src/skm/modules/knowledge/domain/recall.py` | RecallSettings, rank_entries, partition_recall, select_for_budget | P13.01.a |
| `src/skm/modules/knowledge/domain/truncation.py` | TruncationReceipt, estimate_tokens_json, truncate_largest_list | P13.01.a |
| `src/skm/modules/knowledge/host/__init__.py` | package boundary | P00.04.e |
| `src/skm/modules/knowledge/host/derive_project_graph.py` | DeriveProjectGraphOperation, derive_project_graph | P00.04.e → P13.02.b |
| `src/skm/modules/knowledge/host/import_code_graph.py` | ImportCodeGraphOperation, import_code_graph | P00.04.e → P13.02.b |
| `src/skm/modules/knowledge/host/registry.py` | operations | P00.04.e → P13.02.b |
| `src/skm/modules/knowledge/module.py` | MODULE and the host-only LocalEpisodicMemory port | P00.04.e → P13.01.b → P13.02.a → P13.02.b → I-09.4 |
| `src/skm/modules/knowledge/permissions.py` | PERMISSIONS | P00.04.e → P13.01.b |
| `src/skm/modules/knowledge/ports.py` | ScopeLimits, SortKey, start_after, page_of, lesson_filters, applicability_json, MemoryRepository, LessonRepository, GraphRepository, CodeGraphReader, ManifestReader, LocalEpisodicMemory, EpisodeScope, LocalEpisode, EpisodeRecordStatus | P00.04.e → P13.01.b → I-09.4 |
| `src/skm/modules/knowledge/public.py` | promote_lesson, list_lessons_for_context, search_memory_for_context, lesson_confidence_inputs, flag_lesson_decay, deprecate_lesson | P00.04.e → P13.01.b → P13.03.b |
| `src/skm/modules/knowledge/settings.py` | SECTION_URN, SECTION_URNS | P00.04.e → P02.02 |
| `src/skm/modules/learning/__init__.py` | package boundary | P00.04.e |
| `src/skm/modules/learning/application/__init__.py` | package boundary | P00.04.e |
| `src/skm/modules/learning/application/commands/__init__.py` | package boundary | P00.04.e |
| `src/skm/modules/learning/application/commands/record_activity.py` | SPEC, handle | P13.03.c |
| `src/skm/modules/learning/application/commands/extract_candidates.py` | SPEC, handle | P13.03.c |
| `src/skm/modules/learning/application/commands/promote_candidate.py` | SPEC, handle, CandidatePromoted | P13.03.b |
| `src/skm/modules/learning/application/commands/recompute_confidence.py` | SPEC, handle | P13.03.b → P13.03.c |
| `src/skm/modules/learning/application/commands/review_candidate.py` | SPEC, handle | P13.03.b |
| `src/skm/modules/learning/application/queries/__init__.py` | package boundary | P00.04.e |
| `src/skm/modules/learning/application/queries/pathology_stats.py` | SPEC, handle | P13.03.c |
| `src/skm/modules/learning/application/queries/list_signals.py` | SPEC, handle | P13.03.c |
| `src/skm/modules/learning/application/queries/list_candidates.py` | SPEC, handle | P13.03.c |
| `src/skm/modules/learning/application/queries/get_candidate.py` | SPEC, handle | P13.03.c |
| `src/skm/modules/learning/application/registry.py` | COMMANDS, QUERIES | P00.04.e → P13.03.b → P13.03.c |
| `src/skm/modules/learning/application/subscribers.py` | SUBSCRIBERS | P00.04.e → P13.03.c |
| `src/skm/modules/learning/domain/__init__.py` | package boundary | P00.04.e |
| `src/skm/modules/learning/domain/activity.py` | ActivitySummary, ActivityRecord, evidence budget, LearningSettings | P00.04.e → P13.03.a |
| `src/skm/modules/learning/domain/candidate.py` | CandidateState, ConfidenceTier, Candidate, empirical Signal | P00.04.e → P13.03.a |
| `src/skm/modules/learning/domain/check_commands.py` | command-position check recognition | P13.03.a |
| `src/skm/modules/learning/domain/confidence.py` | independent source counters and confidence | P13.03.a |
| `src/skm/modules/learning/domain/consolidation.py` | exact fingerprint, shortlist, consolidation decision | P00.04.e → P13.03.a |
| `src/skm/modules/learning/domain/contracts.py` | CandidateProposalView, CandidateRef | P00.04.e → P01.05.a → P13.03.b → P13.03.c |
| `src/skm/modules/learning/domain/detectors.py` | Detector, Observation, extraction and diagnostic replay | P00.04.e → P13.03.a |
| `src/skm/modules/learning/domain/events.py` | candidate stream, typed event payloads and EVENT_TYPES | P00.04.e → P13.03.a |
| `src/skm/modules/learning/domain/evidence.py` | ExposedLessonRef, DetectorEvidence | P00.04.e → P13.03.a |
| `src/skm/modules/learning/domain/pathology.py` | PathologyCode, PathologyFinding, neutral diagnostics and replay | P00.04.e → P13.03.a |
| `src/skm/modules/learning/domain/promotion.py` | human gate and promotion prerequisites | P13.03.a |
| `src/skm/modules/learning/domain/recompute.py` | adaptive thresholds, attainable gates and numeric transitions | P13.03.a |
| `src/skm/modules/learning/domain/remediations.py` | review hypotheses for recurrent findings | P13.03.a |
| `src/skm/modules/learning/domain/review.py` | ReviewVerdict, CandidateReview, CandidateProposal, review and proposal projections | P00.04.e → P13.03.a |
| `src/skm/modules/learning/domain/tokens.py` | exact text normalization and Unicode shortlist scoring | P13.03.a |
| `src/skm/modules/learning/host/__init__.py` | package boundary | P00.04.e |
| `src/skm/modules/learning/host/registry.py` | HOST_OPERATIONS | P00.04.e |
| `src/skm/modules/learning/module.py` | MODULE | P00.04.e → P13.03.b → P13.03.c |
| `src/skm/modules/learning/permissions.py` | PERMISSIONS | P00.04.e → P13.03.c |
| `src/skm/modules/learning/ports.py` | Cursor, Page, ActivityRecordRepository, CandidateRepository, SignalRepository, CandidateReviewRepository, CandidateProposalRepository | P00.04.e → P13.03.b |
| `src/skm/modules/learning/public.py` | client-safe wire DTOs and lazy domain re-exports | P00.04.e → P13.03.c |
| `src/skm/modules/learning/settings.py` | SECTION_URN, SECTION_URNS | P00.04.e → P02.02 |
| `src/skm/modules/planning/__init__.py` | package boundary | P00.04.c |
| `src/skm/modules/planning/application/__init__.py` | package boundary | P00.04.c |
| `src/skm/modules/planning/application/commands/__init__.py` | package boundary | P00.04.c |
| `src/skm/modules/planning/application/commands/abandon_draft.py` | SPEC, handle, scope_of | P05.04.b |
| `src/skm/modules/planning/application/commands/archive_plan.py` | SPEC, handle, scope_of | P05.04.b |
| `src/skm/modules/planning/application/commands/design_plan.py` | Plan intake and design evidence | P05.04.b → I-11.1 |
| `src/skm/modules/planning/application/commands/create_plan.py` | SPEC, handle, scope_of | P05.04.b → P09.08 |
| `src/skm/modules/planning/application/commands/import_specification.py` | SPEC, handle, permissions_of, scope_of | P05.07 |
| `src/skm/modules/planning/application/commands/open_draft.py` | SPEC, handle, scope_of | P05.04.b |
| `src/skm/modules/planning/application/commands/publish_revision.py` | SPEC, handle, scope_of | P05.04.c |
| `src/skm/modules/planning/application/commands/rebase_draft.py` | SPEC, handle, scope_of | P05.09.b |
| `src/skm/modules/planning/application/commands/restore_revision.py` | SPEC, handle, permissions_of, scope_of | P05.09.b |
| `src/skm/modules/planning/application/commands/save_draft.py` | SPEC, handle, scope_of | P05.04.b |
| `src/skm/modules/planning/application/publication_candidate.py` | PublicationCandidate, finding_to_json, prepare, prepare_publication_candidate, require_publishable, rule_failure_to_json | P05.04.c |
| `src/skm/modules/planning/application/queries/__init__.py` | package boundary | P00.04.c |
| `src/skm/modules/planning/application/queries/diff_revisions.py` | SPEC, handle, scope_of | P05.06 |
| `src/skm/modules/planning/application/queries/export_specification.py` | SPEC, handle, scope_of | P05.07 |
| `src/skm/modules/planning/application/queries/get_draft.py` | SPEC, handle, scope_of | P05.06 |
| `src/skm/modules/planning/application/queries/get_entity.py` | SPEC, handle, scope_of | P05.06 |
| `src/skm/modules/planning/application/queries/get_plan.py` | SPEC, handle, scope_of | P05.06 |
| `src/skm/modules/planning/application/queries/get_revision.py` | SPEC, handle, scope_of | P05.06 |
| `src/skm/modules/planning/application/queries/list_drafts.py` | SPEC, handle, scope_of | P05.06 |
| `src/skm/modules/planning/application/queries/list_entities.py` | SPEC, handle, scope_of | P05.06 |
| `src/skm/modules/planning/application/queries/list_plans.py` | SPEC, handle, scope_of | P05.06 |
| `src/skm/modules/planning/application/queries/list_revisions.py` | SPEC, handle, scope_of | P05.06 |
| `src/skm/modules/planning/application/queries/plan_stats.py` | SPEC, handle, scope_of | P05.06 |
| `src/skm/modules/planning/application/queries/preview_publication.py` | SPEC, handle, scope_of | P05.06 |
| `src/skm/modules/planning/application/queries/read_text.py` | SPEC, handle, scope_of | P05.06 |
| `src/skm/modules/planning/application/queries/ready_preview.py` | SPEC, handle, scope_of | P05.06 |
| `src/skm/modules/planning/application/queries/simulate.py` | Read-only simulation of pinned plan sources | P05.06 → I-11.4 |
| `src/skm/modules/planning/application/queries/resolve_plan_ref.py` | SPEC, handle, scope_of | P05.06 |
| `src/skm/modules/planning/application/queries/validate_draft.py` | SPEC, handle, scope_of | P05.06 |
| `src/skm/modules/planning/application/registry.py` | COMMANDS, QUERIES | P00.04.c → P05.04.b → P05.04.c → P05.06 → P05.07 → P05.09.b |
| `src/skm/modules/planning/application/revision_writer.py` | PinnedMaterial, WrittenRevision, extract_material_pins, resolve_publication_materials, write_revision | P06.04.a → P05.04.c |
| `src/skm/modules/planning/application/source_reader.py` | KIND_ORDER, LoadedSource, build_entity_outlines, build_tree, compute_entity_links, find_raw_entity, first_revision_no_of, read_source, require_plan, require_project | P05.06 |
| `src/skm/modules/planning/application/subscribers.py` | SUBSCRIBERS | P00.04.c → P05.04.a |
| `src/skm/modules/planning/application/validation_context.py` | build_validation_context | P05.03.b |
| `src/skm/modules/planning/domain/__init__.py` | package boundary | P00.04.c |
| `src/skm/modules/planning/domain/brief.py` | BriefChannel, BriefMessageKind, BriefMessage, Brief, Section | P00.04.c → P05.02.a |
| `src/skm/modules/planning/domain/canonical.py` | normalize_document, specification_digest, document_bytes | P00.04.c → P05.02.c |
| `src/skm/modules/planning/domain/changes.py` | ChangeOp, PatchChange, AddChange, RemoveChange, MoveChange, RekeyChange, ReplaceTextChange, ItemDefaults, ChangeOutcome, DraftChange | P00.04.c → P05.02.a |
| `src/skm/modules/planning/domain/check_spec.py` | CheckKind, CheckCategory, EvidencePolicy, Cwd, CommandDefinition, ShellDefinition, ManualDefinition, ExternalDefinition, CheckSpec | P00.04.c → P05.02.a |
| `src/skm/modules/planning/domain/compile_graph.py` | COMPILER_VERSION, TaskKind, CheckBinding, TaskNode, EdgeReason, TaskEdge, BatchGroup, ExecutionGraph | P00.04.c → P05.02.b |
| `src/skm/modules/planning/domain/criterion.py` | VerificationMode, Criterion | P00.04.c → P05.02.a |
| `src/skm/modules/planning/domain/decision.py` | DecisionState, DecisionOption, DecisionEvidence, DecisionOrigin, Decision | P00.04.c → P05.02.a |
| `src/skm/modules/planning/domain/diff.py` | FieldChange, EntityDiff, SpecDiff | P00.04.c → P05.06 |
| `src/skm/modules/planning/domain/display_keys.py` | KeyKind, DisplayKey | P00.04.c → P05.02.a |
| `src/skm/modules/planning/domain/draft.py` | Draft, DraftState | P00.04.c → P05.04.a |
| `src/skm/modules/planning/domain/events.py` | EVENT_TYPES | P00.04.c → P05.04.a |
| `src/skm/modules/planning/domain/execution_constraints.py` | PathRule, ExecutionConstraints | P00.04.c → P05.02.a |
| `src/skm/modules/planning/domain/id_space.py` | IdSpaceDocument | P00.04.c → P05.06 |
| `src/skm/modules/planning/domain/identity.py` | AssignedId | P00.04.c → P05.02.a |
| `src/skm/modules/planning/domain/item.py` | WorkKind, ModelClass, Effort, AuthorityKind, ChangeHint, ArtifactDecl, Relation, SkillReq, RouteFloor, Route, Routine, OwnerGate, ExternalGate, Authority, Research, Item | P00.04.c → P05.02.a |
| `src/skm/modules/planning/domain/material.py` | MaterialKind, MaterialStage, FreshnessPolicy, Freshness, must_refresh_expired, Selector, Material, MaterialRef | P00.04.c → P05.02.a |
| `src/skm/modules/planning/domain/material_status.py` | MaterialObservation, MaterialState, MaterialAssessment, assess_material | P00.04.c → P05.03.b |
| `src/skm/modules/planning/domain/member.py` | MemberRef, EntityLinks | P00.04.c → P05.04.c |
| `src/skm/modules/planning/domain/phase.py` | BatchMode, DesignState, Strategy, Batch, PhaseContract, Assurance, Phase | P00.04.c → P05.02.a |
| `src/skm/modules/planning/domain/plan.py` | PlanLifecycle, PlanPurpose, Plan | P00.04.c → P05.04.a |
| `src/skm/modules/planning/domain/plan_relation.py` | PlanRelationKind, PlanRelation | P00.04.c → P05.02.a |
| `src/skm/modules/planning/domain/reads.py` | ReadPurpose, RepositoryPathRead, MaterialRead, PlanEntityRead, ArtifactRead, ExternalSourceRead, Read | P00.04.c → P05.02.a |
| `src/skm/modules/planning/domain/ready_preview.py` | Lane, Waiting, LaneConflict, RouteGroup, ReadyPreview | P00.04.c → P05.02.b |
| `src/skm/modules/planning/domain/simulation.py` | Heuristic implementation effort ranges | P05.06 → I-11.4 |
| `src/skm/modules/planning/domain/rebase.py` | ConflictKind, RebaseConflict, RebaseResolution, RebaseOutcome | P00.04.c → P05.09.a |
| `src/skm/modules/planning/domain/rebase_helpers.py` | rebase id space owned by rebase.py: Absent, ABSENT, SideDoc, side_doc | P05.09.a |
| `src/skm/modules/planning/domain/references.py` | owner declarations | P00.04.c → P05.02.a |
| `src/skm/modules/planning/domain/scope.py` | Scope shared by phases and items | P05.02.a |
| `src/skm/modules/planning/domain/requirement.py` | Priority, RequirementSource, Requirement | P00.04.c → P05.02.a |
| `src/skm/modules/planning/domain/review_request.py` | CommitReviewTarget, WorkingTreeReviewTarget, ReviewRequestTarget, ReviewRequestSpec, build_review_request_document | P00.04.c → P05.10 |
| `src/skm/modules/planning/domain/review_requirement.py` | ReviewMode, Reviewer, RequiredReview, SelfReview, WaivedReview, ReviewRequirement | P00.04.c → P05.02.a |
| `src/skm/modules/planning/domain/revision.py` | RevisionOrigin, RevisionMeta | P00.04.c → P05.04.a |
| `src/skm/modules/planning/domain/specification.py` | EntityKind, SpecEntity, Specification | P00.04.c → P05.02.a |
| `src/skm/modules/planning/domain/stats.py` | PlanStats | P00.04.c → P05.06 |
| `src/skm/modules/planning/domain/templates.py` | parse_bodies, render_template, validate_inputs, validate_schema | P09.08 |
| `src/skm/modules/planning/domain/text_edits.py` | text edit application, TEXT_EDIT_FIELDS | P05.02.a |
| `src/skm/modules/planning/domain/unit.py` | UnitKind, UnitMode, WriteScopeEntry, OutputEntry, UnitCommand, Unit | P00.04.c → P05.02.a |
| `src/skm/modules/planning/domain/validation/__init__.py` | package boundary | P00.04.c → P05.03.a |
| `src/skm/modules/planning/domain/validation/context.py` | FileVersionStatus, FileVersionObservation, ValidationContext | P00.04.c → P05.03.a |
| `src/skm/modules/planning/domain/validation/findings.py` | Severity, Finding, RuleFailure, ValidationReport | P00.04.c → P05.03.a |
| `src/skm/modules/planning/domain/validation/globs.py` | globs_overlap, covers, bare | P00.04.c → P05.03.a |
| `src/skm/modules/planning/domain/validation/pipeline.py` | Rule, PluginRule, DEFAULT_RULES, validate | P00.04.c → P05.03.a |
| `src/skm/modules/planning/domain/validation/rules_acceptance.py` | criterion_unlinked, criterion_check_mismatch, requirement_unimplemented, criterion_missing | P00.04.c → P05.03.a |
| `src/skm/modules/planning/domain/validation/rules_checks.py` | unit_command_missing, check_cadence, check_duplicate_command, check_manual_rerun_after_integration | P00.04.c → P05.03.a |
| `src/skm/modules/planning/domain/validation/rules_context.py` | scope_ambiguous, context_unbound, brief_duplicate, context_heavy, execution_prompt_heavy, material_unavailable, material_stale | P00.04.c → P05.03.a |
| `src/skm/modules/planning/domain/validation/rules_decisions.py` | decision_fields, decision_superseded_orphan | P00.04.c → P05.03.a |
| `src/skm/modules/planning/domain/validation/rules_dependencies.py` | dependency_cycle, batch_foreign, batch_multiple, batch_unassigned, batch_order_conflict | P00.04.c → P05.03.a |
| `src/skm/modules/planning/domain/validation/rules_readiness.py` | incomplete, phase_skeleton, context_default, research_question_missing | P00.04.c → P05.03.a |
| `src/skm/modules/planning/domain/validation/rules_references.py` | self_reference, ref_unknown, artifact_duplicate, artifact_path_mismatch, plan_relation_unresolved | P00.04.c → P05.03.a |
| `src/skm/modules/planning/domain/validation/rules_review.py` | review_reviewer_unset | P00.04.c → P05.03.a |
| `src/skm/modules/planning/domain/validation/rules_routing.py` | route_unknown_runtime, route_unknown_model, skill_unknown | P00.04.c → P05.03.a |
| `src/skm/modules/planning/domain/validation/rules_scope.py` | mount_unknown, write_scope_overlap, write_scope_overlap_cross_item, write_scope_uncovered, write_scope_empty, write_scope_no_tests, forbidden_path_conflict | P00.04.c → P05.03.a |
| `src/skm/modules/planning/domain/validation/rules_structure.py` | duplicate_id, duplicate_key, key_prefix_mismatch, entity_kind_changed | P00.04.c → P05.03.a |
| `src/skm/modules/planning/domain/work_policy.py` | WorkPolicyOverride | P00.04.c → P05.02.a |
| `src/skm/modules/planning/host/__init__.py` | package boundary | P00.04.c |
| `src/skm/modules/planning/host/registry.py` | HOST_OPERATIONS | P00.04.c.a |
| `src/skm/modules/planning/module.py` | MODULE | P00.04.c → P05.04.a |
| `src/skm/modules/planning/permissions.py` | PERMISSIONS | P00.04.c → P05.04.a |
| `src/skm/modules/planning/ports.py` | Digest, AliasKind, PlanRepository, PlanCounters, DraftRepository, MaterialPin, RevisionRecord, RevisionRepository, PlanningQueries | P00.04.c → P05.04.a → P06.04.a |
| `src/skm/modules/planning/public.py` | get_revision_specification, get_revision_meta, compile_execution_graph, resolve_entity, revision_materials, assess_material, require_active_plan, get_plan_ref, get_plan_summary, validate_revision, publish_review_request_revision, SpecificationDoc, RevisionMetaView, PlanRef, PlanView, EntityRef, CommitReviewTarget, WorkingTreeReviewTarget, ReviewRequestTarget, ReviewRequestSpec, DraftId (reexport of existing domain.draft type) | P00.04.c → P05.04.a → P05.10 → P06.04.b |
| `src/skm/modules/planning/settings.py` | SECTION_URN, SECTION_URNS | P00.04.c → P02.02 → P05.08 |
| `tests/unit/planning/domain/test_draft_rebase_contracts.py` | test_draft_is_a_frozen_slotted_aggregate, conflict_validator, conflict, test_rebase_conflict_accepts_entity_kind_or_null, test_rebase_conflict_rejects_display_keys_and_invalid_kinds | P00.04.c → P05.04.a → P05.10 → P06.04.b |
| `src/skm/modules/policy/__init__.py` | package boundary | P00.04.c |
| `src/skm/modules/policy/application/__init__.py` | package boundary | P00.04.c |
| `src/skm/modules/policy/application/commands/__init__.py` | package boundary | P00.04.c → P07.01.b |
| `src/skm/modules/policy/application/commands/approve_intent.py` | SPEC, handle | P07.01.b |
| `src/skm/modules/policy/application/commands/deny_intent.py` | SPEC, handle | P07.01.b |
| `src/skm/modules/policy/application/commands/expire_intents.py` | SPEC, handle | P07.01.b |
| `src/skm/modules/policy/application/commands/propose_intent.py` | SPEC, handle | P07.01.b |
| `src/skm/modules/policy/application/commands/record_intent_outcome.py` | SPEC, handle | P07.01.b |
| `src/skm/modules/policy/application/commands/record_tool_decisions.py` | SPEC, handle | P07.01.b |
| `src/skm/modules/policy/application/commands/start_intent_execution.py` | SPEC, handle | P07.01.b |
| `src/skm/modules/policy/application/composition.py` | SHELL_FREE_TOOLS, ConfigReader, builtin_profiles, ceiling_layer, compose_effective, denylist_pattern, forbidden_paths_layer, resolve_profile, restriction_layers, task_authority_from | P07.01.a |
| `src/skm/modules/policy/application/queries/__init__.py` | package boundary | P00.04.c → P07.01.b |
| `src/skm/modules/policy/application/queries/check_tool_call.py` | SPEC, handle | P07.01.b |
| `src/skm/modules/policy/application/queries/effective_permissions.py` | SPEC, handle | P07.01.b |
| `src/skm/modules/policy/application/queries/explain_permissions.py` | SPEC, handle | P07.01.b |
| `src/skm/modules/policy/application/queries/get_intent.py` | SPEC, handle | P07.01.b |
| `src/skm/modules/policy/application/queries/list_intents.py` | SPEC, handle | P07.01.b |
| `src/skm/modules/policy/application/queries/list_profiles.py` | SPEC, handle | P07.01.b |
| `src/skm/modules/policy/application/registry.py` | COMMANDS, QUERIES | P00.04.c → P07.01.b |
| `src/skm/modules/policy/application/subscribers.py` | SUBSCRIBERS | P00.04.c → P07.01.b |
| `src/skm/modules/policy/domain/__init__.py` | package boundary | P00.04.c |
| `src/skm/modules/policy/domain/allowlist.py` | SAFE_PREFIX_VAR_RE, SHELL_KEYWORDS, UNSAFE_VAR_RE, segment_allowlisted | P07.01.a |
| `src/skm/modules/policy/domain/approval.py` | ApprovalDecision, Approval | P00.04.c → P07.01.b |
| `src/skm/modules/policy/domain/classify.py` | OperationHit | P00.04.c → P07.01.a |
| `src/skm/modules/policy/domain/command_classes.py` | CARRIER_HEADS, DELETE_HEADS, DOCKER_HEADS, DOCKER_SOCKETS, EXTERNAL_SERVICE_HEADS, FORGE_GH_NOUNS, FORGE_GH_VERBS, FORGE_GLAB_NOUNS, FORGE_GLAB_VERBS, INLINE_FLAGS, INSTALL_RULES, NETWORK_HEADS, PUBLISH_RULES, SECRET_BASENAME_EXCEPTIONS, SECRET_BASENAME_GLOBS, SECRET_COMMANDS, SECRET_HOME_GLOBS, WRITE_HEADS | P07.01.a |
| `src/skm/modules/policy/domain/commands.py` | CommandMode, CommandRule, CommandPolicy | P00.04.c → P07.01.a |
| `src/skm/modules/policy/domain/events.py` | EVENT_TYPES | P00.04.c → P07.01.b |
| `src/skm/modules/policy/domain/git_guard.py` | GitViolation | P00.04.c → P07.01.a |
| `src/skm/modules/policy/domain/network.py` | NetworkMode, NetworkPolicy | P00.04.c → P07.01.a |
| `src/skm/modules/policy/domain/operations.py` | OperationName, OperationDecision, Requirement, AccessCapability, PathOrigin, OperationRule, TaskAuthority, StaticPathFacts | P00.04.c → P07.01.a |

## Research ledger implementation

| File | Contracts | Owner |
|---|---|---|
| `src/skm/modules/context/application/commands/record_research_result.py` | SPEC, handle, scope_of | P09.09.a |
| `src/skm/modules/context/application/queries/find_research_cache.py` | SPEC, handle, scope_of, live research authorization and visibility | P09.09.a |
| `src/skm/modules/context/application/queries/get_research_query.py` | SPEC, handle, scope_of | P09.09.a |
| `src/skm/modules/context/application/queries/list_external_sources.py` | SPEC, handle, scope_of | P09.09.a |
| `src/skm/adapters/memory/context/research.py` | MemoryResearchRepository | P09.09.a |
| `src/skm/adapters/postgres/context/research.py` | PostgresResearchRepository; reserved JSON storage metadata preserves cache-hit delivery without changing nullable public usage | P09.09.a → P09.09.b |

| `src/skm/modules/execution/application/research_access.py` | require_assignment, require_step_scope | P09.09.a |
| `src/skm/modules/access/application/research_access.py` | workspace_ceiling | P09.09.a |

| Host research adapter | Contract | Owner |
|---|---|---|
| `src/skm/adapters/research/command.py` | CommandResearchSource, ProcessSession, PolicyReply, admit_reply, decode_reply, validate_urls; bounded pidfd-owned command/DNS sessions | P09.09.b |
| `src/skm/adapters/research/filesystem.py` | FilesystemResearchSource; no-follow descriptor confinement, git visibility, bounded local matching and checkout fingerprint | P09.09.b |
| `src/skm/adapters/research/mcp_stdio.py` | McpStdioResearchSource; cancellable MCP initialize/tools/call | P09.09.b |
| `src/skm/adapters/research/retry.py` | ResearchSources, SourceBusy, SourceFailed, with_retry; bounded attempts, source gate and injected clock/identifier dependencies | P09.09.b |
| `src/skm/entrypoints/cli/commands/research.py` | GROUP, register; host research query/sources and stored query inspection | P09.09.b |

## P08.12: approved autopilot queue

| File | Responsibility | Owner |
|---|---|---|
| `src/skm/entrypoints/cli/commands/autopilot.py` | Persisted campaign control and approved queue surface | P08.12 |
| `src/skm/modules/execution/application/commands/start_autopilot.py` | Persisted campaign control and approved queue surface | P08.12 |
| `src/skm/modules/execution/application/commands/pause_autopilot.py` | Persisted campaign control and approved queue surface | P08.12 |
| `src/skm/modules/execution/application/commands/drain_autopilot.py` | Persisted campaign control and approved queue surface | P08.12 |
| `src/skm/modules/execution/application/commands/stop_autopilot.py` | Persisted campaign control and approved queue surface | P08.12 |
| `src/skm/modules/execution/application/commands/autopilot_tick.py` | Persisted campaign control and approved queue surface | P08.12 |
| `src/skm/modules/execution/application/queries/get_autopilot_status.py` | Persisted campaign control and approved queue surface | P08.12 |
| `src/skm/modules/execution/application/queries/explain_autopilot.py` | Persisted campaign control and approved queue surface | P08.12 |

Session continuation preserves counters, start time, blockers and narrowed limits. Ticks lock the
campaign before runs, classify AP1-AP20 in order and call existing run commands in the same UoW.
AutopilotStateChanged uses the project stream; follow selects that stream and the current run.
Review status: not_requested (executor self-check is separate from independent review).

Before a project's first real run, owner-required stops have no run FK for DecisionRequest.
The campaign stops with an explicit owner-required stop_detail and project event; no synthetic
run is created. A project-only inbox request requires an owner change to the DecisionRequest
contract/persistence outside P08.12's write set. Once a current/latest real run exists, stops
create a deduplicated owner escalation on it in the same transaction.
