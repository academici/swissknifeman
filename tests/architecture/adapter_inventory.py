"""Concrete adapter exports admitted by their implementation owners."""

_ADAPTER_IMPLEMENTATIONS = {
    "skm.adapters.sandbox": {"SeatbeltSandbox"},
    "skm.adapters.sandbox.bubblewrap": {"BubblewrapSandbox"},
    "skm.adapters.sandbox.seatbelt": {"SeatbeltSandbox"},
    "skm.adapters.git.output_writer": {"PreSealSnapshot"},
    "skm.adapters.exports.obsidian.vault_fs": {"LocalVaultFs"},
    "skm.adapters.http_client.worker_config": {"RemoteWorkerConfig"},
    "skm.adapters.memory.exports.repositories": {"MemoryVaultNoteRepository"},
    "skm.adapters.memory.exports.state": {"NoteState"},
    "skm.adapters.postgres.exports.repositories": {"PostgresVaultNoteRepository"},
    "skm.adapters.http_client.auth": {"BearerHeaders"},  # P11.04.a
    "skm.adapters.http_client.client": {"HttpSkmClient"},  # P11.04.a
    "skm.adapters.http_client.live": {"LivePublisher"},  # P11.03.b
    "skm.adapters.http_client.spool": {
        "BoundedLocalSpool",
        "HistoricalObservation",
        "ReplayReport",
        "SpoolEntry",
        "SpoolItemKind",
    },  # I-10.2
    "skm.adapters.postgres.core.schema_version": {"PostgresSchemaVersionReader"},  # P11.01.a
    "skm.adapters.event_sinks._pinned_http": {"PinnedHttpClient", "HttpRefused"},  # P10.08.b
    "skm.adapters.event_sinks.webhook": {"WebhookSink"},  # P10.08.b
    "skm.adapters.host_commands.subprocess_runner": {
        "SubprocessHostCommandRunner",
        "LocalSubscriptionState",
    },  # P10.08.b
    "skm.adapters.http_client.research": {"ResearchHttpTransport"},  # I-11.2
    "skm.adapters.research.codegraph": {"NativeCodeGraphAdapter"},  # I-09.3
    "skm.adapters.research.command": {"CommandResearchSource", "ProcessSession", "PolicyReply"},  # P09.09.b
    "skm.adapters.research.filesystem": {"FilesystemResearchSource"},  # P09.09.b
    "skm.adapters.research.mcp_stdio": {"McpStdioResearchSource"},  # P09.09.b
    "skm.adapters.research.providers": {
        "Context7ResearchSource",
        "PerplexityApiResearchSource",
        "PerplexityWebResearchSource",
        "WebSearchResearchSource",
    },  # I-11.2
    "skm.adapters.research.retry": {"ResearchSources", "SourceBusy", "SourceFailed"},  # P09.09.b
    "skm.adapters.git.hook_state": {"LocalHookState"},  # P10.05.a
    "skm.adapters.git.identity_proof": {"IdentityProofCache"},  # P10.05.a
    "skm.adapters.blobs.local.materializer": {  # P06.05
        "LocalMaterialWriter",
        "LocalUploadSourceReader",
    },
    "skm.adapters.blobs.local.store": {"LocalBlobStore"},  # P06.02
    "skm.adapters.checkout_fs.docs": {"LocalDocsCheckoutFs"},  # P13.04.c
    "skm.adapters.checkout_fs.local": {"LocalCheckoutFs"},  # P10.01.c
    "skm.adapters.checkout_fs.user_home": {"LocalUserHomeReader"},  # P10.07
    "skm.adapters.execution.context_owner": {"ExecutionContextOwnerGuard"},  # P09.04.d
    "skm.adapters.git.excludes": {"GitInfoExcludes"},  # I-09.1
    "skm.adapters.git.host_inputs": {"GitCheckoutReader"},  # P09.04.c
    "skm.adapters.git.repo_inspect": {"GitRepositoryInspector"},  # P04.06
    "skm.adapters.git.runner": {"GitCommandFailed", "GitResult", "GitRunner"},  # P04.06
    "skm.adapters.integrations.antigravity.target": {"AntigravityTarget"},
    "skm.adapters.integrations.claude_code.session_summary": {"SessionSummarySpool"},  # P13.03.c
    "skm.adapters.integrations.claude_code.settings": {"ClaudeRules"},  # P10.02
    "skm.adapters.integrations.claude_code.target": {"ClaudeCodeTarget"},  # P10.02
    "skm.adapters.integrations.codex.permissions": {"CodexMode"},  # P10.03
    "skm.adapters.integrations.codex.target": {"CodexTarget"},  # P10.03
    "skm.adapters.integrations.cursor.permissions": {"CursorRules"},  # P10.04.a
    "skm.adapters.integrations.cursor.target": {"CursorTarget"},  # P10.04.a
    "skm.adapters.integrations.gemini_cli.target": {"GeminiCliTarget"},
    "skm.adapters.integrations.grok.target": {"GrokTarget"},  # P10.04.b
    "skm.adapters.integrations.registry": {"StaticIntegrationTargetRegistry"},  # P10.02
    "skm.adapters.http_client.router_upstream": {"RouterUpstream", "UpstreamError", "UpstreamResponse"},
    "skm.adapters.knowledge.manifest_readers.composer_json": {"ComposerJsonReader"},
    "skm.adapters.knowledge.manifest_readers.package_json": {"PackageJsonReader"},
    "skm.adapters.knowledge.manifest_readers.pyproject": {"PyprojectReader"},
    "skm.adapters.knowledge.serena_reader": {"SerenaCodeGraphReader"},
    "skm.adapters.knowledge.context_source": {"KnowledgeMemoryRetriever"},  # P13.01.b
    "skm.adapters.memory.knowledge.graph": {"MemoryGraphRepository"},  # P13.02.a
    "skm.adapters.memory.knowledge.lessons": {"MemoryLessonRepository"},  # P13.01.b
    "skm.adapters.memory.knowledge.mapping": {"MemoryKnowledgeState"},  # P13.01.b
    "skm.adapters.memory.knowledge.memory": {"MemoryMemoryRepository"},  # P13.01.b
    "skm.adapters.memory.knowledge.repositories": {"MemoryLessonRepository", "MemoryMemoryRepository"},
    "skm.adapters.postgres.knowledge.graph": {"PostgresGraphRepository"},  # P13.02.a
    "skm.adapters.memory.learning.activity": {"MemoryActivityRecordRepository"},
    "skm.adapters.memory.learning.repositories": {
        "MemoryActivityRecordRepository",
        "MemoryCandidateRepository",
        "MemoryCandidateProposalRepository",
        "MemoryCandidateReviewRepository",
        "MemorySignalRepository",
    },
    "skm.adapters.postgres.learning.activity": {"PostgresActivityRecordRepository"},
    "skm.adapters.postgres.learning.candidates": {"PostgresCandidateRepository"},
    "skm.adapters.postgres.learning.repositories": {
        "PostgresActivityRecordRepository",
        "PostgresCandidateProposalRepository",
        "PostgresCandidateReviewRepository",
        "PostgresSignalRepository",
    },
    "skm.adapters.memory.learning.candidates": {"MemoryCandidateRepository"},  # P13.03.b
    "skm.adapters.memory.learning.proposals": {"MemoryCandidateProposalRepository"},  # P13.03.b
    "skm.adapters.memory.learning.reviews": {"MemoryCandidateReviewRepository"},  # P13.03.b
    "skm.adapters.memory.learning.signals": {"MemorySignalRepository"},  # P13.03.b
    "skm.adapters.postgres.knowledge.lessons": {"PostgresLessonRepository"},  # P13.01.b
    "skm.adapters.postgres.knowledge.memory": {"PostgresMemoryRepository"},  # P13.01.b
    "skm.adapters.postgres.knowledge.repositories": {"PostgresLessonRepository", "PostgresMemoryRepository"},
    "skm.adapters.knowledge.null_retriever": {"NullMemoryRetriever"},
    "skm.adapters.knowledge.local_sqlite_memory": {"LocalSqliteMemoryStore"},  # I-09.4
    "skm.adapters.memory.access.pairing": {"MemoryPairingRepository"},
    "skm.adapters.memory.access.sessions": {"MemoryWebSessionRepository"},
    "skm.adapters.memory.access.repositories": {  # P04.02.a
        "MemoryIdentityRepository",
        "MemoryMembershipRepository",
        "MemoryPrincipalRepository",
        "MemoryTokenRepository",
    },
    "skm.adapters.memory.access.state": {"MemoryAccessState"},  # P04.02.a
    "skm.adapters.memory.artifacts.blob_coordination": {  # P06.03.c
        "MemoryBlobCoordination",
        "MemoryBlobDigestLock",
    },
    "skm.adapters.memory.artifacts.repositories": {  # P06.03.a
        "MemoryAccessGrantRepository",
        "MemoryBlobContentReader",
        "MemoryBlobRepository",
        "MemoryFileRepository",
        "MemoryFileVersionRepository",
        "MemoryStagedBlobRepository",
    },
    "skm.adapters.memory.artifacts.state": {"BlobStoreRef", "MemoryArtifactsState"},  # P06.03.a
    "skm.adapters.resources.builtin_packs": {"PackagedBuiltinPacks"},  # P09.01.a
    "skm.adapters.resources.compiled_pack": {"PackLock"},  # I-09.2a
    "skm.adapters.resources.pack_reader": {"FilesystemPackReader"},  # P09.01.b
    "skm.adapters.resources.upstream_http": {"HttpUpstreamFetcher"},  # P09.01.c
    "skm.adapters.runtimes": {"LocalProxyBridge", "ProxyEndpoint"},
    "skm.adapters.runtimes._cli_session.proxy_bridge": {"LocalProxyBridge", "ProxyEndpoint"},
    "skm.adapters.runtimes.antigravity.runtime": {"AntigravityRuntime"},
    "skm.adapters.runtimes.claude_code.runtime": {"ClaudeCodeRuntime"},  # P08.03
    "skm.adapters.runtimes.codex.runtime": {"CodexRuntime"},  # P08.04
    "skm.adapters.runtimes.cursor.runtime": {"CursorRuntime"},  # P08.05
    "skm.adapters.runtimes.fake.runtime": {"FakeRuntime"},  # P08.02.a
    "skm.adapters.runtimes.fake.scenarios": {"Scenario", "ScenarioError"},  # P08.02.a
    "skm.adapters.runtimes.gemini_cli.runtime": {"GeminiCliRuntime"},
    "skm.adapters.runtimes.grok.runtime": {"GrokRuntime"},  # P08.05
    "skm.adapters.runtimes.interactive": {"InteractiveLauncher", "InteractiveSession"},  # I-08.3
    "skm.adapters.runtimes.pool": {
        "AdaptiveExecutorRouter",
        "FailoverCandidate",
        "FailoverController",
        "FailoverDecision",
        "FailoverPolicy",
        "ProviderPoolManager",
        "ProviderSlot",
        "QuotaGroup",
        "QuotaProber",
        "QuotaReading",
        "QuotaReply",
        "SessionPin",
        "SlotLease",
    },
    "skm.adapters.runtimes.pool.adaptive_router": {"AdaptiveExecutorRouter"},
    "skm.adapters.runtimes.pool.failover": {
        "FailoverCandidate",
        "FailoverController",
        "FailoverDecision",
        "FailoverPolicy",
    },  # I-07.3
    "skm.adapters.runtimes.pool.quota_prober": {"QuotaGroup", "QuotaProber", "QuotaReading", "QuotaReply"},
    "skm.adapters.runtimes.pool.provider_pool": {
        "ProviderPoolManager",
        "ProviderSlot",
        "SessionPin",
        "SlotLease",
        "SlotModel",
        "SlotRuntimeConfig",
    },
    "skm.adapters.runtimes.pool.rate_limit": {"RateLimitAction", "RateLimitDecision"},
    "skm.adapters.runtimes.pool.shallow_home": {"ShallowHome"},
    "skm.adapters.runtimes.router.cli_bridge": {
        "CliBridge",
        "CliRequest",
        "CliResult",
        "CliUnavailable",
        "ConversationBusy",
        "InternalHop",
    },
    "skm.adapters.runtimes.router.dedup": {"Inflight"},
    "skm.adapters.runtimes.router.scheduler": {"Route", "Scheduler"},
    "skm.adapters.host_commands.local_gate": {"LocalUserSchemaValidator", "SubprocessGateRunner"},
    "skm.adapters.memory.blob_store": {"MemoryBlobStore"},  # P06.02
    "skm.adapters.memory.config_store": {"MemoryConfigStore"},
    "skm.adapters.memory.context.research": {"MemoryResearchRepository"},  # P09.09.a
    "skm.adapters.memory.context.repositories": {  # P09.04.a
        "MemoryContextRepository",
        "MemoryResearchRepository",
        "MemoryTextStore",
    },
    "skm.adapters.memory.core.audit": {"MemoryAuditLog", "MemoryConsumerReceipts"},
    "skm.adapters.memory.core.storage_inspector": {"MemoryStorageInspector"},
    "skm.adapters.memory.core.events": {"MemoryEventReader"},
    "skm.adapters.memory.core.idempotency": {"MemoryIdempotencyStore"},
    "skm.adapters.memory.core.outbox": {"MemoryOutboxStore"},
    "skm.adapters.memory.core.scopes": {"MemoryScopeRegistry", "MemoryScopeTree"},
    "skm.adapters.memory.core.state": {"ClockRef", "MemoryBackendState", "MemoryCoreState", "OutboxRecord"},
    "skm.adapters.memory.execution.assignments": {  # P07.05.a
        "MemoryAssignmentRepository",
        "MemoryEnvironmentRepository",
        "MemoryOutputRepository",
    },
    "skm.adapters.memory.execution.attempts_stages": {  # P07.05.a
        "MemoryAttemptRepository",
        "MemoryStageRepository",
        "MemoryStepRepository",
    },
    "skm.adapters.memory.execution.budgets_decisions_effects": {  # P07.05.a
        "MemoryBudgetRepository",
        "MemoryDecisionRepository",
        "MemoryEffectRepository",
    },
    "skm.adapters.memory.execution.checks_reviews": {  # P07.05.a
        "MemoryAcceptanceRepository",
        "MemoryCheckRepository",
        "MemoryReviewRepository",
    },
    "skm.adapters.memory.execution.misc_repos": {  # P07.05.a
        "MemoryAutopilotRepository",
        "MemoryEvidenceBindingRepository",
        "MemoryIntegrationSlotRepository",
        "MemoryRecoveryRepository",
        "MemoryReviewRequestRepository",
    },
    "skm.adapters.memory.execution.queries": {"MemoryExecutionQueries"},  # P07.05.a
    "skm.adapters.memory.execution.queries_views": {"MemoryExecutionQueries"},  # P07.05.a
    "skm.adapters.memory.execution.repositories": {  # P07.05.a
        "MemoryAcceptanceRepository",
        "MemoryAssignmentRepository",
        "MemoryAttemptRepository",
        "MemoryAutopilotRepository",
        "MemoryBudgetRepository",
        "MemoryBundleRepository",
        "MemoryCheckRepository",
        "MemoryDecisionRepository",
        "MemoryEffectRepository",
        "MemoryEnvironmentRepository",
        "MemoryEvidenceBindingRepository",
        "MemoryIntegrationSlotRepository",
        "MemoryOutputRepository",
        "MemoryReadinessRepository",
        "MemoryRecoveryRepository",
        "MemoryReviewRepository",
        "MemoryReviewRequestRepository",
        "MemoryRunRepository",
        "MemoryStageRepository",
        "MemoryStepRepository",
        "MemoryTaskRepository",
    },
    "skm.adapters.memory.execution.runs_tasks": {  # P07.05.a
        "MemoryBundleRepository",
        "MemoryReadinessRepository",
        "MemoryRunRepository",
        "MemoryTaskRepository",
    },
    "skm.adapters.memory.execution.state": {"MemoryExecutionState"},  # P07.05.a
    "skm.adapters.memory.extensions.mapping": {"MemoryExtensionsState", "QuarantineRow"},  # P09.01.a
    "skm.adapters.memory.extensions.repositories": {  # P09.01.a
        "MemoryPackRepository",
        "MemoryQuarantineRepository",
        "MemoryResourceRepository",
    },
    "skm.adapters.memory.integrations.repositories": {"MemoryProjectionRepository"},  # P10.01.b
    "skm.adapters.memory.integrations.state": {  # P10.01.b
        "MemoryIntegrationsState",
        "StoredProjection",
    },
    "skm.adapters.memory.planning.queries": {"MemoryPlanningQueries"},  # P05.05.b
    "skm.adapters.memory.planning.repositories": {  # P05.04.b
        "MemoryDraftRepository",
        "MemoryPlanCounters",
        "MemoryPlanRepository",
        "MemoryRevisionRepository",
    },
    "skm.adapters.memory.planning.state": {  # P05.04.b
        "MemoryPlanningState",
        "StoredIdentity",
        "StoredRevision",
    },
    "skm.adapters.memory.settings.repositories": {  # P02.07.b
        "MemoryConfigEntryRepository",
        "MemoryConfigGenerationCounter",
        "MemoryConfigHistoryRepository",
        "MemorySettingsState",
    },
    "skm.adapters.memory.policy.repositories": {  # P07.01.b
        "MemoryApprovalRepository",
        "MemoryDecisionAuditRepository",
        "MemoryToolIntentRepository",
    },
    "skm.adapters.memory.policy.state": {"MemoryPolicyState"},  # P07.01.b
    "skm.adapters.memory.runtimes.repositories": {  # P08.01.b
        "MemoryCapabilityVerificationRepository",
        "MemoryHostModelAvailabilityRepository",
        "MemoryHostRuntimeRepository",
        "MemoryModelCatalogRepository",
    },
    "skm.adapters.memory.runtimes.state": {  # P08.01.b
        "MemoryRuntimesState",
        "StoredVerification",
    },
    "skm.adapters.memory.uow": {"InMemoryBackend", "InMemoryUnitOfWork", "InMemoryUowFactory"},
    "skm.adapters.memory.workspace.repositories": {  # P04.04.a
        "MemoryCheckoutBindingRepository",
        "MemoryHostRepository",
        "MemoryMountRepository",
        "MemoryProjectRepository",
        "MemoryRepositoryRepository",
        "MemoryWorkerHostLookup",
        "MemoryWorkerRepository",
        "MemoryWorkspaceRepository",
    },
    "skm.adapters.memory.workspace.state": {"MemoryWorkspaceState"},  # P04.04.a
    "skm.adapters.postgres.access.pairing": {"PostgresPairingRepository"},
    "skm.adapters.postgres.access.sessions": {"PostgresWebSessionRepository"},
    "skm.adapters.postgres.access.repositories": {  # P04.02.b
        "PostgresIdentityRepository",
        "PostgresMembershipRepository",
        "PostgresPrincipalRepository",
        "PostgresTokenRepository",
    },
    "skm.adapters.postgres.artifacts.blob_coordination": {  # P06.03.c
        "PostgresBlobCoordination",
        "PostgresBlobDigestLock",
    },
    "skm.adapters.postgres.artifacts.blobs": {  # P06.03.b
        "PostgresBlobContentReader",
        "PostgresBlobRepository",
        "PostgresStagedBlobRepository",
    },
    "skm.adapters.postgres.artifacts.files": {  # P06.03.b
        "PostgresFileRepository",
        "PostgresFileVersionRepository",
    },
    "skm.adapters.postgres.artifacts.grants": {"PostgresAccessGrantRepository"},  # P06.03.b
    "skm.adapters.postgres.artifacts.repositories": {  # P06.03.b compatibility facade
        "PostgresAccessGrantRepository",
        "PostgresBlobContentReader",
        "PostgresBlobRepository",
        "PostgresFileRepository",
        "PostgresFileVersionRepository",
        "PostgresStagedBlobRepository",
    },
    "skm.adapters.postgres.machine": {"PostgresMachineStore"},  # SKM 0.1.0 S01
    "skm.adapters.postgres.config_store": {"PostgresConfigStore", "PostgresScopeTree"},  # P03.06
    "skm.adapters.postgres.context.research": {"PostgresResearchRepository"},  # P09.09.a
    "skm.adapters.postgres.context.repositories": {  # P09.04.a
        "PostgresContextRepository",
        "PostgresResearchRepository",
        "PostgresTextStore",
    },
    "skm.adapters.postgres.core.audit": {"PostgresAuditLog"},  # P03.03.b
    "skm.adapters.postgres.core.consumer_receipts": {"PostgresConsumerReceipts"},  # P03.05
    "skm.adapters.postgres.core.storage_inspector": {"PostgresStorageInspector"},
    "skm.adapters.postgres.core.events_store": {"PostgresEventReader", "PostgresEventWriter"},  # P03.03.a
    "skm.adapters.postgres.core.idempotency": {"PostgresIdempotencyStore"},  # P03.03.b
    "skm.adapters.postgres.core.outbox": {"PostgresOutboxStore"},  # P03.05
    "skm.adapters.postgres.core.scopes": {"PostgresScopeRegistry", "PostgresScopeTree"},  # P03.02
    "skm.adapters.postgres.events": {"EventListener"},  # P11.03.a
    "skm.adapters.postgres.execution.acceptance": {"PostgresAcceptanceRepository"},  # P07.05.a
    "skm.adapters.postgres.execution.assignments": {"PostgresAssignmentRepository"},  # P07.05.a
    "skm.adapters.postgres.execution.attempts_stages": {  # P07.05.a
        "PostgresAttemptRepository",
        "PostgresStageRepository",
    },
    "skm.adapters.postgres.execution.autopilot_recovery": {  # P07.05.a
        "PostgresAutopilotRepository",
        "PostgresEvidenceBindingRepository",
        "PostgresRecoveryRepository",
    },
    "skm.adapters.postgres.execution.budgets": {"PostgresBudgetRepository"},  # P07.05.a
    "skm.adapters.postgres.execution.checks_reviews": {  # P07.05.a
        "PostgresCheckRepository",
        "PostgresReviewRepository",
    },
    "skm.adapters.postgres.execution.decisions_effects": {  # P07.05.a
        "PostgresDecisionRepository",
        "PostgresEffectRepository",
    },
    "skm.adapters.postgres.execution.environments_outputs": {  # P07.05.a
        "PostgresEnvironmentRepository",
        "PostgresOutputRepository",
    },
    "skm.adapters.postgres.execution.integration_slots": {  # P07.05.a
        "PostgresIntegrationSlotRepository",
        "PostgresReviewRequestRepository",
    },
    "skm.adapters.postgres.execution.queries": {"PostgresExecutionQueries"},  # P07.05.a
    "skm.adapters.postgres.execution.repositories": {  # P07.05.a
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
    },
    "skm.adapters.postgres.execution.runs_tasks": {  # P07.05.a
        "PostgresBundleRepository",
        "PostgresReadinessRepository",
        "PostgresRunRepository",
    },
    "skm.adapters.postgres.execution.steps": {"PostgresStepRepository"},  # P07.05.a
    "skm.adapters.postgres.execution.tasks": {"PostgresTaskRepository"},  # P07.05.a
    "skm.adapters.postgres.extensions.pack_config_source": {  # P09.03
        "PackConnectionSlot",
        "PostgresPackConfigSource",
    },
    "skm.adapters.postgres.extensions.repositories": {  # P09.01.a
        "PostgresPackRepository",
        "PostgresQuarantineRepository",
        "PostgresResourceRepository",
    },
    "skm.adapters.postgres.integrations.repositories": {"PostgresProjectionRepository"},  # P10.01.b
    "skm.adapters.postgres.planning.counters": {"PostgresPlanCounters"},  # P05.05.b
    "skm.adapters.postgres.planning.drafts": {"PostgresDraftRepository"},  # P05.05.b
    "skm.adapters.postgres.planning.plans": {"PostgresPlanRepository"},  # P05.05.b
    "skm.adapters.postgres.planning.queries": {"PostgresPlanningQueries"},  # P05.05.b
    "skm.adapters.postgres.planning.revisions": {"PostgresRevisionRepository"},  # P05.05.b
    "skm.adapters.postgres.policy.approvals": {"PostgresApprovalRepository"},  # P07.01.b
    "skm.adapters.postgres.policy.audit": {"PostgresDecisionAuditRepository"},  # P07.01.b
    "skm.adapters.postgres.policy.intents": {"PostgresToolIntentRepository"},  # P07.01.b
    "skm.adapters.postgres.runtimes.repositories": {  # P08.01.b
        "PostgresCapabilityVerificationRepository",
        "PostgresHostModelAvailabilityRepository",
        "PostgresHostRuntimeRepository",
        "PostgresModelCatalogRepository",
    },
    "skm.adapters.postgres.settings.repositories": {  # P03.06
        "PostgresConfigEntryRepository",
        "PostgresConfigGenerationCounter",
        "PostgresConfigHistoryRepository",
    },
    "skm.adapters.postgres.uow": {"PostgresUnitOfWork", "PostgresUowFactory"},  # P03.03.a
    "skm.adapters.postgres.workspace.bindings": {"PostgresCheckoutBindingRepository"},  # P04.04.b
    "skm.adapters.postgres.workspace.hosts": {"PostgresHostRepository"},  # P04.04.b
    "skm.adapters.postgres.workspace.mounts": {"PostgresMountRepository"},  # P04.04.b
    "skm.adapters.postgres.workspace.projects": {"PostgresProjectRepository"},  # P04.04.b
    "skm.adapters.postgres.workspace.repositories": {"PostgresRepositoryRepository"},  # P04.04.b
    "skm.adapters.postgres.workspace.worker_hosts": {"PostgresWorkerHostLookup"},  # P04.04.b
    "skm.adapters.postgres.workspace.workers": {"PostgresWorkerRepository"},  # P04.04.b
    "skm.adapters.postgres.workspace.workspaces": {"PostgresWorkspaceRepository"},  # P04.04.b
    "skm.adapters.secrets.env": {"EnvSecretResolver"},
    "skm.adapters.secrets.file": {"FileSecretResolver"},
    "skm.adapters.secrets.keyring": {"KeyringSecretResolver"},
}
