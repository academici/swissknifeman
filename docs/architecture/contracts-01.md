# Contract inventory, part 1

## 3. Два вида прикладного кода — проверяемые типы

| Признак | Control plane (bus handlers, подписчики) | Host operations |
|---|---|---|
| `src/skm/__init__.py` | package boundary | P00.01 |
| `src/skm/adapters/__init__.py` | package boundary | P00.04.f |
| `src/skm/adapters/blobs/__init__.py` | package boundary | P00.04.f |
| `src/skm/adapters/blobs/local/__init__.py` | package boundary | P00.04.f |
| `src/skm/adapters/blobs/local/materializer.py` | READY_MANIFEST_NAME, LocalMaterialWriter, LocalUploadSourceReader | P00.04.f → P06.05 |
| `src/skm/adapters/blobs/local/store.py` | LocalBlobStore | P00.04.f → P06.02 |
| `src/skm/adapters/checkout_fs/__init__.py` | package boundary | P00.04.f |
| `src/skm/adapters/checkout_fs/docs.py` | LocalDocsCheckoutFs | P13.04.c |
| `src/skm/adapters/checkout_fs/local.py` | LocalCheckoutFs | P00.04.f → P10.01.c |
| `src/skm/adapters/checkout_fs/user_home.py` | LocalUserHomeReader | P00.04.f → P10.07 |
| `src/skm/adapters/checks/__init__.py` | package boundary | P00.04.f |
| `src/skm/adapters/checks/command.py` | CommandCheckRunner | P00.04.f → P07.07.a |
| `src/skm/adapters/checks/external.py` | ExternalCheckRunner | P00.04.f → P07.07.a |
| `src/skm/adapters/checks/lifecycle.py` | TrustedCheckLauncher, claim_marker, terminate_group, environment_guard (check process lifecycle) | P07.07.a |
| `src/skm/adapters/checks/manual.py` | ManualCheckRunner | P00.04.f → P07.07.a |
| `src/skm/adapters/checks/shell.py` | ShellCheckRunner | P00.04.f → P07.07.a |
| `src/skm/adapters/event_sinks/__init__.py` | package boundary | P00.04.f |
| `src/skm/adapters/execution/__init__.py` | package boundary | P00.04.f |
| `src/skm/adapters/execution/context_owner.py` | ExecutionContextOwnerGuard | P00.04.f → P09.04.d → P09.09.a |
| `src/skm/adapters/exports/__init__.py` | package boundary | P00.04.f |
| `src/skm/adapters/exports/obsidian/__init__.py` | package boundary | P00.04.f |
| `src/skm/adapters/exports/obsidian/identity.py` | ensure_identity, read_identity, require_writer, update_identity | P13.04.b |
| `src/skm/adapters/exports/obsidian/vault_fs.py` | LocalVaultFs | P00.04.f → P13.04.b |
| `src/skm/adapters/git/__init__.py` | package boundary | P00.04.f |
| `src/skm/adapters/git/_checkout_marker.py` | descriptor-relative checkout marker IO | P15.04.a |
| `src/skm/adapters/git/commit.py` | git_vcs, git_output_sealer, snapshot_commit | P00.04.f → P07.07.a |
| `src/skm/adapters/git/environments/__init__.py` | package boundary | P00.04.f |
| `src/skm/adapters/git/environments/worktree.py` | GitWorktreeEnvironments | P00.04.f → P07.07.a → P07.08.a |
| `src/skm/adapters/git/host_inputs.py` | GitCheckoutReader | P00.04.f → P07.07.a → P09.04.c |
| `src/skm/adapters/git/output_writer.py` | PreSealSnapshot, verify_sealed_output | P07.07.a → I-04.2 |
| `src/skm/adapters/git/excludes.py` | GitInfoExcludes, trusted common Git info/exclude lock and CAS, index-only service file removal | P10.01.c → I-09.1 |
| `src/skm/adapters/git/repo_inspect.py` | GitRepositoryInspector | P00.04.f → P04.06 |
| `src/skm/adapters/git/runner.py` | GitRunner, GitResult, GitCommandFailed | P04.06 |
| `src/skm/adapters/host_commands/__init__.py` | package boundary | P00.04.f |
| `src/skm/adapters/host_commands/local_gate.py` | LocalUserSchemaValidator, SubprocessGateRunner | P02.02 (SKM-0.2.0) |
| `src/skm/adapters/host_commands/subprocess_runner.py` | SubprocessHostCommandRunner | P00.04.f → P10.08.b |
| `src/skm/adapters/http_client/__init__.py` | package boundary | P00.04.f |
| `src/skm/adapters/http_client/auth.py` | BearerHeaders | P11.04.a |
| `src/skm/adapters/http_client/client.py` | HttpSkmClient | P00.04.f → P11.04.a |
| `src/skm/adapters/http_client/events.py` | read_events | P11.04.a |
| `src/skm/adapters/http_client/live.py` | LivePublisher, stream_live | P11.03.b |
| `src/skm/adapters/http_client/retry.py` | TRANSPORT_FAILURES, idempotency_key, send_with_retry, transport_error | P11.04.a |
| `src/skm/adapters/http_client/spool.py` | DEFAULT_MAX_BYTES, DEFAULT_TTL, FORBIDDEN_REPLAY_OPERATIONS, HEARTBEAT_OBSERVATION_OP, BoundedLocalSpool, HistoricalObservation, ReplayReport, SpoolEntry, SpoolItemKind | P13.06 |
| `src/skm/adapters/http_client/worker_config.py` | RemoteWorkerConfig | P11.02.c → P13.04.b |
| `src/skm/adapters/integrations/__init__.py` | package boundary | P00.04.f |
| `src/skm/adapters/integrations/_render/__init__.py` | package boundary | P00.04.f |
| `src/skm/adapters/integrations/_render/json_doc.py` | dumps, dumps_bytes | P10.01.a |
| `src/skm/adapters/integrations/_render/markdown_rules.py` | dumps, dumps_bytes, parse_frontmatter, validate_frontmatter | P10.04.a |
| `src/skm/adapters/integrations/_render/toml_doc.py` | dumps, dumps_bytes, format_inline_table, format_key, format_table, format_value | P10.01.a |
| `src/skm/adapters/integrations/antigravity/__init__.py` | package boundary | P10.04.b contract → Antigravity manual port |
| `src/skm/adapters/integrations/antigravity/target.py` | AntigravityTarget | P10.04.b contract → Antigravity manual port |
| `src/skm/adapters/integrations/claude_code/__init__.py` | package boundary | P00.04.f |
| `src/skm/adapters/integrations/claude_code/agents.py` | CLAUDE_AGENTS_PREFIX, CLAUDE_AGENTS_RENDERER, render_agents | P10.02 |
| `src/skm/adapters/integrations/claude_code/doctor_layers.py` | CLAUDE_LAYER_SPECS, read_claude_layers | P10.02 |
| `src/skm/adapters/integrations/claude_code/hooks.py` | CLAUDE_HOOKS_RENDERER, CLAUDE_HOOK_EVENTS, MAX_PROMPT_BYTES, build_hook_command, normalize_hook_payload, render_hook_decision, render_hook_entries | P10.02 → I-09.2c |
| `src/skm/adapters/integrations/claude_code/instructions.py` | CLAUDE_INSTRUCTIONS_PATH, CLAUDE_INSTRUCTIONS_RENDERER, CLAUDE_INSTRUCTION_BLOCK_IDS, render_instructions | P10.02 |
| `src/skm/adapters/integrations/claude_code/mcp.py` | CLAUDE_MCP_PATH, CLAUDE_MCP_RENDERER, render_mcp | P10.02 |
| `src/skm/adapters/integrations/claude_code/session_summary.py` | SessionSummarySpool | P13.03.c |
| `src/skm/adapters/integrations/claude_code/settings.py` | CLAUDE_DENY_FLOOR, CLAUDE_LOCAL_SETTINGS_PATH, CLAUDE_SETTINGS_PATH, CLAUDE_SETTINGS_RENDERER, ClaudeRules, default_mode_for_profile, render_claude_rules, render_local_settings, render_project_settings | P10.02 |
| `src/skm/adapters/integrations/claude_code/skills.py` | CLAUDE_SKILLS_PREFIX, CLAUDE_SKILLS_RENDERER, SKILL_LISTING_MAX_CHARS, render_skills | P10.02 |
| `src/skm/adapters/integrations/claude_code/target.py` | CLAUDE_CODE_RENDERER_VERSION, ClaudeCodeTarget, load_capabilities | P10.02 |
| `src/skm/adapters/integrations/codex/__init__.py` | package boundary | P00.04.f |
| `src/skm/adapters/integrations/codex/agents.py` | CODEX_AGENTS_PREFIX, CODEX_AGENTS_RENDERER, render_agents | P10.03 |
| `src/skm/adapters/integrations/codex/config_toml.py` | CODEX_CONFIG_PATH, CODEX_CONFIG_RENDERER, render_config_toml | P10.03 |
| `src/skm/adapters/integrations/codex/doctor_layers.py` | CODEX_LAYER_SPECS, effective_hooks_enabled, project_machine_local_keys, read_codex_layers | P10.03 |
| `src/skm/adapters/integrations/codex/hooks.py` | CODEX_HOOKS_PATH, CODEX_HOOKS_RENDERER, CODEX_HOOK_EVENTS, MAX_PROMPT_BYTES, build_hook_command, normalize_hook_payload, render_hook_decision, render_hook_entries, render_hooks | P10.03 → I-09.2c |
| `src/skm/adapters/integrations/codex/instructions.py` | CODEX_INSTRUCTIONS_PATH, CODEX_INSTRUCTIONS_RENDERER, CODEX_INSTRUCTION_BLOCK_IDS, render_instructions | P10.03 |
| `src/skm/adapters/integrations/codex/mcp.py` | CODEX_MCP_RENDERER, build_mcp_servers | P10.03 |
| `src/skm/adapters/integrations/codex/permissions.py` | CODEX_DENY_FLOOR_PATTERNS, CODEX_MACHINE_LOCAL_KEYS, CodexMode, render_codex_mode, validate_codex_permissions, validate_no_machine_local_keys | P10.03 |
| `src/skm/adapters/integrations/codex/skills.py` | CODEX_SKILLS_PREFIX, CODEX_SKILLS_RENDERER, SKILL_LISTING_MAX_CHARS, render_skills | P10.03 |
| `src/skm/adapters/integrations/codex/target.py` | CODEX_RENDERER_VERSION, CodexTarget, load_capabilities | P10.03 |
| `src/skm/adapters/integrations/cursor/__init__.py` | package boundary | P00.04.f |
| `src/skm/adapters/integrations/cursor/agents.py` | CURSOR_AGENTS_PREFIX, CURSOR_AGENTS_RENDERER, render_agents | P10.04.a |
| `src/skm/adapters/integrations/cursor/hooks.py` | CURSOR_HOOKS_PATH, CURSOR_HOOKS_RENDERER, CURSOR_HOOKS_VERSION, CURSOR_HOOK_EVENTS, build_hook_command, normalize_hook_payload, render_hook_decision, render_hook_entries, render_hooks | P10.04.a |
| `src/skm/adapters/integrations/cursor/instructions.py` | CURSOR_INSTRUCTIONS_DESCRIPTION, CURSOR_INSTRUCTIONS_PATH, CURSOR_INSTRUCTIONS_RENDERER, CURSOR_INSTRUCTIONS_SLUG, render_instructions | P10.04.a |
| `src/skm/adapters/integrations/cursor/mcp.py` | CURSOR_MCP_PATH, CURSOR_MCP_RENDERER, render_mcp | P10.04.a |
| `src/skm/adapters/integrations/cursor/permissions.py` | CURSOR_CLI_FORBIDDEN_MODE_KEYS, CURSOR_CLI_PATH, CURSOR_DENY_FLOOR, CURSOR_IDE_PERMISSIONS_PATH, CURSOR_PERMISSIONS_RENDERER, CursorRules, render_cli_permissions, render_cursor_rules, render_ide_permissions, validate_no_cli_mode_keys | P10.04.a |
| `src/skm/adapters/integrations/cursor/rules.py` | CURSOR_RULES_PREFIX, CURSOR_RULES_RENDERER, render_mdc_rule, validate_mdc_rule | P10.04.a |
| `src/skm/adapters/integrations/cursor/skills.py` | CURSOR_SKILLS_PREFIX, CURSOR_SKILLS_RENDERER, SKILL_LISTING_MAX_CHARS, render_skills | P10.04.a |
| `src/skm/adapters/integrations/cursor/target.py` | CURSOR_LAYER_SPECS, CURSOR_RENDERER_VERSION, CursorTarget, load_capabilities, read_cursor_layers | P10.04.a |
| `src/skm/adapters/integrations/gemini_cli/__init__.py` | package boundary | P10.04.b contract → I-09.2b |
| `src/skm/adapters/integrations/gemini_cli/target.py` | GeminiCliTarget | P10.04.b contract → I-09.2b |
| `src/skm/adapters/integrations/grok/__init__.py` | package boundary | P00.04.f |
| `src/skm/adapters/integrations/grok/config_toml.py` | GROK_CONFIG_PATH, GROK_CONFIG_RENDERER, render_config_toml | P10.04.b |
| `src/skm/adapters/integrations/grok/hooks.py` | GROK_HOOKS_DESCRIPTION, GROK_HOOKS_PATH, GROK_HOOKS_RENDERER, GROK_HOOK_EVENTS, MAX_PROMPT_BYTES, build_hook_command, normalize_hook_payload, render_hook_decision, render_hook_entries, render_hooks | P10.04.b |
| `src/skm/adapters/integrations/grok/instructions.py` | GROK_INSTRUCTIONS_PATH, GROK_INSTRUCTIONS_RENDERER, GROK_INSTRUCTIONS_SLUG, render_instructions | P10.04.b |
| `src/skm/adapters/integrations/grok/mcp.py` | GROK_MCP_RENDERER, build_mcp_servers | P10.04.b |
| `src/skm/adapters/integrations/grok/permissions.py` | GROK_DENY_FLOOR, GROK_FORBIDDEN_PROJECT_MODE_KEYS, GROK_LAUNCH_FLAGS, GROK_LAUNCH_MODES, launch_flags_for_profile, launch_mode_for_profile, render_grok_deny, validate_no_project_mode_keys | P10.04.b |
| `src/skm/adapters/integrations/grok/rules.py` | GROK_RULES_PREFIX, GROK_RULES_RENDERER, render_markdown_rule | P10.04.b |
| `src/skm/adapters/integrations/grok/skills.py` | GROK_SKILLS_PREFIX, GROK_SKILLS_RENDERER, SKILL_LISTING_MAX_CHARS, render_skills | P10.04.b |
| `src/skm/adapters/integrations/grok/target.py` | GROK_LAYER_SPECS, GROK_RENDERER_VERSION, GrokTarget, load_capabilities, read_grok_layers | P10.04.b |
| `src/skm/adapters/integrations/hookd.py` | Authenticated Unix socket listener and client transport | P10.05.a → I-09.2c |
| `src/skm/adapters/integrations/registry.py` | TARGETS, StaticIntegrationTargetRegistry, default_target_registry | P00.04.f → P10.02 → P10.03 → P10.04.a → P10.04.b |
| `src/skm/adapters/knowledge/__init__.py` | package boundary | P00.04.f |
| `src/skm/adapters/knowledge/context_source.py` | KnowledgeMemoryRetriever | P00.04.f → P13.01.b |
| `src/skm/adapters/knowledge/local_sqlite_memory.py` | LocalSqliteMemoryStore for HOST_PRIVATE episodes and consumption receipts | P13.01.b → I-09.4 |
| `src/skm/adapters/knowledge/null_retriever.py` | NullMemoryRetriever | P09.05 |
| `src/skm/adapters/knowledge/manifest_readers/__init__.py` | package boundary | P00.04.f |
| `src/skm/adapters/knowledge/manifest_readers/composer_json.py` | ComposerJsonReader | P13.02.b |
| `src/skm/adapters/knowledge/manifest_readers/package_json.py` | PackageJsonReader | P13.02.b |
| `src/skm/adapters/knowledge/manifest_readers/pyproject.py` | PyprojectReader | P13.02.b |
| `src/skm/adapters/knowledge/serena_reader.py` | SerenaCodeGraphReader reads a prebuilt `.serena/graph.json` with `ref`, `tool_schema`, `index`, `symbols` and `references` | P13.02.b |
| `src/skm/adapters/memory/__init__.py` | package boundary | P00.04.f |
| `src/skm/adapters/memory/access/__init__.py` | package boundary | P00.04.f → P04.02.a → P04.02.b |
| `src/skm/adapters/memory/access/repositories.py` | MemoryPrincipalRepository, MemoryIdentityRepository, MemoryTokenRepository, MemoryMembershipRepository | P00.04.f → P04.02.a → P04.02.b |
| `src/skm/adapters/memory/access/pairing.py` | MemoryPairingRepository | P04.02.b → I-10.1a |
| `src/skm/adapters/memory/access/sessions.py` | MemoryWebSessionRepository | P04.02.b → I-10.1b |
| `src/skm/adapters/memory/access/state.py` | STATE_KEY, MemoryAccessState, access_state | P04.02.a |
| `src/skm/adapters/memory/artifacts/__init__.py` | package boundary | P00.04.f → P06.03.a → P06.03.c |
| `src/skm/adapters/memory/artifacts/blob_coordination.py` | MemoryBlobCoordination, MemoryBlobDigestLock, bind_memory_artifacts, digest_lock_key | P06.03.c |
| `src/skm/adapters/memory/artifacts/repositories.py` | MemoryStagedBlobRepository, MemoryBlobRepository, MemoryFileRepository, MemoryFileVersionRepository, MemoryAccessGrantRepository, MemoryBlobContentReader | P00.04.f → P06.03.a |
| `src/skm/adapters/memory/artifacts/state.py` | STATE_KEY, BlobStoreRef, MemoryArtifactsState, artifacts_state | P06.03.a |
| `src/skm/adapters/memory/blob_store.py` | MemoryBlobStore (in-memory BlobStore for tests, artifacts §3) | P06.02 |
| `src/skm/adapters/memory/context/__init__.py` | package boundary | P00.04.f → P09.04.a |
| `src/skm/adapters/memory/context/repositories.py` | MemoryContextRepository, MemoryTextStore, MemoryResearchRepository | P00.04.f → P09.04.a → P09.04.d → P09.09.a |
| `src/skm/adapters/memory/core/__init__.py` | package boundary | P00.04.f → P01.08.b |
| `src/skm/adapters/memory/core/storage_inspector.py` | MemoryStorageInspector | P15.01.a |
| `src/skm/adapters/memory/execution/__init__.py` | package boundary; exports REPOSITORIES | P00.04.f → P07.05.a |
| `src/skm/adapters/memory/execution/assignments.py` | MemoryAssignmentRepository, MemoryEnvironmentRepository, MemoryOutputRepository | P07.05.a |
| `src/skm/adapters/memory/execution/attempts_stages.py` | MemoryAttemptRepository, MemoryStageRepository, MemoryStepRepository | P07.05.a |
| `src/skm/adapters/memory/execution/budgets_decisions_effects.py` | MemoryBudgetRepository, MemoryDecisionRepository, MemoryEffectRepository | P07.05.a |
| `src/skm/adapters/memory/execution/checks_reviews.py` | MemoryCheckRepository, MemoryReviewRepository, MemoryAcceptanceRepository | P07.05.a |
| `src/skm/adapters/memory/execution/fix_briefs.py` | add_fix_brief, get_fix_brief (existing memory review store) | P08.10 |
| `src/skm/adapters/memory/execution/misc_repos.py` | MemoryIntegrationSlotRepository, MemoryReviewRequestRepository, MemoryAutopilotRepository, MemoryRecoveryRepository, MemoryEvidenceBindingRepository | P07.05.a |
| `src/skm/adapters/memory/execution/queries.py` | MemoryExecutionQueries | P00.04.f → P07.05.a → P07.08.a → P07.05.c |
| `src/skm/adapters/memory/execution/queries_helpers.py` | record selection for MemoryExecutionQueries documents | P07.05.a |
| `src/skm/adapters/memory/execution/queries_views.py` | MemoryExecutionQueries read-model implementation | P07.05.a |
| `src/skm/adapters/memory/execution/repositories.py` | MemoryRunRepository, MemoryBundleRepository, MemoryReadinessRepository, MemoryTaskRepository, MemoryAttemptRepository, MemoryStageRepository, MemoryStepRepository, MemoryAssignmentRepository, MemoryEnvironmentRepository, MemoryOutputRepository, MemoryCheckRepository, MemoryReviewRepository, MemoryAcceptanceRepository, MemoryBudgetRepository, MemoryDecisionRepository, MemoryEffectRepository, MemoryIntegrationSlotRepository, MemoryReviewRequestRepository, MemoryAutopilotRepository, MemoryRecoveryRepository, MemoryEvidenceBindingRepository | P00.04.f → P07.05.a → P07.08.a → P07.05.c |
| `src/skm/adapters/memory/execution/runs_tasks.py` | MemoryRunRepository, MemoryBundleRepository, MemoryReadinessRepository, MemoryTaskRepository | P07.05.a |
| `src/skm/adapters/memory/execution/state.py` | STATE_KEY, MemoryExecutionState, execution_state, cloning and payload validators | P07.05.a |
| `src/skm/adapters/memory/exports/__init__.py` | package boundary | P00.04.f → P13.04.a |
| `src/skm/adapters/memory/exports/repositories.py` | MemoryVaultNoteRepository | P00.04.f → P13.04.a |
| `src/skm/adapters/memory/exports/state.py` | NoteState, exports_state | P13.04.a |
| `src/skm/adapters/memory/extensions/__init__.py` | REPOSITORIES | P00.04.f → P09.01.a |
| `src/skm/adapters/memory/extensions/mapping.py` | STATE_KEY, MemoryExtensionsState, QuarantineRow, extensions_state | P09.01.a |
| `src/skm/adapters/memory/extensions/queries.py` | pack_summary, resource_summary | P09.01.a |
| `src/skm/adapters/memory/extensions/repositories.py` | MemoryPackRepository, MemoryResourceRepository, MemoryQuarantineRepository | P00.04.f → P09.01.a |
| `src/skm/adapters/memory/integrations/__init__.py` | package boundary; exports REPOSITORIES | P00.04.f → P10.01.b |
| `src/skm/adapters/memory/integrations/repositories.py` | MemoryProjectionRepository | P00.04.f → P10.01.b |
| `src/skm/adapters/memory/integrations/state.py` | STATE_KEY, StoredProjection, MemoryIntegrationsState, integrations_state | P10.01.b |
| `src/skm/adapters/memory/knowledge/__init__.py` | REPOSITORIES | P00.04.f → P13.01.b → P13.02.a |
| `src/skm/adapters/memory/knowledge/graph.py` | MemoryGraphRepository | P13.02.a |
| `src/skm/adapters/memory/knowledge/lessons.py` | MemoryLessonRepository | P13.01.b |
| `src/skm/adapters/memory/knowledge/mapping.py` | MemoryKnowledgeState, knowledge_state | P13.01.b |
| `src/skm/adapters/memory/knowledge/memory.py` | MemoryMemoryRepository | P13.01.b |
| `src/skm/adapters/memory/knowledge/repositories.py` | MemoryMemoryRepository, MemoryLessonRepository, MemoryGraphRepository | P00.04.f → P13.01.b → P13.03.b |
| `src/skm/adapters/memory/learning/__init__.py` | REPOSITORIES | P00.04.f → P13.03.b |
| `src/skm/adapters/memory/learning/activity.py` | MemoryActivityRecordRepository | P13.03.c |
| `src/skm/adapters/memory/learning/candidates.py` | MemoryCandidateRepository | P13.03.b |
| `src/skm/adapters/memory/learning/constraints.py` | activity_checks, candidate_checks, project_scope, reference | P13.03.c |
| `src/skm/adapters/memory/learning/proposals.py` | MemoryCandidateProposalRepository | P13.03.b |
| `src/skm/adapters/memory/learning/repositories.py` | MemoryActivityRecordRepository, MemoryCandidateRepository, MemorySignalRepository, MemoryCandidateReviewRepository, MemoryCandidateProposalRepository | P00.04.f → P13.03.b → P13.03.c |
| `src/skm/adapters/memory/learning/reviews.py` | MemoryCandidateReviewRepository | P13.03.b |
| `src/skm/adapters/memory/learning/signals.py` | MemorySignalRepository | P13.03.b |
| `src/skm/adapters/memory/planning/__init__.py` | package boundary | P00.04.f → P05.04.b |
| `src/skm/adapters/memory/planning/queries.py` | MemoryPlanningQueries | P00.04.f → P05.04.b → P05.04.c → P06.04.a → P06.04.b |
| `src/skm/adapters/memory/planning/repositories.py` | MemoryPlanRepository, MemoryPlanCounters, MemoryDraftRepository, MemoryRevisionRepository | P00.04.f → P05.04.b → P05.04.c → P06.04.a |
| `src/skm/adapters/memory/planning/state.py` | STATE_KEY, MemoryPlanningState, StoredIdentity, StoredRevision, planning_state | P05.04.b |
| `src/skm/adapters/memory/policy/__init__.py` | package boundary | P00.04.f → P07.01.b |
| `src/skm/adapters/memory/policy/repositories.py` | MemoryToolIntentRepository, MemoryApprovalRepository, MemoryDecisionAuditRepository | P00.04.f → P07.01.b |
| `src/skm/adapters/memory/policy/state.py` | STATE_KEY, MemoryPolicyState, policy_state | P07.01.b |
| `src/skm/adapters/memory/runtimes/__init__.py` | package boundary; exports REPOSITORIES | P00.04.f → P08.01.b |
| `src/skm/adapters/memory/runtimes/repositories.py` | MemoryHostRuntimeRepository, MemoryCapabilityVerificationRepository, MemoryModelCatalogRepository, MemoryHostModelAvailabilityRepository | P00.04.f → P08.01.b |
| `src/skm/adapters/memory/runtimes/state.py` | STATE_KEY, StoredVerification, MemoryRuntimesState, runtimes_state | P08.01.b |
| `src/skm/adapters/memory/settings/__init__.py` | REPOSITORIES | P00.04.f → P02.07.b |
| `src/skm/adapters/memory/settings/repositories.py` | MemoryConfigEntryRepository, MemoryConfigHistoryRepository, MemoryConfigGenerationCounter, MemorySettingsState, settings_state, STATE_KEY | P00.04.f → P02.07.b |
| `src/skm/adapters/memory/uow.py` | InMemoryUnitOfWork, InMemoryUowFactory | P00.04.f → P01.08.b → P03.05.b |
| `src/skm/adapters/memory/workspace/__init__.py` | package boundary | P00.04.f → P04.04.a |
| `src/skm/adapters/memory/workspace/repositories.py` | MemoryWorkspaceRepository, MemoryProjectRepository, MemoryRepositoryRepository, MemoryMountRepository, MemoryHostRepository, MemoryCheckoutBindingRepository, MemoryWorkerRepository | P00.04.f → P04.04.a |
| `src/skm/adapters/memory/workspace/state.py` | MemoryWorkspaceState, workspace_state, STATE_KEY | P04.04.a |
| `src/skm/adapters/postgres/__init__.py` | package boundary | P00.04.f |
| `src/skm/adapters/postgres/access/__init__.py` | package boundary | P00.04.f → P04.02.b |
| `src/skm/adapters/postgres/access/repositories.py` | PostgresPrincipalRepository, PostgresIdentityRepository, PostgresTokenRepository, PostgresMembershipRepository | P00.04.f → P04.02.b |
| `src/skm/adapters/postgres/access/pairing.py` | PostgresPairingRepository | P04.02.b → I-10.1a |
| `src/skm/adapters/postgres/access/sessions.py` | PostgresWebSessionRepository | P04.02.b → I-10.1b |
| `src/skm/adapters/postgres/artifacts/__init__.py` | package boundary; exports REPOSITORIES | P00.04.f → P06.03.b → P06.03.c |
| `src/skm/adapters/postgres/artifacts/blob_coordination.py` | PostgresBlobCoordination, PostgresBlobDigestLock, bind_postgres_artifacts, create_coordination_pool, digest_lock_key | P06.03.c |
| `src/skm/adapters/postgres/artifacts/repositories.py` | PostgresStagedBlobRepository, PostgresBlobRepository, PostgresFileRepository, PostgresFileVersionRepository, PostgresAccessGrantRepository, PostgresBlobContentReader | P00.04.f → P06.03.b |
| `src/skm/adapters/postgres/machine.py` | PostgresMachineStore | P03.01.a → SKM 0.1.0 S01 |
| `src/skm/adapters/postgres/config_store.py` | PostgresConfigStore, PostgresScopeTree | P03.06 |
| `src/skm/adapters/postgres/connection.py` | PgSettings, configure_session, connect_single, conninfo_of (adapters §1.2) | P03.01.a |
| `src/skm/adapters/postgres/context/__init__.py` | package boundary | P00.04.f → P09.04.a |
| `src/skm/adapters/postgres/context/repositories.py` | PostgresContextRepository, PostgresTextStore, PostgresResearchRepository | P00.04.f → P09.04.a → P09.04.d → P09.09.a |
| `src/skm/adapters/postgres/core/__init__.py` | package boundary | P00.04.f → P03.02 → P03.03.a → P03.05 |
| `src/skm/adapters/postgres/core/audit.py` | PostgresAuditLog | P03.03.b |
| `src/skm/adapters/postgres/core/consumer_receipts.py` | PostgresConsumerReceipts | P03.05 |
| `src/skm/adapters/postgres/core/events_store.py` | PostgresEventWriter, PostgresEventReader | P03.03.a |
| `src/skm/adapters/postgres/events.py` | EventListener | P11.03.a |
| `src/skm/adapters/postgres/core/idempotency.py` | PostgresIdempotencyStore | P03.03.b |
| `src/skm/adapters/postgres/core/outbox.py` | PostgresOutboxStore, VISIBILITY_TIMEOUT | P03.05 → P10.08.a |
| `src/skm/adapters/postgres/core/schema_version.py` | SchemaVersionReader, SchemaCompatibility, PostgresSchemaVersionReader | P03.01.a → P11.01.a |
| `src/skm/adapters/postgres/core/storage_inspector.py` | PostgresStorageInspector | P15.01.a |
| `src/skm/adapters/postgres/core/scopes.py` | PostgresScopeRegistry, PostgresScopeTree | P03.02 |
| `src/skm/adapters/postgres/errors.py` | translate_pg_error (adapters §1.3) | P03.01.a |
| `src/skm/adapters/postgres/execution/__init__.py` | package boundary; exports REPOSITORIES | P00.04.f → P07.05.a |
| `src/skm/adapters/postgres/execution/acceptance.py` | PostgresAcceptanceRepository | P07.05.a |
| `src/skm/adapters/postgres/execution/assignments.py` | PostgresAssignmentRepository | P07.05.a |
| `src/skm/adapters/postgres/execution/attempts_stages.py` | PostgresAttemptRepository, PostgresStageRepository | P07.05.a |
| `src/skm/adapters/postgres/execution/autopilot_recovery.py` | PostgresAutopilotRepository, PostgresRecoveryRepository, PostgresEvidenceBindingRepository | P07.05.a |
| `src/skm/adapters/postgres/execution/budgets.py` | PostgresBudgetRepository | P07.05.a |
| `src/skm/adapters/postgres/execution/checks_reviews.py` | PostgresCheckRepository, PostgresReviewRepository | P07.05.a |
| `src/skm/adapters/postgres/execution/fix_briefs.py` | add_fix_brief, get_fix_brief (existing SQL review repository) | P08.10 |
| `src/skm/adapters/postgres/execution/codecs.py` | re-exports of PostgreSQL row/domain codecs for skm_execution | P07.05.a |
| `src/skm/adapters/postgres/execution/codecs_core.py` | core PostgreSQL row/domain codecs for runs, tasks, attempts, stages, steps | P07.05.a |
| `src/skm/adapters/postgres/execution/codecs_leases_outputs.py` | PostgreSQL row/domain codecs for assignments, environments, outputs | P07.05.a |
| `src/skm/adapters/postgres/execution/codecs_outcomes.py` | outcome PostgreSQL row/domain codecs for checks, reviews, acceptance, budgets, decisions, effects, slots, autopilot, recoveries | P07.05.a |
| `src/skm/adapters/postgres/execution/decisions_effects.py` | PostgresDecisionRepository, PostgresEffectRepository | P07.05.a |
| `src/skm/adapters/postgres/execution/environments_outputs.py` | PostgresEnvironmentRepository, PostgresOutputRepository | P07.05.a |
| `src/skm/adapters/postgres/execution/integration_slots.py` | PostgresIntegrationSlotRepository, PostgresReviewRequestRepository | P07.05.a |
| `src/skm/adapters/postgres/execution/mapping.py` | DictRow, run, error helpers, canonical payload validators, reap_barrier_satisfied | P07.05.a |
| `src/skm/adapters/postgres/execution/queries.py` | PostgresExecutionQueries | P00.04.f → P07.05.a → P07.08.a → P07.05.c |
| `src/skm/adapters/postgres/execution/queries_events_outcomes.py` | QueriesEventsOutcomesMixin for event/history and outcome read projections | P07.05.a |
| `src/skm/adapters/postgres/execution/repositories.py` | PostgresRunRepository, PostgresBundleRepository, PostgresReadinessRepository, PostgresTaskRepository, PostgresAttemptRepository, PostgresStageRepository, PostgresStepRepository, PostgresAssignmentRepository, PostgresEnvironmentRepository, PostgresOutputRepository, PostgresCheckRepository, PostgresReviewRepository, PostgresAcceptanceRepository, PostgresBudgetRepository, PostgresDecisionRepository, PostgresEffectRepository, PostgresIntegrationSlotRepository, PostgresReviewRequestRepository, PostgresAutopilotRepository, PostgresRecoveryRepository, PostgresEvidenceBindingRepository | P00.04.f → P07.05.a → P07.08.a → P07.05.c |
| `src/skm/adapters/postgres/execution/runs_tasks.py` | PostgresRunRepository, PostgresBundleRepository, PostgresReadinessRepository | P07.05.a |
| `src/skm/adapters/postgres/execution/steps.py` | PostgresStepRepository | P07.05.a |
| `src/skm/adapters/postgres/execution/tasks.py` | PostgresTaskRepository | P07.05.a |
| `src/skm/adapters/postgres/exports/__init__.py` | package boundary | P00.04.f → P13.04.a |
| `src/skm/adapters/postgres/exports/mapping.py` | note_from_row, write_from_row | P13.04.a |
| `src/skm/adapters/postgres/exports/repositories.py` | PostgresVaultNoteRepository | P00.04.f → P13.04.a |
| `src/skm/adapters/postgres/extensions/__init__.py` | REPOSITORIES | P00.04.f → P09.01.a |
| `src/skm/adapters/postgres/extensions/mapping.py` | Row, not_found, pack_from_row, pack_summary_from_row, pack_version_from_row, resource_from_row, resource_summary_from_row, resource_version_from_row, run | P09.01.a |
| `src/skm/adapters/postgres/extensions/pack_config_source.py` | PackConnectionSlot, PostgresPackConfigSource | P09.03 |
| `src/skm/adapters/postgres/extensions/queries.py` | one named function per statement of the extensions repositories (get_pack … release_quarantine) | P09.01.a |
| `src/skm/adapters/postgres/extensions/repositories.py` | PostgresPackRepository, PostgresResourceRepository, PostgresQuarantineRepository | P00.04.f → P09.01.a |
| `src/skm/adapters/postgres/integrations/__init__.py` | package boundary; exports REPOSITORIES | P00.04.f → P10.01.b |
| `src/skm/adapters/postgres/integrations/repositories.py` | PostgresProjectionRepository | P00.04.f → P10.01.b |
| `src/skm/adapters/postgres/jsonb.py` | canonical_dumps, to_jsonb, require_aware (adapters §1.4) | P03.01.a |
| `src/skm/adapters/postgres/knowledge/__init__.py` | REPOSITORIES | P00.04.f → P13.01.b → P13.02.a |
| `src/skm/adapters/postgres/knowledge/graph.py` | PostgresGraphRepository | P13.02.a |
| `src/skm/adapters/postgres/knowledge/lessons.py` | PostgresLessonRepository | P13.01.b |
| `src/skm/adapters/postgres/knowledge/mapping.py` | Row, lesson_from_row, memory_from_row, run, scope_from_row | P13.01.b |
| `src/skm/adapters/postgres/knowledge/memory.py` | PostgresMemoryRepository | P13.01.b |
| `src/skm/adapters/postgres/knowledge/repositories.py` | PostgresMemoryRepository, PostgresLessonRepository, PostgresGraphRepository | P00.04.f → P13.01.b → P13.03.b |
| `src/skm/adapters/postgres/learning/__init__.py` | package boundary | P00.04.f → P13.03.c |
| `src/skm/adapters/postgres/learning/activity.py` | PostgresActivityRecordRepository | P13.03.c |
| `src/skm/adapters/postgres/learning/candidates.py` | PostgresCandidateRepository | P13.03.c |
| `src/skm/adapters/postgres/learning/mapping.py` | learning row mapping | P13.03.c |
| `src/skm/adapters/postgres/learning/repositories.py` | PostgresActivityRecordRepository, PostgresCandidateRepository, PostgresSignalRepository, PostgresCandidateReviewRepository, PostgresCandidateProposalRepository | P00.04.f → P13.03.b → P13.03.c |
| `src/skm/adapters/postgres/migrations/__init__.py` | package boundary | P00.04.f |
| `src/skm/adapters/postgres/migrations/machine_sql/__init__.py` | machine database migration resources | P03.01.a → SKM 0.1.0 S01 |
| `src/skm/adapters/postgres/migrations/runner.py` | MigrationRunner, MigrationSession, MigrationFile, MigrationState (adapters §1.10) | P03.01.a |
| `src/skm/adapters/postgres/migrations/snapshot.py` | schema_snapshot, normalize_dump (adapters §1.10) | P03.01.a |
| `src/skm/adapters/postgres/migrations/sql/__init__.py` | package boundary of the packaged migration files (adapters §1.10) | P03.01.b |
| `src/skm/adapters/postgres/pagination.py` | Cursor, keyset helpers (adapters §1.5) | P03.01.a |
| `src/skm/adapters/postgres/planning/__init__.py` | package boundary; exports REPOSITORIES | P00.04.f → P05.05.b |
| `src/skm/adapters/postgres/planning/counters.py` | PostgresPlanCounters | P05.05.b |
| `src/skm/adapters/postgres/planning/drafts.py` | PostgresDraftRepository | P05.05.b |
| `src/skm/adapters/postgres/planning/mapping.py` | Row, already_exists, damaged, draft_from_row, field_owned, member_ref_from_row, not_found, plan_from_row, require_unchanged, revision_meta_from_row, run, work_policy_from_sql, work_policy_to_sql | P05.05.b |
| `src/skm/adapters/postgres/planning/plans.py` | PostgresPlanRepository | P05.05.b |
| `src/skm/adapters/postgres/planning/queries.py` | PostgresPlanningQueries, list_plans, plan_summary, find_member, find_member_by_id, entity_links, revision_pins, revision_materials, revisions_pinning_file_version | P00.04.f → P05.05.b → P06.04.a |
| `src/skm/adapters/postgres/planning/revisions.py` | PostgresRevisionRepository | P05.05.b |
| `src/skm/adapters/postgres/planning/spec_reader.py` | load_typed_document, load_revision_pins, load_revision_materials, revisions_for_file_version | P05.05.b → P06.04.a → P06.04.b |
| `src/skm/adapters/postgres/planning/spec_writer.py` | write_revision_record | P05.05.b → P06.04.a |
| `src/skm/adapters/postgres/pool.py` | PoolHandle, create_pool, connect_single (adapters §1.2) | P03.01.a |
| `src/skm/adapters/postgres/policy/__init__.py` | package boundary | P00.04.f → P07.01.b |
| `src/skm/adapters/postgres/policy/approvals.py` | PostgresApprovalRepository | P07.01.b |
| `src/skm/adapters/postgres/policy/audit.py` | PostgresDecisionAuditRepository | P07.01.b |
| `src/skm/adapters/postgres/policy/intents.py` | PostgresToolIntentRepository | P07.01.b |
| `src/skm/adapters/postgres/policy/mapping.py` | Row, run, damaged, not_found, version_conflict, time_key, keyset, ensure_kept | P07.01.b |
| `src/skm/adapters/postgres/runtimes/__init__.py` | package boundary | P00.04.f → P08.01.b |
| `src/skm/adapters/postgres/runtimes/repositories.py` | PostgresHostRuntimeRepository, PostgresCapabilityVerificationRepository, PostgresModelCatalogRepository, PostgresHostModelAvailabilityRepository | P00.04.f → P08.01.b |
| `src/skm/adapters/postgres/settings/__init__.py` | package boundary | P00.04.f → P03.06 |
| `src/skm/adapters/postgres/settings/repositories.py` | PostgresConfigEntryRepository, PostgresConfigHistoryRepository, PostgresConfigGenerationCounter | P00.04.f → P03.06 |
| `src/skm/adapters/postgres/uow.py` | PostgresUnitOfWork, PostgresUowFactory | P00.04.f → P03.03.a → P03.05.b |
| `src/skm/adapters/postgres/workspace/__init__.py` | package boundary; exports REPOSITORIES | P00.04.f → P04.04.b |
| `src/skm/adapters/postgres/workspace/bindings.py` | PostgresCheckoutBindingRepository | P04.04.b |
| `src/skm/adapters/postgres/workspace/hosts.py` | PostgresHostRepository | P04.04.b |
| `src/skm/adapters/postgres/workspace/mapping.py` | Row, STEP, run, damaged, not_found, version_conflict, text_key, time_key, keyset, ensure_kept | P04.04.b |
| `src/skm/adapters/postgres/workspace/mounts.py` | PostgresMountRepository | P04.04.b |
| `src/skm/adapters/postgres/workspace/projects.py` | PostgresProjectRepository | P04.04.b |
| `src/skm/adapters/postgres/workspace/repositories.py` | PostgresRepositoryRepository | P00.04.f → P04.04.b |
| `src/skm/adapters/postgres/workspace/worker_hosts.py` | PostgresWorkerHostLookup | P04.04.b |
| `src/skm/adapters/postgres/workspace/workers.py` | PostgresWorkerRepository | P04.04.b |
| `src/skm/adapters/postgres/workspace/workspaces.py` | PostgresWorkspaceRepository | P04.04.b |
| `src/skm/adapters/research/__init__.py` | package boundary | P00.04.f |
| `src/skm/adapters/http_client/research.py` | bounded cancellable HTTPS transport for host research | P09.09.b → I-11.2 |
| `src/skm/adapters/research/codegraph.py` | NativeCodeGraphAdapter; trusted per-checkout CodeGraph lifecycle, MCP descriptor and native research source | P09.09.b → I-09.3 |
| `src/skm/adapters/research/providers.py` | Context7, Perplexity API, isolated Perplexity browser broker and Brave Search research sources | P09.09.b → I-11.2 |
| `src/skm/adapters/resources/__init__.py` | package boundary | P00.04.f |
| `src/skm/adapters/resources/archive.py` | safe_extract_to_payload | P09.01.b |
| `src/skm/adapters/resources/builtin_packs.py` | PackagedBuiltinPacks | P09.01.a |
| `src/skm/adapters/resources/compiled_pack.py` | PackLock, compiled asset resolution and SHA-256 verification | P09.01.b → I-09.2a |
| `src/skm/adapters/resources/pack_compiler.py` | compile_packs | P09.01.b → I-09.2a |
| `src/skm/adapters/resources/pack_reader.py` | FilesystemPackReader | P00.04.f → P09.01.b |
| `src/skm/adapters/resources/upstream_http.py` | HttpUpstreamFetcher | P00.04.f → P09.01.c |
| `src/skm/adapters/runtimes/__init__.py` | package boundary | P00.04.f |
| `src/skm/adapters/runtimes/_cli_session/__init__.py` | package boundary | P00.04.f |
| `src/skm/adapters/runtimes/_cli_session/activity.py` | ActivityMonitor | P08.02.b |
| `src/skm/adapters/runtimes/_cli_session/cancel.py` | CancelEscalation | P08.02.b |
| `src/skm/adapters/runtimes/_cli_session/identity.py` | ProcessGroupTracker | P08.02.b |
| `src/skm/adapters/runtimes/_cli_session/observation.py` | SessionObservation, collect_observation | P08.02.b |
| `src/skm/adapters/runtimes/_cli_session/probe.py` | CliDetector, ProbeCacheKey, CommandOutput, ProbeCommandRunner | P08.03 |
| `src/skm/adapters/runtimes/_cli_session/proxy_bridge.py` | LocalProxyBridge, ProxyEndpoint | P02.01 (SKM-0.2.0) |
| `src/skm/adapters/runtimes/_cli_session/runtime.py` | CliAgentRuntime, ProbedCli, load_static_declarations | P08.03 |
| `src/skm/adapters/runtimes/_cli_session/launch.py` | LaunchCommand, ensure_private_dir, prepare_client_home, base_child_env, landlock_argv | P08.03 |
| `src/skm/adapters/runtimes/_cli_session/usage.py` | TokenCounts, MessageUsageAccumulator, nonneg_counter, nonneg_counter_opt | P08.03 |
| `src/skm/adapters/runtimes/_cli_session/session.py` | CliSession, SessionLimits | P08.02.b |
| `src/skm/adapters/runtimes/_cli_session/signals.py` | SessionSignals, ToolDenial | P08.02.b |
| `src/skm/adapters/runtimes/_cli_session/stream.py` | LineReader, StreamParser | P08.02.b |
| `src/skm/adapters/runtimes/_cli_session/stream_json.py` | StreamJsonParser, UsageTracker | P08.03 |
| `src/skm/adapters/runtimes/_cli_session/transcript.py` | TranscriptWriter | P08.02.b |
| `src/skm/adapters/runtimes/_cli_session/wire_values.py` | bounded_id, bounded_version, extract_http_status | P08.03 |
| `src/skm/adapters/runtimes/antigravity/__init__.py` | package boundary | P08.05 contract → Antigravity manual port |
| `src/skm/adapters/runtimes/antigravity/detect.py` | AntigravityDetector, ProbedBinary | P08.05 contract → Antigravity manual port |
| `src/skm/adapters/runtimes/antigravity/runtime.py` | AntigravityRuntime | P08.05 contract → Antigravity manual port |
| `src/skm/adapters/runtimes/antigravity/stream_parser.py` | AntigravityStreamParser | P08.05 contract → Antigravity manual port |
| `src/skm/adapters/runtimes/claude_code/__init__.py` | package boundary | P00.04.f |
| `src/skm/adapters/runtimes/claude_code/detect.py` | ClaudeDetector, ProbedBinary | P08.03 |
| `src/skm/adapters/runtimes/claude_code/launch.py` | LaunchPlan, build_launch_plan, compute_launch_config_digest | P08.03 |
| `src/skm/adapters/runtimes/claude_code/permissions.py` | RenderedPermissions, render_permission_flags, denial_hint | P08.03 |
| `src/skm/adapters/runtimes/claude_code/runtime.py` | ClaudeCodeRuntime | P00.04.f → P08.03 |
| `src/skm/adapters/runtimes/claude_code/stream_parser.py` | ClaudeStreamParser | P08.03 |
| `src/skm/adapters/runtimes/claude_code/usage.py` | UsageAccumulator, normalize_usage_counts | P08.03 |
| `src/skm/adapters/runtimes/codex/__init__.py` | package boundary | P00.04.f |
| `src/skm/adapters/runtimes/codex/detect.py` | CodexDetector, ProbedBinary | P08.04 |
| `src/skm/adapters/runtimes/codex/launch.py` | LaunchPlan, build_launch_plan, compute_launch_config_digest | P08.04 |
| `src/skm/adapters/runtimes/codex/permissions.py` | RenderedPermissions, render_permission_flags, denial_hint | P08.04 |
| `src/skm/adapters/runtimes/codex/runtime.py` | CodexRuntime | P00.04.f → P08.04 |
| `src/skm/adapters/runtimes/codex/stream_parser.py` | CodexStreamParser | P08.04 |
| `src/skm/adapters/runtimes/codex/usage.py` | UsageAccumulator, normalize_usage_counts | P08.04 |
| `src/skm/adapters/runtimes/cursor/__init__.py` | package boundary | P00.04.f |
| `src/skm/adapters/runtimes/cursor/detect.py` | CursorDetector, ProbedBinary | P08.05 |
| `src/skm/adapters/runtimes/cursor/runtime.py` | CursorRuntime | P00.04.f → P08.05 |
| `src/skm/adapters/runtimes/fake/__init__.py` | package boundary | P00.04.f |
| `src/skm/adapters/runtimes/fake/runtime.py` | FakeRuntime (adapter-local RuntimeStartError carries ProviderFailure) | P00.04.f → P08.02.a |
| `src/skm/adapters/runtimes/fake/scenarios.py` | Scenario, ScenarioError, load_scenario, select_scenario | P08.02.a |
| `src/skm/adapters/runtimes/gemini_cli/__init__.py` | package boundary | P08.05 contract → I-09.2b |
| `src/skm/adapters/runtimes/gemini_cli/capabilities.toml` | runtime capability declarations | P08.05 contract → I-09.2b |
| `src/skm/adapters/runtimes/gemini_cli/detect.py` | GeminiCliDetector, ProbedBinary | P08.05 contract → I-09.2b |
| `src/skm/adapters/runtimes/gemini_cli/error_rules.toml` | provider error rules | P08.05 contract → I-09.2b |
| `src/skm/adapters/runtimes/gemini_cli/runtime.py` | GeminiCliRuntime | P08.05 contract → I-09.2b |
| `src/skm/adapters/runtimes/_interactive_terminal.py` | PTY owner, terminal resizing, attach and detach via private FIFOs | P08.05 contract → I-08.3 |
| `src/skm/adapters/runtimes/interactive.py` | InteractiveLauncher, private session records and pidfd lifecycle | P08.05 contract → I-08.3 |
| `src/skm/adapters/runtimes/launch_identity.py` | matches_cli_binary, read-only executable identity check | P08.03 → W02 → T02 |
| `src/skm/adapters/runtimes/gemini_cli/stream_parser.py` | GeminiCliStreamParser | P08.05 contract → I-09.2b |
| `src/skm/adapters/runtimes/gemini_cli/usage.py` | parse_usage | P08.05 contract → I-09.2b |
| `src/skm/adapters/runtimes/grok/__init__.py` | package boundary | P00.04.f |
| `src/skm/adapters/runtimes/grok/detect.py` | GrokDetector, ProbedBinary | P08.05 |
| `src/skm/adapters/runtimes/grok/launch.py` | LaunchPlan, build_launch_plan, compute_launch_config_digest, enforce_containment_invariants | P08.05 |
| `src/skm/adapters/runtimes/grok/permissions.py` | RenderedPermissions, render_permission_flags, denial_hint | P08.05 |
| `src/skm/adapters/runtimes/grok/runtime.py` | GrokRuntime | P00.04.f → P08.05 |
| `src/skm/adapters/runtimes/grok/stream_parser.py` | GrokStreamParser | P08.05 |
| `src/skm/adapters/runtimes/grok/usage.py` | UsageAccumulator, normalize_usage_counts | P08.05 |
| `src/skm/adapters/runtimes/pool/__init__.py` | ProviderPoolManager, ProviderSlot, SessionPin, SlotLease, QuotaGroup, QuotaProber, QuotaReading, QuotaReply, AdaptiveExecutorRouter, FailoverCandidate, FailoverController, FailoverDecision, FailoverPolicy | P08.01.b → I-07.1 → I-07.2 → I-07.3 |
| `src/skm/adapters/runtimes/pool/adaptive_router.py` | AdaptiveExecutorRouter ranks eligible slots by static provider weight, then runtime and slot ID | P08.01.b → I-07.2 |
| `src/skm/adapters/runtimes/pool/failover.py` | FailoverCandidate, FailoverController, FailoverDecision, FailoverPolicy gate HTTP 529 cross-cloud failover and local proxy routing on opt-in, consent, ToS, known in-budget pricing, a fresh session, and a run free of HOST_PRIVATE episode consumption | P08.01.b → I-07.3 |
| `src/skm/adapters/runtimes/pool/quota_prober.py` | QuotaGroup, QuotaProber, QuotaReading, QuotaReply, opus_fallback | P08.01.b → I-07.2 |
| `src/skm/adapters/runtimes/pool/provider_pool.py` | Host-local slot leases and serialized refresh, slot-scoped session pins, strict credential boundary via host-dispatched tools, ranked slot acquisition | P08.01.b → I-07.1 → I-07.2 → SKM-0.2.0 P01 |
| `src/skm/adapters/runtimes/pool/rate_limit.py` | RateLimitAction, RateLimitDecision, classify_rate_limit | P02.01 (SKM-0.2.0) |
| `src/skm/adapters/runtimes/pool/shallow_home.py` | ShallowHome, fingerprint_credentials | P02.01 (SKM-0.2.0) |
| `src/skm/adapters/sandbox/__init__.py` | package boundary, SeatbeltSandbox | P00.04.f → I-04.3 |
| `src/skm/adapters/sandbox/backend.py` | BackendIsolation, SpecView, Companion, CompanionProof, ProofRequest, Coverage, assess (backend contract and coverage check) | P08.07.a |
| `src/skm/adapters/sandbox/bubblewrap.py` | BubblewrapSandbox (Linux, `skm:bubblewrap`) | P08.07.a → I-04.2 |
| `src/skm/adapters/sandbox/container.py` | ContainerIsolation | P00.04.f → P08.07.a |
| `src/skm/adapters/sandbox/container_inspect.py` | BASELINE_FIELDS, dig, inspected_one, verified_probe_id | P08.07.a |
| `src/skm/adapters/sandbox/landlock.py` | LandlockIsolation | P00.04.f → P08.07.a |
| `src/skm/adapters/sandbox/landlock_exec.py` | Landlock child wrapper | P08.07.a |
| `src/skm/adapters/sandbox/none.py` | NoneIsolation | P00.04.f → P08.07.a |
| `src/skm/adapters/sandbox/registry.py` | IsolationRegistry | P08.07.a |
| `src/skm/adapters/sandbox/seatbelt.py` | SeatbeltSandbox (macOS, `skm:seatbelt`, `unverified` until a real macOS canary) | P08.07.a → I-04.3 |
| `src/skm/adapters/sandbox/worktree.py` | WorktreeIsolation | P00.04.f → P08.07.a |
| `src/skm/adapters/secrets/__init__.py` | package boundary | P00.04.f |
| `src/skm/adapters/secrets/env.py` | EnvSecretResolver | P00.04.f → P02.05.b |
| `src/skm/adapters/secrets/file.py` | FileSecretResolver | P00.04.f → P02.05.b |
| `src/skm/adapters/secrets/keyring.py` | KeyringSecretResolver | P00.04.f → P11.07 |
| `src/skm/application_bus/__init__.py` | package boundary | P00.04.a |
| `src/skm/application_bus/_outbox_delivery.py` | Single-row outbox delivery, subscriber isolation and retry | P03.05 → P13.04.a |
| `src/skm/application_bus/client.py` | QueryMeta, StagedBlobRef, UploadedBlob, BlobUploader, ContentOpener, SkmClient, EmbeddedClient, embedded_client_factory | P00.04.a → P01.08.a → P01.08.b → P06.03.c |
| `src/skm/application_bus/context.py` | AuthBasisKind, AuthBasis, CommandContext, QueryContext, SubscriberContext, ExternalConsumerContext | P00.04.a → P01.08.a → P03.05.b → I-10.1c |
| `src/skm/application_bus/host.py` | HostContext | P00.04.a → P01.08.a → P01.09.a → P15.01.b |
| `src/skm/application_bus/platform/__init__.py` | package boundary of `platform` pseudo-module handlers | P02.08.b |
| `src/skm/application_bus/platform/doctor.py` | DOCTOR (`QuerySpec` `platform.doctor`), handle, CHECK_IDS, RESTART_PENDING, REGISTERED_CHECKS | P02.08.b → P03.01.b |
| `src/skm/application_bus/platform/migrations.py` | MIGRATION_STATUS (`QuerySpec` `platform.migration_status`), handle, SchemaVersionReader (`repository_port` seam), PackagedMigration, AppliedMigration | P03.01.b |
| `src/skm/application_bus/platform/outbox.py` | LIST_DEAD_OUTBOX (`QuerySpec` `platform.list_dead_outbox`), RETRY_OUTBOX (`CommandSpec` `platform.retry_outbox`), handle_list_dead_outbox, handle_retry_outbox | P03.05 |
| `src/skm/application_bus/platform/storage.py` | VERIFY_STORAGE, REPAIR_STORAGE_SAFE, StorageInspector, StorageObjects, StorageRepair | P15.01.a |
| `src/skm/application_bus/ports.py` | AuthzDecision, Authorizer, ScopeChainResolver, IdempotencyReceipt, IdempotencyStore, AuditRecord, AuditLog, EventReader, OutboxState, OutboxItem, OutboxEntry, OutboxStore, ConsumerReceipts, DeliveryPlan, Sent, RetryAt, GiveUp, SendResult, ExternalConsumer, ProcessObservationState, PendingRestart, CurrentProcessObservation, CurrentProcessObserver, RegisteredCheckReport, DoctorRunner | P00.04.a → P01.08.a → P03.05 → P02.08.b → P10.08.a |
| `src/skm/application_bus/registry.py` | IdempotencyMode, ScopeResolver, CommandSpec (catalogued permission alternatives; additional rights remain required), QuerySpec, SubscriberSpec, ExternalConsumerSpec | P00.04.a → P01.08.a → P03.05.b → P09.04.d → P09.09.a |
| `src/skm/background/__init__.py` | package boundary | P00.04.f |
| `src/skm/background/autopilot.py` | Autopilot | P00.04.f → P08.12 |
| `src/skm/background/janitor.py` | Janitor, JanitorTask, JanitorCommandDispatcher, JanitorService, ExpireStagedBlobsTask, IntentExpiryTask, PurgeNotesTask, build_janitor_tasks | P00.04.f → P03.05.b → P06.03.d → P13.04.a |
| `src/skm/background/learning_recompute.py` | LearningRecompute | P00.04.f → P13.03.c |
| `src/skm/background/lease_sweeper.py` | LeaseSweeper | P00.04.f → P07.06 |
| `src/skm/background/memory_expirer.py` | MemoryExpirer | P00.04.f → P13.01.b |
| `src/skm/background/outbox_relay.py` | OutboxRelay, OutboxRelayService, RelayPass | P00.04.f → P03.05 → P03.05.b |
| `src/skm/background/scheduler.py` | Scheduler | P00.04.f → P07.06 |
| `src/skm/background/service_runner.py` | TickResult, BackgroundService, ServiceHealth, ServiceRunner | P00.04.f → P01.09.b |
| `src/skm/background/stall_detector.py` | StallDetector | P00.04.f → P08.08 |
| `src/skm/background/timeout_enforcer.py` | TimeoutEnforcer | P00.04.f → P07.06 |
| `src/skm/background/vault_push.py` | VaultPush | P00.04.f → P13.04.b |
| `src/skm/bootstrap/_http_mode.py` | HttpHookApp, build_http_client, build_http_hook_app | P11.04.a |
| `src/skm/bootstrap/projection_wiring.py` | bind_cli_projections, checkout filesystem, Git excludes, target registry and effective project settings | P10.01.c → I-09.1 |
| `src/skm/bootstrap/interactive_sessions.py` | Local session composition with runtime routing, host binaries and project projection sync | P11.02.e → I-08.3 |
| `src/skm/bootstrap/_knowledge_wiring.py` | bind_memory_retriever, bind_cli_knowledge | P13.01.b → P13.02.b |
| `src/skm/bootstrap/_quarantine.py` | PostgreSQL snapshot hooks, staging recovery, activation and guard composition | P15.01.b |
| `src/skm/bootstrap/_quarantine_rebind.py` | verified checkout pins and fenced read-only Git worker composition | P15.01.b |
| `src/skm/bootstrap/__init__.py` | package boundary | P00.04.a → P00.04.f |
| `src/skm/bootstrap/adapters.py` | RepositoryFactory, CORE_PORTS, REPOSITORY_TABLE, postgres_repository_table, memory_repository_table (implemented P02.08.a: merges `adapters.memory.core` and module `REPOSITORIES`) | P00.04.f → P02.08.a → P03.03.a |
| `src/skm/bootstrap/builtins.py` | BUILTIN_COMPONENTS, OWNER_PROTOCOLS, builtin_keys, component_problem and the native CodeGraph factory wired to trusted Git excludes | P00.04.f → P01.10 → I-09.3 |
| `src/skm/bootstrap/catalog_transport.py` | HttpsCatalogTransport, PROVIDER_RUNTIME; HTTPS catalog fetch and provider slug map for `skm runtime sync` | P08.01.b → I-05.2 |
| `src/skm/bootstrap/composition.py` | App, build_app, build_cli_app, CompositionOverrides (test-only), KNOWN_SCHEMA_VERSION, invocation_from_json; P02.08.a builds only the transient memory composition, production without overrides answers CAPABILITY_UNAVAILABLE; P02.08.b always adds the `DoctorRunner` adapter (the reports `App.doctor`, a `DoctorCheckCollector` over the `doctor_checks` of the enabled manifests and the platform, recorded host-side, with the restart observation of the app's `ConfigLoader` beneath them) to the control-plane gateway table (supplied test entries take precedence) | P00.04.f → P02.08.a → P03.03.c → P04.02.c → P01.10 → P06.03.c → P09.03 → P09.04.d → P09.09.a → P11.04.a → P15.01.b |
| `src/skm/bootstrap/api_startup.py` | restricted_api_process: database-free API status startup | P11.01.a |
| `src/skm/bootstrap/doctor.py` | DoctorContext, DoctorCheckSpec, DoctorCheckRegistry, DoctorCheckCollector, RestartPendingKey, ServingProcessObservation, ServingProcessObserver | P00.04.f → P01.09.a → P02.08.b |
| `src/skm/bootstrap/hook.py` | Native hook client and evaluator composition | P00.04.f → P10.05.a → P10.05.b → I-09.2c |
| `src/skm/bootstrap/hookd.py` | Protected native hook request routing and daemon composition | P10.05.a → I-09.2c |
| `src/skm/bootstrap/checkout_operations.py` | Local checkout resolution and durable bind and verify against a pinned project | P04.05 → SKM 0.1.0 A02 |
| `src/skm/bootstrap/host_services.py` | build_host_services, bind_cli_research and effective host/project research settings | P00.04.f → P01.09.a → P07.07.b → P11.04.b → I-09.3 |
| `src/skm/bootstrap/instance.py` | init_instance | P00.04.f → P03.07.a → P03.07.b |
| `src/skm/bootstrap/instance_profiles.py` | authenticated HTTPS profile activation and rebind, pinned identity and checkout marker resolution | P11.07 → SKM 0.1.0 S03 |
| `src/skm/bootstrap/sdk.py` | Authenticated HTTP profile connection and transport lifetime | P03.07.a → I-12.4 |
| `src/skm/sdk/__init__.py` | Python client and public campaign operations | P03.07.a → I-12.4 |
| `src/skm/bootstrap/machine.py` | Open the installation's machine storage, enforce verified profile pins and locate the Unix socket | P03.07.a · SKM 0.1.0 A01 |
| `src/skm/bootstrap/machine_access.py` | Authenticate the project's caller, issue machine handles and validate machine user settings | P11.01.a · SKM 0.1.0 A01 |
| `src/skm/bootstrap/runtime_detection.py` | Local operator runtime probing with a bounded project inventory report | P08.01.b · SKM 0.1.0 A01 |
| `src/skm/bootstrap/instance_secrets.py` | PEPPER_BYTES, ensure_pepper, create_exclusive, read_private, http_credential, open_http_client (private instance credentials and authenticated HTTP clients) | P03.07.a → P03.07.b |
| `src/skm/bootstrap/local_cleanup.py` | local retention planning and host cleanup | P11.06 |
| `tests/e2e/test_local_lifecycle_shutdown.py` | PostgreSQL cleanup and bounded shutdown of requests and in-flight runtime units | P11.06 |
| `src/skm/bootstrap/local_execution.py` | Ephemeral runtime composition and durable HOST_PRIVATE consumption marker | P11.06 → I-08.1 |
| `src/skm/bootstrap/local_postgres.py` | local PostgreSQL detection and packaged Compose lifecycle | P11.06 |
| `src/skm/bootstrap/lifecycle.py` | local process identity, supervision, PostgreSQL and serve composition | P11.06 |
| `src/skm/bootstrap/pack_compiler.py` | compile_pack_tree, offline compiler binding | P09.01.b → I-09.2a |
| `src/skm/bootstrap/local_memory.py` | local_episodic_memory binding for embedded host mode | P13.01.b → I-09.4 |
| `src/skm/bootstrap/modules.py` | ModuleCatalogEntry, MODULE_CATALOG, MANIFESTS, PLATFORM_SECTIONS, ModuleGraphError, ModuleSelection, topological_order, select_modules, enabled_manifests, section_index, resolve_section_urns | P00.04.a → P00.04.f → P02.08.a → P10.08.a |
| `src/skm/bootstrap/platform_module.py` | PLATFORM_MANIFEST (P02.08.b: `gateway_ports=(DoctorRunner,)`; P03.01.b: `queries=(DOCTOR, MIGRATION_STATUS)`; P03.05: `LIST_DEAD_OUTBOX`, `commands=(RETRY_OUTBOX,)`) | P00.04.b → P00.04.f → P02.08.b → P03.01.b → P03.05 → P15.01.a |
| `src/skm/bootstrap/plugin_distribution.py` | ENTRY_POINT_GROUP, PluginProvenance, RuntimeDataFiles, default_entry_points, read_runtime_data, provenance, record_digest (steps 1, 2a and 11 of 02-plugins §4, no plugin code runs) | P00.04.f → P01.10 |
| `src/skm/bootstrap/plugins.py` | LoadedPlugin, PluginStatus, PluginAllowlist, PluginSchema, PluginSchemas, PluginSettingsView, PluginViews, ProcessPlugins, SettingsPhase2, load_plugins (steps 1-11 of 02-plugins §4), capability_catalog, merged_schemas, plugin_settings_view, default_context; `component_problem` and `OWNER_PROTOCOLS` from `bootstrap/builtins.py` check each built component | P00.04.f → P01.10 |
| `src/skm/bootstrap/provider_accounts.py` | ProviderAccounts, load_provider_accounts compose host-local slot registries and HTTPS probes | P08.01.b → I-07.2 |
| `src/skm/bootstrap/local_modes.py` | build_local_modes_deps | P02.02 (SKM-0.2.0) |
| `src/skm/bootstrap/runtimes.py` | RUNTIME_FACTORIES, build_provider_pool | P00.04.f → P08.03 → P08.04 → P08.05 → I-07.1 → I-07.2 → SKM-0.2.0 P01 |
| `src/skm/bootstrap/services.py` | ServiceDef, BACKGROUND_SERVICES | P00.04.f → P01.09.b → P07.06 |
| `src/skm/entrypoints/__init__.py` | package boundary | P00.01 → P00.04.f |
| `src/skm/entrypoints/api/__init__.py` | side-effect-free package boundary | P00.04.f → P11.02.a |
| `src/skm/entrypoints/api/app.py` | create_app, build_routes, call_bus, serve_asgi | P00.04.f → P11.01.a → P11.02.a → P11.06 |
| `src/skm/entrypoints/api/routing.py` | Route, RouteTable, build_route_table | P11.02.a |
| `src/skm/entrypoints/api/etag.py` | encode_etag, parse_if_match, check_version | P11.02.a |
| `src/skm/entrypoints/api/pagination.py` | encode_cursor, decode_cursor, page | P11.02.a |
| `src/skm/entrypoints/api/auth.py` | HTTP admission boundary, AuthBasis attachment | P11.01.a → I-10.1b → I-10.1c |
| `src/skm/entrypoints/api/errors.py` | HTTP admission boundary | P11.01.a |
| `src/skm/entrypoints/api/health.py` | HTTP admission boundary | P11.01.a |
| `src/skm/entrypoints/api/middleware.py` | HTTP admission boundary | P11.01.a |
| `src/skm/entrypoints/api/openapi.py` | endpoint serving the generated package resource | P11.02.d |
| `src/skm/entrypoints/api/openapi.json` | generated OpenAPI 3.1 package resource | P11.02.d |
| `src/skm/entrypoints/api/machine.py` | Explicit machine routes and private Unix socket transport | P11.01.a · SKM 0.1.0 A01 |
| `src/skm/entrypoints/api/request_context.py` | HTTP admission boundary | P11.01.a |
| `src/skm/entrypoints/api/static.py` | Packaged Vite assets and browser history fallback | P15.04.a |
| `src/skm/entrypoints/api/sse.py` | workspace and project SSE replay, per-event RBAC, continuous AuthBasis revocation checks | P11.03.a → I-10.1c |
| `src/skm/entrypoints/api/live.py` | worker-only fenced NDJSON publish and live attempt SSE with continuous AuthBasis revocation checks | P11.03.b → I-10.1c |
| `src/skm/entrypoints/api/versioning.py` | HTTP admission boundary | P11.01.a |
| `src/skm/schemas/api/health.v1.json` | HTTP API v1 wire schema | P11.01.a |
| `src/skm/schemas/api/page.v1.json` | HTTP API v1 wire schema | P11.01.a |
| `src/skm/schemas/api/problem.v1.json` | HTTP API v1 wire schema | P11.01.a |
| `src/skm/schemas/api/staged-blob.v1.json` | HTTP API v1 wire schema | P11.01.a |
| `src/skm/platform/generated/api.py` | generated HTTP API wire contracts | P11.01.a |
| `src/skm/entrypoints/api/routes/__init__.py` | pure package boundary and route discovery | P00.04.f → P11.02.a |
| `src/skm/entrypoints/api/blobs.py` | mount_blobs, staged upload and authorized content streaming | P11.02.b |
| `src/skm/entrypoints/api/long_poll.py` | ClaimLongPoll, mount_worker | P11.02.c |
| `src/skm/entrypoints/api/routes/access.py` | access HTTP route declarations | P11.02.b |
| `src/skm/entrypoints/api/routes/auth.py` | AUTH_ROUTE_SPECS, build_auth_routes | P11.02.b → I-10.1b |
| `src/skm/entrypoints/api/routes/artifacts.py` | artifacts HTTP route declarations | P11.02.b |
| `src/skm/entrypoints/api/routes/context.py` | ROUTES | P11.02.e |
| `src/skm/entrypoints/api/routes/execution.py` | ROUTES | P11.02.e |
| `src/skm/entrypoints/api/routes/extensions.py` | ROUTES | P11.02.f |
| `src/skm/entrypoints/api/routes/exports.py` | ROUTES | P13.04.a |
| `src/skm/entrypoints/api/routes/integrations.py` | ROUTES | P11.02.f |
| `src/skm/entrypoints/api/routes/knowledge.py` | ROUTES for project memory, workspace lessons, graph reads and graph import | P13.01.c → P13.02.b |
| `src/skm/modules/knowledge/contracts.py` | Wire DTOs and results for knowledge routes and bus registration | P13.01.c → P13.02.b |
| `src/skm/entrypoints/api/routes/learning.py` | ROUTES | P13.03.c |
| `src/skm/entrypoints/api/routes/planning.py` | ROUTES | P11.02.e |
| `src/skm/entrypoints/api/routes/platform.py` | ROUTES | P11.02.f → P15.01.a |
| `src/skm/entrypoints/api/routes/policy.py` | ROUTES | P11.02.f |
| `src/skm/entrypoints/api/routes/runtimes.py` | ROUTES | P11.02.f |
| `src/skm/entrypoints/api/routes/settings.py` | settings HTTP route declarations | P11.02.b |
| `src/skm/entrypoints/api/routes/worker.py` | ROUTES | P11.02.c |
| `src/skm/entrypoints/api/routes/workspace.py` | workspace HTTP route declarations | P11.02.b |
| `src/skm/entrypoints/cli/__init__.py` | package boundary | P00.01 → P00.04.f |
| `src/skm/entrypoints/cli/commands/__init__.py` | CommandGroup, SubParsers, GroupRegistryError, discover_groups, GROUPS (derived by discovery; not edited by later groups) | P00.04.f → P02.08.a |
| `src/skm/entrypoints/cli/commands/accounts.py` | GROUP, register for host account listing | P08.01.b → I-07.2 |
| `src/skm/entrypoints/cli/commands/backup.py` | GROUP | P15.01.b |
| `src/skm/entrypoints/cli/commands/config.py` | GROUP, register; settings facade CLI (schema/get/explain/set/unset/remove/lock/unlock/import/export/entries/history); `set` reads key metadata with `config.read` in its target scope; no CLI nesting limit; `doctor [--only CHECK]…` asks `platform.doctor` (instance, no `--scope`), prints `warn` unknowns as such and exits 6 on any `fail` | P02.08.b |
| `src/skm/entrypoints/cli/commands/db.py` | GROUP, register; local migration CLI `skm db` with verbs migrate, status, verify, snapshot over `MigrationRunner` with the migrator DSN (`--database-url`, else bootstrap `database.migrator_url`, else `database.url`); no backend, no bus, no API route; `migrate` takes `--target`/`--dry-run`, `snapshot` takes `--output`/`--write` | P03.01.b |
| `src/skm/entrypoints/cli/commands/export.py` | GROUP, register | P13.04.b |
| `src/skm/entrypoints/cli/commands/analytics.py` | GROUP, register | P07.09 → I-12.3 |
| `src/skm/entrypoints/cli/commands/ext.py` | GROUP, register; extensions CLI `skm ext` with verbs list, show, resolve, install, sync, quarantine, release, uninstall, retire, upstream over the `extensions` commands, queries and host operations `extensions.host.install_pack` and `extensions.host.check_upstream` (backend group, module `extensions`) | P09.01.c |
| `src/skm/entrypoints/cli/commands/pack.py` | GROUP, register, offline `skm pack compile` | P09.01.c → I-09.2a |
| `src/skm/entrypoints/cli/commands/file.py` | GROUP, register, resolve_file_id, resolve_file_version_id; artifacts CLI `skm file` with verbs add, version, list, show, versions, cat, trash, restore over the `artifacts` commands, queries, streaming upload/content APIs and `artifacts.host.upload_file` (backend group, module `artifacts`) | P06.05 |
| `src/skm/entrypoints/cli/commands/host.py` | GROUP, register, resolve_host_id, resolve_host_view, run_workspace_host_op; host CLI `skm host` with verbs register, list, show over `workspace` host queries and `workspace.host.register_this_host` (backend group, module `workspace`) | P04.05 |
| `src/skm/entrypoints/cli/commands/init.py` | GROUP, register; core instance bootstrap CLI `skm init` (one unnamed verb, command `cli.init`, no backend, no bus, no API route) with `--json`, `--database-url` (migrator DSN, else `SKM_DATABASE_URL`; a rerun on an existing profile resolves it from the profile like `skm db migrate`), `--state-dir`, `--blobs-root`, `--host-name` and the global `--bootstrap`/`--instance`; creates or verifies the bootstrap profile, the state directory with its private `secrets/`, the token pepper, the migrated schema and the instance scope through `init_instance`; the DSN and its password are registered with the redactor before any output and never written to the profile; owner principal, token, host registration and `--workspace`/`--mode` are P03.07.b | P03.07.a |
| `src/skm/entrypoints/cli/commands/instance.py` | GROUP, register | P11.07 |
| `src/skm/platform/config/sources/bootstrap.py` | NewProfile, ProfileCatalog, add_profile, cli_state_path, edit_cli_state, read_cli_state, save_selection | P11.07 |
| `src/skm/schemas/cli/state.v1.json` | urn:skm:cli:state:v1 | P11.07 |
| `src/skm/entrypoints/cli/commands/integrations.py` | GROUP, register; integrations CLI `skm integrations` with verbs plan, apply, drift, adopt, remove, list and untrack-service-files over `integrations.list_projections` and host operations `integrations.host.{plan_projection,apply_projection,detect_drift,adopt_file,remove_projection,untrack_service_files}` (backend group, module `integrations`) | P10.01.c |
| `src/skm/entrypoints/cli/commands/graph.py` | GROUP, register | P13.02.b |
| `src/skm/entrypoints/cli/commands/learning.py` | CLI commands | P13.03.c |
| `src/skm/entrypoints/cli/commands/lessons.py` | GROUP, register; list, show and deprecate workspace lessons | P13.01.c |
| `src/skm/entrypoints/cli/commands/local.py` | GROUP, register, compose_file; up, down, status, logs, open, clean and token | P11.06 |
| `src/skm/entrypoints/cli/commands/serve.py` | GROUP, register; single-process API and background service entrypoint | P11.06 |
| `src/skm/entrypoints/cli/commands/mcp.py` | GROUP and register for credential-bound stdio, tool discovery and embedded host-only memory mode | P11.05.b → I-09.4 |
| `src/skm/entrypoints/cli/commands/memory.py` | GROUP, read_pages, register; remember, search, list and forget project memory | P13.01.c |
| `src/skm/entrypoints/cli/commands/member.py` | GROUP, register; membership CLI `skm member` with verbs grant, revoke, list over `access.GrantMembership`, `access.RevokeMembership`, `access.ListMemberships` through the bus (backend group, module `access`) | P04.02.c |
| `src/skm/entrypoints/cli/commands/plan.py` | GROUP, register, resolve_plan_id, resolve_revision_id; planning CLI `skm plan` with verbs create, list, show, entities, text, revisions, diff, preview, stats, archive, restore, publish, export, import and `draft` subcommands open, show, edit, save, validate, publication-preview, preview, rebase, abandon over the `planning` commands and queries (backend group, module `planning`) | P05.08 |
| `src/skm/entrypoints/cli/commands/plugins.py` | GROUP, register, lint_sources; plugin CLI `skm plugins` with verbs list, show, lint over installed `skm.plugins` entry points without importing them (no backend, no bus, no API route) | P01.10 |
| `src/skm/entrypoints/cli/commands/principal.py` | GROUP, principal_ref, register; principal CLI `skm principal` with verbs create, list, show, disable over the `access` principal commands and queries through the bus (backend group, module `access`) | P04.02.c |
| `src/skm/entrypoints/cli/commands/project.py` | GROUP, register, resolve_project_id, resolve_project_view; project CLI `skm project` with verbs create, list, show and archive over `workspace` commands and queries, plus activate via `integrations.host.sync_projections` (backend group, module `workspace`) | P04.05 |
| `src/skm/entrypoints/cli/commands/providers.py` | GROUP, register for provider quota probes | P08.01.b → I-07.2 |
| `src/skm/entrypoints/cli/commands/repo.py` | GROUP, register, resolve_repository_id; repository CLI `skm repo` with verbs register, add-remote, attach, detach, bind, verify, list over `workspace` repository commands, queries and host operations `workspace.host.bind_checkout` and `workspace.host.verify_checkout` (backend group, module `workspace`) | P04.05 |
| `src/skm/entrypoints/cli/commands/runtime.py` | GROUP, register; `skm runtime` uses runtimes queries and the `runtimes.host.detect_runtimes` host operation. The `sync` verb calls `runtimes.public.ModelCatalogSyncJob` directly | P08.01.b → I-05.2 |
| `src/skm/entrypoints/cli/commands/storage.py` | GROUP | P15.01.a |
| `src/skm/entrypoints/cli/commands/token.py` | GROUP, duration, register; API token CLI `skm token` with verbs create, rotate, revoke, list over the `access` token commands and queries through the bus; a revealed secret is shown once and registered for redaction (backend group, module `access`) | P04.02.c |
| `src/skm/entrypoints/cli/commands/use.py` | GROUP, cli_context_path, cli_state_path, register, selects_instance_only; `skm use` local CLI context selector over `cli-context.json` and `cli-state.json` (backend group, module `workspace`) | P04.05 |
| `src/skm/entrypoints/cli/commands/version.py` | GROUP, register (`skm version`, no backend) | P02.08.a |
| `src/skm/entrypoints/cli/commands/whoami.py` | GROUP, register; `skm whoami` over `access.WhoAmI` through the bus (backend group, module `access`) | P04.02.c |
| `src/skm/entrypoints/cli/commands/worker.py` | GROUP, register, resolve_worker_view, worker_token_path; worker CLI `skm worker` with verbs register, list, show, status, drain, retire over `workspace` worker commands/queries and `workspace.host.rotate_worker_token` (backend group, module `workspace`) | P04.05 |
| `src/skm/entrypoints/cli/commands/workspace.py` | GROUP, register, resolve_workspace_id, resolve_workspace_view; workspace CLI `skm workspace` with verbs create, list, show and archive over `workspace` commands and queries, plus sync-projections via `integrations.host.sync_projections` (backend group, module `workspace`) | P04.05 |
| `src/skm/entrypoints/cli/context.py` | CliContext, CliOptions, CliSession, CONTEXT_SCHEMA; DraftId from planning.public | P00.04.f → P02.08.a → P11.07 |
| `src/skm/entrypoints/cli/editor.py` | EditorRunner, edit_document, resolve_editor | P02.08.a |
| `src/skm/entrypoints/cli/errors.py` | run_guarded, EXIT_OK, EXIT_USAGE, EXIT_INTERRUPTED, TRACEBACK_VERBOSITY | P00.04.f → P02.08.a |
| `src/skm/entrypoints/cli/host.py` | build_host_context, host_context_factory | P02.08.a |
| `src/skm/entrypoints/cli/main.py` | main, Backend, BackendFactory, app_backend, production_backend (composes through `open_cli_app`: bootstrap, application, acting principal) | P00.01 → P00.04.f → P02.08.a → P04.02.c |
| `src/skm/entrypoints/cli/output.py` | render, render_page, render_findings, render_waiting, render_error, render_table, kv_lines, Column, FindingLike, escape_terminal, safe_text, to_jsonable, CLI_EXIT, ENVELOPE_SCHEMA | P00.04.f → P02.08.a |
| `src/skm/entrypoints/cli/parser.py` | build_parser, parse_command_line, options_from, GLOBAL_FLAGS | P00.04.f → P02.08.a |
| `src/skm/entrypoints/cli/refs.py` | RefKind, RefForm, CliRef, ScopeSelector, parse_ref, parse_scope, default_scope_kind | P02.08.a |
| `src/skm/entrypoints/hook/__init__.py` | package boundary | P00.04.f |
| `src/skm/entrypoints/hook/daemon.py` | skm-hookd console entry point | P10.05.a → I-09.2c |
| `src/skm/entrypoints/hook/main.py` | main | P00.04.f → P10.05.a → P10.05.b → I-09.2c |
| `src/skm/entrypoints/mcp/__init__.py` | package boundary | P00.04.f |
| `src/skm/entrypoints/mcp/protocol.py` | Request, RpcError, JSON-RPC errors and NDJSON framing, negotiate_version | P11.05.a |
| `src/skm/entrypoints/mcp/registry.py` | ToolSpec, TOOLS, lookup_tool, export_tool, published_tools, tools_digest | P00.04.f → P11.05.a → P11.05.b |
| `src/skm/entrypoints/mcp/server.py` | serve (stdio JSON-RPC loop and tool dispatch) | P00.04.f → P11.05.a |
| `src/skm/entrypoints/mcp/session.py` | McpSession, LocalMemorySession, DEFAULT_MAX_RESPONSE_TOKENS | P00.04.f → P11.05.a → I-09.4 |
| `src/skm/entrypoints/mcp/tools/local_memory.py` | Host-only episodic record, search and summarize | P11.05.a → I-09.4 |
| `src/skm/entrypoints/mcp/tools/__init__.py` | package boundary | P00.04.f |
| `src/skm/entrypoints/mcp/tools/memory.py` | Project-bound memory, lessons, graph neighbors and graph paths | P13.01.c → P13.02.b |
| `src/skm/entrypoints/mcp/tools/notes.py` | record_note, record_step_note; assignment-bound note dispatch | P11.05.b |
| `src/skm/entrypoints/mcp/tools/plan.py` | Project-scoped plan and revision reads, pinned entity/text reads, draft and publication tools | P11.05.b |
| `src/skm/entrypoints/mcp/tools/questions.py` | ask_question, decision_summary, inbox_list | P11.05.b |
| `src/skm/entrypoints/mcp/tools/task.py` | run_history, run_status, task_context, task_status | P11.05.b |
| `src/skm/entrypoints/mcp/truncation.py` | fit, estimate_tokens, TruncationReceipt, AuthoringReceipt, AuthoringReceipts, AUTHORING_READS | P11.05.a |
| `src/skm/entrypoints/worker/__init__.py` | package boundary | P00.04.f |
| `src/skm/entrypoints/worker/main.py` | main | P00.04.f → P07.07.b → P11.04.b |
| `src/skm/kernel/__init__.py` | package boundary | P00.04.a |
| `src/skm/kernel/error_codes.py` | error catalog facade | P01.02 |
| `src/skm/kernel/errors.py` | structured errors | P01.02 |
| `src/skm/kernel/generated/__init__.py` | generated package boundary | P01.02 |
| `src/skm/kernel/generated/error_codes.py` | generated error catalog | P01.02 |
| `src/skm/kernel/isolation.py` | IsolationProfile, plugin profiles | P01.01 |
| `src/skm/kernel/languages.py` | ECOSYSTEMS, language_for_ecosystem, language_for_path | P00.04.a → I-03.3 |
| `src/skm/kernel/outcomes.py` | Result, Ok, Err | P01.02 |
| `src/skm/kernel/path_globs.py` | globs_overlap, covers, bare | P05.03.a |
| `src/skm/kernel/pagination.py` | Cursor, Page, PageRequest | P01.01 |
| `src/skm/platform/system_clock.py` | system clock | P01.02 |
| `src/skm/platform/storage/__init__.py` | Package for storage reports and repair planning | P15.01.a |
| `src/skm/platform/storage/backup.py` | create_backup, ExportedSnapshot | P15.01.b |
| `src/skm/platform/storage/repair.py` | selected_codes, repair_report | P15.01.a |
| `src/skm/platform/storage/restore.py` | verify_backup, restore_backup, activate_restore | P15.01.b |
| `src/skm/platform/storage/verify.py` | LEVELS, CATALOG, Finding, ObjectInventory | P15.01.a |
| `src/skm/platform/system_entropy.py` | system entropy | P01.02 |
| `src/skm/platform/system_ids.py` | system identifiers | P01.02 |
| `src/skm/kernel/actor.py` | PrincipalKind, TokenGrant, Actor, SYSTEM_PRINCIPAL_ID | P00.04.a → P01.01 |
| `src/skm/kernel/cancel.py` | CancelToken, Cancelled | P00.04.a → P01.06.c |
| `src/skm/kernel/clock.py` | Clock, Monotonic | P00.04.a → P01.02 |
| `src/skm/kernel/data_classification.py` | HOST_PRIVATE data classification | P09.04.a → I-09.4 |
| `src/skm/kernel/entropy.py` | EntropySource | P00.04.a → P01.02 |
| `src/skm/kernel/events.py` | STREAM_KINDS, DomainEvent, EventEnvelope | P00.04.a → P01.07 |
| `src/skm/kernel/gateways.py` | GatewayTableKind, Gateways, GatewayTable, control_plane_gateway, host_gateway, shared_gateway | P00.04.a → P01.09.a |
| `src/skm/kernel/id_generator.py` | IdGenerator | P00.04.a → P01.02 |
| `src/skm/kernel/ids.py` | UUID7_MAX_RAND_A, UUID7_MAX_RAND_B | P00.04.a → P01.01 |
| `src/skm/kernel/json_types.py` | JsonScalar, JsonValue, JsonObject | P00.04.a → P01.01 |
| `src/skm/kernel/module_manifest.py` | HostOperationSpec, ModuleManifest | P00.04.a |
| `src/skm/kernel/ports_uow.py` | PORT_KIND_ATTRIBUTE, PortKind, Surface, Isolation, RequestMeta, OutboxEnqueuer, UnitOfWork, UnitOfWorkFactory, repository_port | P00.04.a → P01.08.a |
| `src/skm/kernel/scopes.py` | ScopeKind, ALLOWED_PARENTS, ScopeRef, ScopeRecord, ScopeRegistry, check_scope_parent, check_scope_workspace, scope_not_found | P00.04.a |
| `src/skm/kernel/tokens.py` | TokenEstimator | P00.04.a |
| `src/skm/kernel/versions.py` | ExpectedVersion | P00.04.a → P01.01 → P01.02 |
| `src/skm/kernel/yaml_scalars.py` | parse_quoted_yaml_string | P10.07 → SKM 0.2.0 P03 |
| `src/skm/modules/__init__.py` | package boundary | P00.04.a |
| `src/skm/modules/access/__init__.py` | package boundary | P00.04.b |
| `src/skm/modules/access/application/__init__.py` | package boundary | P00.04.b → P04.02.a |
| `src/skm/modules/access/application/authorizer.py` | RbacAuthorizer (the production `Authorizer`: admits a live, enabled principal and its token binding; permission checks go through `authz`) | P04.02.c |
| `src/skm/modules/access/application/authentication.py` | authenticate_token | P04.02.a |
| `src/skm/modules/access/application/authz.py` | BUS_REASON, chain_of, decision, effective, ensure_live, is_instance_owner, refuse, require, workspace_id_of | P04.02.a |
| `src/skm/modules/access/application/pairing.py` | issue_pairing_token, lock_pairing_token, consume_pairing_token | P04.02.b → I-10.1a |
| `src/skm/modules/access/application/passwords.py` | set_first_password, authenticate_local_owner_password | P04.02.b → I-10.1a |
| `src/skm/modules/access/application/sessions.py` | create_web_session, authenticate_web_session, revoke_web_session, revoke_all_web_sessions, resolve_local_owner | P04.02.b → I-10.1b |
| `src/skm/modules/access/application/commands/__init__.py` | package boundary | P00.04.b → P04.02.a |
| `src/skm/modules/access/application/commands/bootstrap_local_owner.py` | SPEC, handle | P04.02.a |
| `src/skm/modules/access/application/commands/create_principal.py` | SPEC, handle | P04.02.a |
| `src/skm/modules/access/application/commands/create_token.py` | SPEC, handle, scope_of | P04.02.a |
| `src/skm/modules/access/application/commands/disable_principal.py` | SPEC, handle | P04.02.a |
| `src/skm/modules/access/application/commands/grant_membership.py` | SPEC, handle, scope_of | P04.02.a |
| `src/skm/modules/access/application/commands/revoke_membership.py` | SPEC, handle, scope_of | P04.02.a |
| `src/skm/modules/access/application/commands/revoke_token.py` | SPEC, handle | P04.02.a |
| `src/skm/modules/access/application/commands/rotate_token.py` | SPEC, handle, require_manageable | P04.02.a |
| `src/skm/modules/access/application/delegation.py` | ensure_scope_within_grant, ensure_token_fits_grant, scope_within | P04.02.a |
| `src/skm/modules/access/application/events.py` | PrincipalCreated, PrincipalDisabled, TokenCreated, TokenRotated, TokenRevoked, MembershipGranted, MembershipRevoked | P04.02.a |
| `src/skm/modules/access/application/facade.py` | create_worker_principal, issue_assignment_token, extend_assignment_tokens, revoke_assignment_tokens, grant_initial_membership, revoke_principal_tokens | P04.02.a |
| `src/skm/modules/access/application/queries/__init__.py` | package boundary | P00.04.b → P04.02.a |
| `src/skm/modules/access/application/queries/get_principal.py` | SPEC, handle | P04.02.a |
| `src/skm/modules/access/application/queries/list_memberships.py` | SPEC, handle, scope_of | P04.02.a |
| `src/skm/modules/access/application/queries/list_principals.py` | SPEC, handle | P04.02.a |
| `src/skm/modules/access/application/queries/list_tokens.py` | SPEC, handle | P04.02.a |
| `src/skm/modules/access/application/queries/whoami.py` | SPEC, all_memberships, handle, scope_of | P04.02.a |
| `src/skm/modules/access/application/registry.py` | COMMANDS, QUERIES | P00.04.b → P04.02.a |
| `src/skm/modules/access/application/scopes.py` | scope_by_id | P04.02.a |
| `src/skm/modules/access/application/subscribers.py` | SUBSCRIBERS | P00.04.b → P04.02.a |
| `src/skm/modules/access/application/tokens.py` | PREFIX_ATTEMPTS, add_with_fresh_secret, default_settings, fresh_secret, record_created, record_revoked, workspace_of_scope | P04.02.a |
| `src/skm/modules/access/application/views.py` | membership_view, principal_summary, principal_view, token_summary | P04.02.a |
| `src/skm/modules/access/domain/__init__.py` | package boundary | P00.04.b |
| `src/skm/modules/access/domain/authorization.py` | DenyReason, Allowed, Denied, AuthzDecision | P00.04.b → P04.01 |
| `src/skm/modules/access/domain/events.py` | EVENT_TYPES | P00.04.b → P04.01 |
| `src/skm/modules/access/domain/identity.py` | LOCAL_ISSUER, PrincipalIdentity | P00.04.b → P04.01 |
| `src/skm/modules/access/domain/membership.py` | Membership | P00.04.b → P04.01 |
| `src/skm/modules/access/domain/principal.py` | PrincipalState, Principal | P00.04.b → P04.01 |
| `src/skm/modules/access/domain/roles.py` | Role, ROLE_RANK, ROLE_PERMISSIONS | P00.04.b → P04.01 → P09.09.a |
| `src/skm/modules/access/domain/token.py` | TokenKind, TokenState, TokenSecret, ApiToken | P00.04.b → P04.01 |
| `src/skm/modules/access/domain/pairing.py` | PairingToken, PairingResult | P04.02.b → I-10.1a |
| `src/skm/modules/access/domain/session.py` | WebSession | P04.02.b → I-10.1b |
| `src/skm/modules/access/module.py` | MODULE | P00.04.b → P04.02.a |
| `src/skm/modules/access/permissions.py` | PERMISSIONS | P00.04.b → P04.02.a |
| `src/skm/modules/access/ports.py` | PrincipalRepository, IdentityRepository, TokenRepository, MembershipRepository, TokenPepperSource, WorkerHostLookup | P00.04.b → P04.02.a |
| `src/skm/modules/access/public.py` | authenticate_token, effective_permissions, role_permissions, create_worker_principal, issue_assignment_token, extend_assignment_tokens, revoke_assignment_tokens, generate_secret, grant_initial_membership, revoke_principal_tokens, SYSTEM_ACTOR, RbacAuthorizer | P00.04.b → P04.02.a → P04.02.c → P09.09.a |
| `src/skm/modules/access/settings.py` | SECTION_URNS, SECTION_URN | P00.04.b → P02.02 |
| `src/skm/modules/artifacts/__init__.py` | package boundary | P00.04.b |
| `src/skm/modules/artifacts/application/__init__.py` | package boundary | P00.04.b → P06.03.a |
| `src/skm/modules/artifacts/application/admission.py` | AdmissionPolicy, admission_policy, content_kind, scan_staged, scan_and_admit | P06.03.a |
| `src/skm/modules/artifacts/application/commands/__init__.py` | package boundary | P00.04.b → P06.03.a |
| `src/skm/modules/artifacts/application/commands/add_file.py` | SPEC, handle, scope_of | P06.03.a → P06.03.c |
| `src/skm/modules/artifacts/application/commands/add_file_version.py` | SPEC, handle | P06.03.a → P06.03.c |
| `src/skm/modules/artifacts/application/commands/expire_staged_blobs.py` | SPEC, handle | P06.03.d |
| `src/skm/modules/artifacts/application/commands/prune_orphan_objects.py` | SPEC, handle | P06.03.d |
| `src/skm/modules/artifacts/application/commands/record_staged_blob.py` | SPEC, handle, scope_of | P06.03.c |
| `src/skm/modules/artifacts/application/commands/restore_file.py` | SPEC, handle | P06.03.a |
| `src/skm/modules/artifacts/application/commands/trash_file.py` | SPEC, handle | P06.03.a |
| `src/skm/modules/artifacts/application/events.py` | FileAdded, FileVersionAdded, FileTrashed, FileRestored | P06.03.a |
| `src/skm/modules/artifacts/application/guards.py` | can_read_version, file_scope, file_scope_of_file, file_scope_of_version, holds, holds_grant, require, require_bound, require_file, require_not_worker, require_version_read | P06.03.a |
| `src/skm/modules/artifacts/application/queries/__init__.py` | package boundary | P00.04.b → P06.03.a |
| `src/skm/modules/artifacts/application/queries/find_orphan_blobs.py` | SPEC, collect_orphan_report, handle | P06.03.d |
| `src/skm/modules/artifacts/application/queries/get_file.py` | SPEC, handle | P06.03.a |
| `src/skm/modules/artifacts/application/queries/get_file_version.py` | SPEC, handle | P06.03.a |
| `src/skm/modules/artifacts/application/queries/list_file_versions.py` | SPEC, handle | P06.03.a |
| `src/skm/modules/artifacts/application/queries/list_files.py` | SPEC, handle, scope_of | P06.03.a |
| `src/skm/modules/artifacts/application/queries/open_file_version_content.py` | SPEC, handle | P06.03.a |
| `src/skm/modules/artifacts/application/reads.py` | open_text, present_location, read_up_to, ready, require_present_location, version_blob, version_view_of | P06.03.a |
| `src/skm/modules/artifacts/application/registration.py` | register | P06.03.a |
| `src/skm/modules/artifacts/application/registry.py` | COMMANDS, QUERIES | P00.04.b → P06.03.a → P06.03.c → P06.03.d |
| `src/skm/modules/artifacts/application/safety_rules.py` | build_safety_rules | P06.03.a |
| `src/skm/modules/artifacts/application/staging.py` | StagedBlobView, consume_staged, ensure_blob | P06.03.a |
| `src/skm/modules/artifacts/application/subscribers.py` | SUBSCRIBERS | P00.04.b → P06.03.a |
| `src/skm/modules/artifacts/application/upload.py` | UploadDeps, bind_embedded_upload, open_file_version_content_embedded, upload_blob_embedded | P06.03.c |
| `src/skm/modules/artifacts/application/versions.py` | VersionDraft, append_version, create_file | P06.03.a |
| `src/skm/modules/artifacts/application/views.py` | add_file_safety, add_version_safety, file_summary, file_version_ref, file_view, get_file_version_view, literal, source_from_command, version_view | P06.03.a |
| `src/skm/modules/artifacts/domain/__init__.py` | package boundary | P00.04.b |
| `src/skm/modules/artifacts/domain/access_grant.py` | GrantReason, AccessGrant | P00.04.b → P06.01.a |
| `src/skm/modules/artifacts/domain/binding.py` | FileVersionRef, BindingRole | P00.04.b → P06.01.a |
| `src/skm/modules/artifacts/domain/blob.py` | BlobAvailability, LocationState, ContentDigest, Blob, BlobLocation | P00.04.b → P06.01.a |
| `src/skm/modules/artifacts/domain/classification.py` | Classification | P00.04.b → P06.01.a |
| `src/skm/modules/artifacts/domain/content_safety.py` | SafetyLevel, ContentKind, SafetyRules, SafetyFinding, SafetyReport | P00.04.b → P06.01.b |
| `src/skm/modules/artifacts/domain/events.py` | EVENT_TYPES | P00.04.b → P06.01.a |
| `src/skm/modules/artifacts/domain/file.py` | FileState, FileOrigin, File | P00.04.b → P06.01.a |
| `src/skm/modules/artifacts/domain/file_version.py` | VersionSource, FileVersion | P00.04.b → P06.01.a |
| `src/skm/modules/artifacts/domain/materialization.py` | MaterialEntry, MaterialPlan | P00.04.b → P06.01.b |
| `src/skm/modules/artifacts/domain/orphans.py` | OrphanObject, MissingObject, OrphanReport, orphan_report_digest, build_orphan_report, prunable, parse_object_storage_key | P00.04.b → P06.03.d |
| `src/skm/modules/artifacts/domain/staged_blob.py` | StagedBlobRef, StagedBlob | P00.04.b → P06.01.a |
| `src/skm/modules/artifacts/domain/storage_backend.py` | BackendKind, BackendState, StorageBackend | P00.04.b → P06.01.a |
| `src/skm/modules/artifacts/domain/upload_rules.py` | EXECUTABLE_TYPES, MEDIA_SIGNATURES, OCTET_STREAM, MediaSignature, detect_media_type, media_type_consistent, normalize_media_type, validate_filename | P06.01.b |

## MCP tool schemas

| File | Contract | Owner |
|---|---|---|
| `src/skm/schemas/mcp/tool-input-ask-question.v1.json` | skm_ask_question input schema | P11.05.a |
| `src/skm/schemas/mcp/tool-input-fetch.v1.json` | skm_fetch input schema | P11.05.a |
| `src/skm/schemas/mcp/tool-input-graph-neighbors.v1.json` | skm_graph_neighbors input schema | P13.02.b |
| `src/skm/schemas/mcp/tool-input-graph-path.v1.json` | skm_graph_path input schema | P13.02.b |
| `src/skm/schemas/mcp/tool-input-inbox-list.v1.json` | skm_inbox_list input schema | P11.05.a |
| `src/skm/schemas/mcp/tool-input-lessons-list.v1.json` | skm_lessons_list input schema | P11.05.a |
| `src/skm/schemas/mcp/tool-input-memory-forget.v1.json` | skm_memory_forget input schema | P13.01.c |
| `src/skm/schemas/mcp/tool-input-memory-remember.v1.json` | skm_memory_remember input schema | P11.05.a |
| `src/skm/schemas/mcp/tool-input-memory-search.v1.json` | skm_memory_search input schema | P11.05.a |
| `src/skm/schemas/mcp/tool-input-local-memory-record.v1.json` | skm_local_memory_record input schema | P11.05.a → I-09.4 |
| `src/skm/schemas/mcp/tool-input-local-memory-search.v1.json` | skm_local_memory_search input schema | P11.05.a → I-09.4 |
| `src/skm/schemas/mcp/tool-input-local-memory-summarize.v1.json` | skm_local_memory_summarize input schema | P11.05.a → I-09.4 |
| `src/skm/schemas/mcp/tool-input-plan-draft-abandon.v1.json` | skm_plan_draft_abandon input schema | P11.05.a |
| `src/skm/schemas/mcp/tool-input-plan-draft-open.v1.json` | skm_plan_draft_open input schema | P11.05.a |
| `src/skm/schemas/mcp/tool-input-plan-draft-rebase.v1.json` | skm_plan_draft_rebase input schema | P11.05.a |
| `src/skm/schemas/mcp/tool-input-plan-draft-save.v1.json` | skm_plan_draft_save input schema | P11.05.a |
| `src/skm/schemas/mcp/tool-input-plan-entities.v1.json` | skm_plan_entities input schema | P11.05.a |
| `src/skm/schemas/mcp/tool-input-plan-entity.v1.json` | skm_plan_entity input schema | P11.05.a |
| `src/skm/schemas/mcp/tool-input-plan-list.v1.json` | skm_plan_list input schema | P11.05.a |
| `src/skm/schemas/mcp/tool-input-plan-publication-preview.v1.json` | skm_plan_publication_preview input schema | P11.05.a |
| `src/skm/schemas/mcp/tool-input-plan-publish.v1.json` | skm_plan_publish input schema | P11.05.a |
| `src/skm/schemas/mcp/tool-input-plan-read-text.v1.json` | skm_plan_read_text input schema | P11.05.a |
| `src/skm/schemas/mcp/tool-input-plan-show.v1.json` | skm_plan_show input schema | P11.05.a |
| `src/skm/schemas/mcp/tool-input-record-note.v1.json` | skm_record_note input schema | P11.05.a |
| `src/skm/schemas/mcp/tool-input-run-history.v1.json` | skm_run_history input schema | P11.05.a |
| `src/skm/schemas/mcp/tool-input-run-status.v1.json` | skm_run_status input schema | P11.05.a |
| `src/skm/schemas/mcp/tool-input-task-context.v1.json` | skm_task_context input schema | P11.05.a |
| `src/skm/schemas/mcp/tool-input-task-status.v1.json` | skm_task_status input schema | P11.05.a |
| `src/skm/schemas/mcp/tool-output-ask-question.v1.json` | skm_ask_question output schema | P11.05.a |
| `src/skm/schemas/mcp/tool-output-fetch.v1.json` | skm_fetch output schema | P11.05.a |
| `src/skm/schemas/mcp/tool-output-graph-neighbors.v1.json` | skm_graph_neighbors output schema | P13.02.b |
| `src/skm/schemas/mcp/tool-output-graph-path.v1.json` | skm_graph_path output schema | P13.02.b |
| `src/skm/schemas/mcp/tool-output-inbox-list.v1.json` | skm_inbox_list output schema | P11.05.a |
| `src/skm/schemas/mcp/tool-output-lessons-list.v1.json` | skm_lessons_list output schema | P11.05.a |
| `src/skm/schemas/mcp/tool-output-memory-forget.v1.json` | skm_memory_forget output schema | P13.01.c |
| `src/skm/schemas/mcp/tool-output-memory-remember.v1.json` | skm_memory_remember output schema | P11.05.a |
| `src/skm/schemas/mcp/tool-output-memory-search.v1.json` | skm_memory_search output schema | P11.05.a |
| `src/skm/schemas/mcp/tool-output-local-memory-record.v1.json` | skm_local_memory_record output schema | P11.05.a → I-09.4 |
| `src/skm/schemas/mcp/tool-output-local-memory-search.v1.json` | skm_local_memory_search output schema | P11.05.a → I-09.4 |
| `src/skm/schemas/mcp/tool-output-local-memory-summarize.v1.json` | skm_local_memory_summarize output schema | P11.05.a → I-09.4 |
| `src/skm/schemas/mcp/tool-output-plan-draft-abandon.v1.json` | skm_plan_draft_abandon output schema | P11.05.a |
| `src/skm/schemas/mcp/tool-output-plan-draft-open.v1.json` | skm_plan_draft_open output schema | P11.05.a |
| `src/skm/schemas/mcp/tool-output-plan-draft-rebase.v1.json` | skm_plan_draft_rebase output schema | P11.05.a |
| `src/skm/schemas/mcp/tool-output-plan-draft-save.v1.json` | skm_plan_draft_save output schema | P11.05.a |
| `src/skm/schemas/mcp/tool-output-plan-entities.v1.json` | skm_plan_entities output schema | P11.05.a |
| `src/skm/schemas/mcp/tool-output-plan-entity.v1.json` | skm_plan_entity output schema | P11.05.a |
| `src/skm/schemas/mcp/tool-output-plan-list.v1.json` | skm_plan_list output schema | P11.05.a |
| `src/skm/schemas/mcp/tool-output-plan-publication-preview.v1.json` | skm_plan_publication_preview output schema | P11.05.a |
| `src/skm/schemas/mcp/tool-output-plan-publish.v1.json` | skm_plan_publish output schema | P11.05.a |
| `src/skm/schemas/mcp/tool-output-plan-read-text.v1.json` | skm_plan_read_text output schema | P11.05.a |
| `src/skm/schemas/mcp/tool-output-plan-show.v1.json` | skm_plan_show output schema | P11.05.a |
| `src/skm/schemas/mcp/tool-output-record-note.v1.json` | skm_record_note output schema | P11.05.a |
| `src/skm/schemas/mcp/tool-output-run-history.v1.json` | skm_run_history output schema | P11.05.a |
| `src/skm/schemas/mcp/tool-output-run-status.v1.json` | skm_run_status output schema | P11.05.a |
| `src/skm/schemas/mcp/tool-output-task-context.v1.json` | skm_task_context output schema | P11.05.a |
| `src/skm/schemas/mcp/tool-output-task-status.v1.json` | skm_task_status output schema | P11.05.a |
| `src/skm/schemas/mcp/tool-output-truncation-receipt.v1.json` | TruncationReceipt for list fields in rendered MCP responses | P11.05.b |
