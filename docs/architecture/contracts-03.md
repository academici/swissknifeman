# Contract inventory, part 3

| Признак | Control plane (bus handlers, подписчики) | Host operations |
|---|---|---|
| `src/skm/modules/policy/domain/calls.py` | FileRead, FileWrite, FileEdit, FileDelete, RunCommand, WebAccess, McpCall, ToolCall, tool_name | P00.04.c → P07.01.a |
| `src/skm/modules/policy/domain/repo_commands.py` | forge_write, gh_api_read, git_config_writes, git_dir_change, remote_operand | P07.01.a |
| `src/skm/modules/policy/domain/glob_overlap.py` | glob_overlap | P07.01.a |
| `src/skm/modules/policy/domain/paths.py` | PathScope, PathRule, PathPolicy, ScopeRoots, ScopedPath | P00.04.c → P07.01.a |
| `src/skm/modules/policy/domain/permission_set.py` | PermissionSet, PermissionLayer | P00.04.c → P07.01.a |
| `src/skm/modules/policy/domain/profiles.py` | PolicyProfile, BUILTIN_PROFILE_IDS | P00.04.c → P07.01.a |
| `src/skm/modules/policy/domain/render.py` | IsolationGrants, Violation, isolation_grants, operation_document, representable_paths, request_violations, view_document | P07.01.a |
| `src/skm/modules/policy/domain/rm_guard.py` | DELETE_PROGRAMS, RmTarget, rm_is_safe, rm_targets | P07.01.a |
| `src/skm/modules/policy/domain/rule_ladder.py` | GuardMode, LadderRule, LadderVerdict | P00.04.c → P07.01.a |
| `src/skm/modules/policy/domain/shell_scan.py` | ShellScan | P00.04.c → P07.01.a |
| `src/skm/modules/policy/domain/shell_words.py` | SimpleCommand | P00.04.c → P07.01.a |
| `src/skm/modules/policy/domain/tool_call.py` | EnforcementMode, DecisionOutcome, Allow, Ask, Deny, ToolDecision | P00.04.c → P07.01.a |
| `src/skm/modules/policy/domain/tool_intent.py` | EffectKind, EnforcementMode, RiskClass, IntentState, ToolIntent | P00.04.c → P07.01.b → I-04.1 |
| `src/skm/modules/policy/host/__init__.py` | package boundary | P07.01.b → I-04.1 |
| `src/skm/modules/policy/host/external_write.py` | write_external | P07.01.b → I-04.1 |
| `src/skm/modules/policy/module.py` | MODULE | P00.04.c → P07.01.b |
| `src/skm/modules/policy/permissions.py` | PERMISSIONS | P00.04.c → P07.01.b |
| `src/skm/modules/policy/ports.py` | ToolIntentRepository, ApprovalRepository, DecisionAuditRepository, PathFacts, ExternalFileWriter | P00.04.c → P07.01.b → I-04.1 |
| `src/skm/modules/policy/public.py` | check_tool_call, narrow, permission_set_from_view, task_authority_from_view, git_guard_check, managed_hit, managed_guard_verdict, changelog_gate_verdict, representable_paths, isolation_grants, permissions_digest, effective_permissions, task_authority, forbidden_paths_layer, propose_intent, require_approved, record_outcome, is_subset | P00.04.c → P07.01.a → P07.01.b → P10.05.a |
| `src/skm/modules/policy/settings.py` | SECTION_URN, SECTION_URNS | P00.04.c → P02.02 |
| `src/skm/modules/runtimes/__init__.py` | package boundary | P00.04.c |
| `src/skm/modules/runtimes/application/__init__.py` | package boundary | P00.04.c |
| `src/skm/modules/runtimes/application/commands/__init__.py` | package boundary | P00.04.c → P08.01.b |
| `src/skm/modules/runtimes/application/commands/record_capability_verification.py` | RecordCapabilityVerification, handle, SPEC | P08.01.b |
| `src/skm/modules/runtimes/application/commands/record_host_runtimes.py` | SENTINEL_DETECTED_AT, handle, SPEC | P08.01.b |
| `src/skm/modules/runtimes/application/queries/__init__.py` | package boundary | P00.04.c → P08.01.b |
| `src/skm/modules/runtimes/application/queries/explain_routing.py` | handle, SPEC | P08.01.b |
| `src/skm/modules/runtimes/application/queries/get_capabilities.py` | resolve_capabilities, handle, SPEC | P08.01.b |
| `src/skm/modules/runtimes/application/queries/list_models.py` | resolve_catalog, resolve_model_entry, resolve_usage_cost, handle, SPEC | P08.01.b |
| `src/skm/modules/runtimes/application/queries/list_runtimes.py` | ListRuntimesResult, handle, SPEC | P08.01.b |
| `src/skm/modules/runtimes/application/registry.py` | COMMANDS, QUERIES | P00.04.c → P08.01.b |
| `src/skm/modules/runtimes/application/subscribers.py` | SUBSCRIBERS | P00.04.c → P08.01.b |
| `src/skm/modules/runtimes/domain/__init__.py` | package boundary | P00.04.c |
| `src/skm/modules/runtimes/domain/admission.py` | Operation, ResumePolicy, OperationContext, PreviousRoute, FixBriefFacts, AdmissionFacts, AdmissionPolicy, AdmissionNote, Admission, FixBounds, ADMISSION_DEFAULTS, OPERATION_ROLES, classify_operation, operations_of_role, admit, admission_allows_resume, ResumeAllowance, session_policy_for, fix_within_bounds | P00.04.c → P08.11 |
| `src/skm/modules/runtimes/domain/capability.py` | Capability, CapabilityStatus, CapabilityRecord, VerificationContext, RuntimeCapabilities, SelfLoadKind, SelfLoad, ConfigIsolationSpec, SelfLoadView, explain_self_loads, self_loaded_instruction_files, config_mode_for, validate_verification_record | P00.04.c → P08.01.a → P08.01.b → P08.11 (explain_self_loads) |
| `src/skm/modules/runtimes/application/activate_catalog.py` | activate_staged_catalog | P08.01.b → I-05.2 |
| `src/skm/modules/runtimes/application/catalog_sources.py` | CatalogTransport, ModelsDevSource, OpenRouterSource, V1ModelsSource, FallbackGeneralizationsSource, default_adapters | P08.01.b → I-05.2 |
| `src/skm/modules/runtimes/application/catalog_sync_job.py` | ModelCatalogSyncJob | P08.01.b → I-05.2 |
| `src/skm/modules/runtimes/application/seed_catalog.py` | seed_builtin_model_catalog | P08.01.b → I-05.1 |
| `src/skm/modules/runtimes/application/host_availability.py` | Record and resolve fresh worker model snapshots and host previews | P08.01.b → I-05.3 · SKM 0.1.0 W02 |
| `src/skm/modules/runtimes/domain/catalog_records.py` | CanonicalModel, ProviderModelOffering, ModelGuideline, HostModelAvailability, WorkerModelSnapshot | P08.01.a → I-05.1 · SKM 0.1.0 W02 |
| `src/skm/modules/runtimes/domain/catalog_sync.py` | CatalogCandidate, StagedCandidate, CandidateTrust, CatalogSyncReport, stage_candidates, render_catalog_toml | P08.01.b → I-05.2 |
| `src/skm/modules/runtimes/domain/catalog.py` | Pricing, ModelStatus, ModelEntry, RuntimeCatalogEntry, ModelCatalog | P00.04.c → P08.01.a |
| `src/skm/modules/runtimes/domain/classes.py` | ModelClass, Effort, RoleId, MODEL_CLASS_ORDER, EFFORT_ORDER | P00.04.c → P08.01.a |
| `src/skm/modules/runtimes/domain/detection.py` | DetectProbe, CancellationResult, VerificationRecord | P00.04.c → P08.01.b → P08.02.b → P08.11 |
| `src/skm/modules/runtimes/domain/error_rules.py` | ErrorClass, ErrorScope, RuntimeSignals, ErrorRule, ProviderFailure, classify | P00.04.c → P08.01.a |
| `src/skm/modules/runtimes/domain/events.py` | EVENT_TYPES | P00.04.c → P08.01.b |
| `src/skm/modules/runtimes/domain/ids.py` | RuntimeId, ModelId, SessionRef, Digest | P00.04.c → P08.01.a |
| `src/skm/modules/runtimes/domain/installation.py` | AuthState, RuntimeInstallation | P00.04.c → P08.01.b |
| `src/skm/modules/runtimes/domain/observation.py` | ObservationBinding, ObservationTiming, CaptureObservation, ToolVisibility, RuntimeObservation, validate_runtime_observation | P00.04.c → P08.01.a |
| `src/skm/modules/runtimes/domain/genai_semconv.py` | GenAIInvocationSpan, agent_invocation_span | P08.01.a → I-12.3 |
| `src/skm/modules/runtimes/domain/request.py` | ResultFormat, RuntimeLimits, ProcessOwner, ProcessOwnership, PermissionGrant, McpServerSpec, AgentRequest | P00.04.c → P08.01.a |
| `src/skm/modules/runtimes/domain/result.py` | ExitInfo, ToolDenial, RuntimeResult | P00.04.c → P08.01.a |
| `src/skm/modules/runtimes/domain/routing.py` | RouteRequest, RouteConfig, RouteRejection, RouteDecision, route, RouteCandidate, RouteNeeds, route_needs, route_refusal | P00.04.c → P08.01.b → P08.11 (RouteNeeds, route_needs, route_refusal) |
| `src/skm/modules/runtimes/domain/session_events.py` | ToolCallStatus, StopReason, SessionStarted, TextDelta, ToolRequested, ToolCompleted, UsageReported, CheckpointAvailable, CancelIgnored, SessionCompleted, SessionFailed, SessionEvent | P00.04.c → P08.01.a |
| `src/skm/modules/runtimes/domain/usage.py` | UsageStatus, SubagentUsage, UsageReport, merge_usage, cost, fresh_tokens, cache_hit_rate, estimate_from_prompt | P00.04.c → P08.01.a → P09.04.a (I-06.3) |
| `src/skm/modules/runtimes/host/__init__.py` | package boundary | P00.04.c |
| `src/skm/modules/runtimes/host/detect_runtimes.py` | DetectRuntimesOperation | P00.04.c → P08.01.b |
| `src/skm/modules/runtimes/host/registry.py` | HOST_OPERATIONS | P00.04.c → P08.01.b |
| `src/skm/modules/runtimes/module.py` | MODULE | P00.04.c → P08.01.b |
| `src/skm/modules/runtimes/permissions.py` | PERMISSIONS | P00.04.c → P08.01.b |
| `src/skm/modules/runtimes/ports.py` | AgentRuntime, SessionHandle, RuntimeRegistry, CapabilityCatalog, HostRuntimeRepository, CapabilityVerificationRepository, ModelCatalogRepository, HostModelAvailabilityRepository, WorkerModelOfferPolicy (W02) | P00.04.c → P08.01.a |
| `src/skm/bootstrap/stage_broker.py` | Credential-bound Unix channel for assignment MCP tools | P07.05.a, P11.04.b, W03 |
| `src/skm/modules/runtimes/public.py` | admission_policy, route_role, catalog, capabilities, model_entry, usage_cost, cache_hit_rate, model_context_window, summarize_tool_activity, seed_builtin_model_catalog, ModelCatalogSyncJob, activate_staged_catalog | P00.04.c → P08.01.a → P08.11 → I-05.2 → P09.04.a (I-06.3) |
| `src/skm/modules/runtimes/settings.py` | SECTION_URN, SECTION_URNS | P00.04.c → P02.02 |
| `src/skm/modules/settings/__init__.py` | package boundary | P00.04.b |
| `src/skm/modules/settings/application/__init__.py` | package boundary | P00.04.b → P02.07.b |
| `src/skm/modules/settings/application/commands/__init__.py` | package boundary | P00.04.b → P02.07.b |
| `src/skm/modules/settings/application/commands/import_config.py` | SPEC, handle, DOCUMENT_MAX_BYTES | P02.07.b |
| `src/skm/modules/settings/application/commands/lock_value.py` | SPEC, handle, change_lock | P02.07.b |
| `src/skm/modules/settings/application/commands/remove_value.py` | SPEC, handle | P02.07.b |
| `src/skm/modules/settings/application/commands/set_value.py` | SPEC, handle, write_value | P02.07.b |
| `src/skm/modules/settings/application/commands/unlock_value.py` | SPEC, handle | P02.07.b |
| `src/skm/modules/settings/application/commands/unset_value.py` | SPEC, handle | P02.07.b |
| `src/skm/modules/settings/application/preview.py` | Preview, RegistryChecks, chain_kind, contribution_of | P02.07.b |
| `src/skm/modules/settings/application/queries/__init__.py` | package boundary | P00.04.b → P02.07.b |
| `src/skm/modules/settings/application/queries/explain_config.py` | SPEC, ExplainConfigResult, handle | P02.07.b |
| `src/skm/modules/settings/application/queries/export_config.py` | SPEC, handle | P02.07.b |
| `src/skm/modules/settings/application/queries/get_generation.py` | SPEC, handle | P02.07.b |
| `src/skm/modules/settings/application/queries/get_history.py` | SPEC, handle | P02.07.b |
| `src/skm/modules/settings/application/queries/get_host_config.py` | SPEC, handle | P02.07.b |
| `src/skm/modules/settings/application/queries/get_schema.py` | SPEC, handle; optional `scope` selects where the bus checks `config.read` before metadata (default instance) | P02.07.b → P02.08.b |
| `src/skm/modules/settings/application/queries/get_value.py` | SPEC, handle | P02.07.b |
| `src/skm/modules/settings/application/queries/list_entries.py` | SPEC, handle | P02.07.b |
| `src/skm/modules/settings/application/registry.py` | COMMANDS, QUERIES | P00.04.b → P02.07.b |
| `src/skm/modules/settings/application/project_keys.py` | Machine operator keys excluded from project settings | P02.07.b · SKM 0.1.0 A01 |
| `src/skm/modules/settings/application/rights.py` | BASE_PERMISSION, Rights, base_permission, key_write_permission, packaged_schemas, write_permissions | P02.07.b |
| `src/skm/modules/settings/application/scopes.py` | ScopeRefDto, Target, bus_scope_of, resolve_target_scope, scope_of | P02.07.b |
| `src/skm/modules/settings/application/subscribers.py` | SUBSCRIBERS | P00.04.b → P02.07.b |
| `src/skm/modules/settings/application/write_flow.py` | EntryWrite, WriteSession, candidate_problems, effective_view, entry_view, layer_view, raise_problems, safe_value | P02.07.b |
| `src/skm/modules/settings/domain/__init__.py` | package boundary | P00.04.b |
| `src/skm/modules/settings/domain/digest.py` | entries_digest | P02.07.a |
| `src/skm/modules/settings/domain/entry.py` | EntryOp, ConfigEntryId, ConfigEntry, new_entry, change_entry, set_lock, same_content, same_value, version_conflict | P00.04.b → P02.07.a |
| `src/skm/modules/settings/domain/events.py` | EVENT_TYPES, ConfigChanged, ConfigLocked, ConfigUnlocked, EntryChangeKind | P00.04.b → P02.07.b |
| `src/skm/modules/settings/domain/history.py` | ChangeKind, HistoryRecord, history_record | P00.04.b → P02.07.a |
| `src/skm/modules/settings/domain/import_plan.py` | ChangeType, EntryChange, ImportPlan, ImportDocument, plan_import | P00.04.b → P02.07.a |
| `src/skm/modules/settings/domain/worker_config.py` | Registered worker project limits and identifiers | P02.07.a · SKM 0.1.0 W01 |
| `src/skm/modules/settings/domain/write_rules.py` | WriteRequest, WriteContext, ValueChecks, KeySpecView, ResolutionView, Problem, required_permissions, check_write, collect_write_problems | P00.04.b → P02.07.a |
| `src/skm/modules/settings/module.py` | MODULE | P00.04.b → P02.07.b |
| `src/skm/modules/settings/permissions.py` | PERMISSIONS | P00.04.b → P02.07.b |
| `src/skm/modules/settings/ports.py` | ConfigEntryRepository, ConfigHistoryRepository, ConfigGenerationCounter | P00.04.b → P02.07.a |
| `src/skm/modules/settings/public.py` | settings DTOs, results and views, ExplainConfigResult, ScopeRefDto, entries_digest | P00.04.b → P02.07.b |
| `src/skm/modules/settings/settings.py` | SECTION_URNS | P00.04.b |
| `src/skm/modules/workspace/__init__.py` | package boundary | P00.04.b |
| `src/skm/modules/workspace/application/__init__.py` | package boundary | P00.04.b → P04.04.a |
| `src/skm/modules/workspace/application/commands/__init__.py` | package boundary | P00.04.b → P04.04.a |
| `src/skm/modules/workspace/application/commands/add_repository_remote.py` | SPEC, handle | P04.04.a |
| `src/skm/modules/workspace/application/commands/archive_project.py` | SPEC, handle | P04.04.a |
| `src/skm/modules/workspace/application/commands/archive_workspace.py` | SPEC, handle | P04.04.a |
| `src/skm/modules/workspace/application/commands/attach_repository.py` | SPEC, handle | P04.04.a |
| `src/skm/modules/workspace/application/commands/bind_checkout.py` | PERMISSION, SPEC, handle | P04.04.a |
| `src/skm/modules/workspace/application/commands/create_project.py` | SPEC, handle | P04.04.a |
| `src/skm/modules/workspace/application/commands/create_workspace.py` | SPEC, handle | P04.04.a |
| `src/skm/modules/workspace/application/commands/detach_repository.py` | SPEC, handle | P04.04.a |
| `src/skm/modules/workspace/application/commands/record_checkout_verification.py` | PERMISSION, SPEC, handle | P04.04.a |
| `src/skm/modules/workspace/application/commands/record_worker_heartbeat.py` | PERMISSION, SPEC, handle | P04.04.a |
| `src/skm/modules/workspace/application/commands/register_host.py` | SPEC, handle | P04.04.a |
| `src/skm/modules/workspace/application/commands/register_repository.py` | SPEC, handle | P04.04.a |
| `src/skm/modules/workspace/application/commands/register_worker.py` | SPEC, handle | P04.04.a |
| `src/skm/modules/workspace/application/commands/exchange_pairing_token.py` | SPEC, handle | P04.04.a → I-10.1a |
| `src/skm/modules/workspace/application/commands/set_worker_state.py` | PERMISSION, SPEC, handle | P04.04.a |
| `src/skm/modules/workspace/application/events.py` | CheckoutBindingVerified, CheckoutBound, HostRegistered, ProjectArchived, ProjectCreated, RepositoryAttached, RepositoryDetached, RepositoryRegistered, WorkerRegistered, WorkerStateChanged, WorkspaceArchived, WorkspaceCreated | P04.04.a |
| `src/skm/modules/workspace/application/guards.py` | SELF_PERMISSION, allow_unconfined, chain_of, holds, require, require_active_project, require_active_workspace, scope_ref, stale_after_days | P04.04.a |
| `src/skm/modules/workspace/application/locations.py` | resolve_location | P04.04.a |
| `src/skm/modules/workspace/application/queries/__init__.py` | package boundary | P00.04.b → P04.04.a |
| `src/skm/modules/workspace/application/queries/get_host.py` | SPEC, handle, scope_of | P04.04.a |
| `src/skm/modules/workspace/application/queries/get_project.py` | SPEC, handle | P04.04.a |
| `src/skm/modules/workspace/application/queries/get_workspace.py` | SPEC, handle | P04.04.a |
| `src/skm/modules/workspace/application/queries/list_hosts.py` | SPEC, handle | P04.04.a |
| `src/skm/modules/workspace/application/queries/list_project_repositories.py` | SPEC, handle | P04.04.a |
| `src/skm/modules/workspace/application/queries/list_projects.py` | SPEC, handle | P04.04.a |
| `src/skm/modules/workspace/application/queries/list_repositories.py` | SPEC, handle | P04.04.a |
| `src/skm/modules/workspace/application/queries/list_workers.py` | SPEC, handle | P04.04.a |
| `src/skm/modules/workspace/application/queries/list_workspaces.py` | SPEC, handle | P04.04.a |
| `src/skm/modules/workspace/application/queries/match_checkout.py` | SPEC, handle | P04.04.a |
| `src/skm/modules/workspace/application/queries/resolve_checkout.py` | SPEC, handle | P04.04.a |
| `src/skm/modules/workspace/application/registry.py` | COMMANDS, QUERIES | P00.04.b → P04.04.a |
| `src/skm/modules/workspace/application/subscribers.py` | SUBSCRIBERS | P00.04.b → P04.04.a |
| `src/skm/modules/workspace/application/views.py` | attach_decision_view, binding_variant, binding_view, capabilities_document, capabilities_from_document, host_view, literal, location_view, mount_view, platform_from_document, project_summary, project_view, repository_view, worker_view, workspace_summary, workspace_view | P04.04.a |
| `src/skm/modules/workspace/domain/__init__.py` | package boundary | P00.04.b → P04.03 |
| `src/skm/modules/workspace/domain/attach.py` | UseMarker, UseExistingRepository, CreateRepository, Refuse, AttachDecision | P00.04.b → P04.03 |
| `src/skm/modules/workspace/domain/checkout_binding.py` | BindingState, ObservedCheckout, CheckoutBinding | P00.04.b → P04.03 |
| `src/skm/modules/workspace/domain/checkout_marker.py` | CheckoutMarker | P00.04.b → P04.03 |
| `src/skm/modules/workspace/domain/events.py` | EVENT_TYPES | P00.04.b → P04.03 |
| `src/skm/modules/workspace/domain/host.py` | HostOs, HostArch, HostState, HostName, HostPlatform, Host | P00.04.b → P04.03 |
| `src/skm/modules/workspace/domain/mount.py` | MountRole, MountName, ProjectRepository | P00.04.b → P04.03 |
| `src/skm/modules/workspace/domain/project.py` | ProjectState, Project | P00.04.b → P04.03 |
| `src/skm/modules/workspace/domain/remote_url.py` | NormalizedRemote | P00.04.b → P04.03 |
| `src/skm/modules/workspace/domain/repository.py` | RepositoryProvider, Repository, RepositoryRemote | P00.04.b → P04.03 |
| `src/skm/modules/workspace/domain/slug.py` | Slug | P00.04.b → P04.03 |
| `src/skm/modules/workspace/domain/worker.py` | WorkerState, WorkerCapabilities, Worker | P00.04.b → P04.03 |
| `src/skm/modules/workspace/domain/workspace.py` | WorkspaceState, Workspace | P00.04.b → P04.03 |
| `src/skm/modules/workspace/host/__init__.py` | package boundary | P00.04.b → P04.05 |
| `src/skm/modules/workspace/host/bind_checkout.py` | BindCheckoutOperation | P00.04.b → P04.05 |
| `src/skm/modules/workspace/host/checkout_config.py` | checkout_marker_relpath, git_timeout_seconds | P04.05 |
| `src/skm/modules/workspace/host/checkout_transaction.py` | Local durable checkout transaction contract | P04.05 → SKM 0.1.0 A02 |
| `src/skm/modules/workspace/host/register_this_host.py` | RegisterThisHostOperation | P00.04.b → P04.05 |
| `src/skm/modules/workspace/host/registry.py` | HOST_OPERATIONS | P00.04.b → P04.05 |
| `src/skm/modules/workspace/host/rotate_worker_token.py` | RotateWorkerTokenOperation | P00.04.b → P04.05 |
| `src/skm/modules/workspace/host/verify_checkout.py` | VerifyCheckoutOperation | P00.04.b → P04.05 |
| `src/skm/modules/workspace/module.py` | MODULE | P00.04.b → P04.04.a |
| `src/skm/modules/workspace/permissions.py` | PERMISSIONS | P00.04.b → P04.04.a |
| `src/skm/modules/workspace/ports.py` | WorkspaceRepository, ProjectRepository, RepositoryRepository, MountRepository, HostRepository, CheckoutBindingRepository, WorkerRepository, RepositoryInspector | P00.04.b → P04.04.a → P04.06 |
| `src/skm/modules/workspace/public.py` | get_project, require_active_project, project_mounts, project_repositories, resolve_checkout, get_repository, get_worker, worker_for_principal, mark_workers_offline, scope_chain, workspace_of_project, require_active_workspace, require_repository, get_host, get_checkout_binding, primary_remote, list_online_workers, normalize_remote, redact_remote | P00.04.b → P04.04.a |
| `src/skm/modules/workspace/settings.py` | SECTION_URNS, SECTION_URN | P00.04.b → P02.02 |
| `src/skm/platform/__init__.py` | package boundary | P00.04.b |
| `src/skm/platform/machine.py` | MachineStore, local profile, session, checkout and retry records | P02.05.a → SKM 0.1.0 S01 |
| `src/skm/platform/config/__init__.py` | package boundary | P00.04.b |
| `src/skm/platform/config/effective.py` | EffectiveConfig, FrozenConfig, InvalidKey, InvalidReason, ProcessConfig, Provenance, normalize_numbers, registry_descriptor_digest, values_digest | P00.04.b → P02.04.a → P02.04.b |
| `src/skm/platform/config/keys.py` | Chain, Level, NarrowSpec, KeySpec and config metadata | P02.01 |
| `src/skm/platform/config/merge.py` | ContributionTrace, KeyResolution, is_unset_marker, deep_merge, apply_unset_markers, narrow_widens, narrow_value, fold | P02.03 |
| `src/skm/platform/config/layers.py` | LayerRef, Contribution, Layer | P02.01 |
| `src/skm/platform/config/scopes.py` | ScopeRef, ScopeChain | P02.01 |
| `src/skm/platform/config/scope_tree.py` | RegistryScopeTree | P02.01 |
| `src/skm/platform/config/loader.py` | ConfigLoader (generation cache, process capture), ProcessConfig re-export | P00.04.b → P02.06 |
| `src/skm/platform/config/validators.py` | SECTION_URNS, VALIDATORS, VIEWS | P02.09 |
| `src/skm/platform/config/explain.py` | build_explain, render_explain_text | P02.04.b |
| `src/skm/platform/config/resolver.py` | resolve | P02.04.a |
| `src/skm/platform/config/validation.py` | SectionValidatorFn, ValidatorFinding, check_section_validators, run_section_validators, validate_value | P02.04.a |
| `src/skm/platform/config/registry.py` | SectionValidatorFn, SettingsRegistry, schema_closure_digest | P00.04.b → P02.02 |
| `src/skm/platform/config/secrets.py` | SecretResolver; SecretRef value/parse/string | P00.04.b → P01.05.a (bounded amendment) → P02.05.b |
| `src/skm/platform/config/sources/__init__.py` | package boundary | P00.04.b |
| `src/skm/platform/config/store.py` | ConfigStore, ScopeTree, PackConfigSource, StoredContribution, EmptyPackConfigSource | P00.04.b → P02.06 |
| `src/skm/platform/fs/__init__.py` | package boundary | P00.04.b |
| `src/skm/platform/jsonc/canonical.py` | canonical JSON and scalar formatting | P01.03 |
| `src/skm/platform/jsonc/digest.py` | digest/v1 | P01.03 |
| `src/skm/platform/jsonc/__init__.py` | package boundary | P00.04.b |
| `src/skm/platform/logging/__init__.py` | package boundary | P00.04.b |
| `src/skm/platform/logging/logger.py` | StructLogger | P00.04.b → P01.06.a |
| `src/skm/platform/logging/redaction.py` | Redactor | P00.04.b → P01.06.a |
| `src/skm/platform/process/__init__.py` | package boundary | P00.04.b |
| `src/skm/platform/schema/findings.py` | schema issue and load errors | P01.04 |
| `src/skm/platform/schema/formats.py` | schema format checks | P01.04 |
| `src/skm/platform/schema/locator.py` | packaged schema locator | P01.04 |
| `src/skm/platform/schema/registry.py` | schema registry | P01.04 |
| `src/skm/platform/schema/validator.py` | schema validation; is_schema_type (stock Draft 2020-12 type predicate) | P01.04 |
| `src/skm/platform/schema/__init__.py` | package boundary | P00.04.b |
| `src/skm/platform/tokens/heuristic.py` | CHARS_PER_TOKEN_CYR, CHARS_PER_TOKEN_LAT, ESTIMATOR_ID, HeuristicTokenEstimator, estimate_tokens | P09.04.a |
| `src/skm/plugin_api/__init__.py` | API_VERSION and re-exports of the stable plugin API (manifest types, runtime contracts, Clock, TokenEstimator, errors, diagnostics) | P01.10 |
| `src/skm/plugin_api/manifest.py` | PLUGIN_ID_PATTERN, ComponentKind, Side, ComponentSpec, PluginManifest, PluginContext, requires_skm_matches | P01.10 |
| `src/skm/plugin_api/testing/__init__.py` | contract harness ContractCase, ContractFailure, ContractReport, run_contract_suite, FixedClock, plugin_test_context, manifest_contract_suite | P01.10 |
| `src/skm/py.typed` | typed package | P00.01 |
| `src/skm/schemas/access/commands/bootstrap-local-owner.v1.json` | urn:skm:access:command:bootstrap-local-owner:v1 | P00.04.b → P04.02.a |
| `src/skm/schemas/access/commands/create-principal.v1.json` | urn:skm:access:command:create-principal:v1 | P00.04.b → P04.02.a |
| `src/skm/schemas/access/commands/create-token.v1.json` | urn:skm:access:command:create-token:v1 | P00.04.b → P04.02.a |
| `src/skm/schemas/access/commands/disable-principal.v1.json` | urn:skm:access:command:disable-principal:v1 | P00.04.b → P04.02.a |
| `src/skm/schemas/access/commands/grant-membership.v1.json` | urn:skm:access:command:grant-membership:v1 | P00.04.b → P04.02.a |
| `src/skm/schemas/access/commands/revoke-membership.v1.json` | urn:skm:access:command:revoke-membership:v1 | P00.04.b → P04.02.a |
| `src/skm/schemas/access/commands/revoke-token.v1.json` | urn:skm:access:command:revoke-token:v1 | P00.04.b → P04.02.a |
| `src/skm/schemas/access/commands/rotate-token.v1.json` | urn:skm:access:command:rotate-token:v1 | P00.04.b → P04.02.a |
| `src/skm/schemas/access/defs.v1.json` | urn:skm:access:defs:v1 | P00.04.b → P04.02.a |
| `src/skm/schemas/access/scope-grant.v1.json` | urn:skm:access:scope-grant:v1 | P00.04.b → I-10.1a |
| `src/skm/schemas/access/events/membership-granted.v1.json` | urn:skm:access:event:membership-granted:v1 | P00.04.b → P04.01 |
| `src/skm/schemas/access/events/membership-revoked.v1.json` | urn:skm:access:event:membership-revoked:v1 | P00.04.b → P04.01 |
| `src/skm/schemas/access/events/principal-created.v1.json` | urn:skm:access:event:principal-created:v1 | P00.04.b → P04.01 |
| `src/skm/schemas/access/events/principal-disabled.v1.json` | urn:skm:access:event:principal-disabled:v1 | P00.04.b → P04.01 |
| `src/skm/schemas/access/events/token-created.v1.json` | urn:skm:access:event:token-created:v1 | P00.04.b → P04.02.a |
| `src/skm/schemas/access/events/token-revoked.v1.json` | urn:skm:access:event:token-revoked:v1 | P00.04.b → P04.01 |
| `src/skm/schemas/access/events/token-rotated.v1.json` | urn:skm:access:event:token-rotated:v1 | P00.04.b → P04.01 |
| `src/skm/schemas/access/queries/get-principal.v1.json` | urn:skm:access:query:get-principal:v1 | P00.04.b → P04.02.a |
| `src/skm/schemas/access/queries/list-memberships.v1.json` | urn:skm:access:query:list-memberships:v1 | P00.04.b → P04.02.a |
| `src/skm/schemas/access/queries/list-principals.v1.json` | urn:skm:access:query:list-principals:v1 | P00.04.b → P04.02.a |
| `src/skm/schemas/access/queries/list-tokens.v1.json` | urn:skm:access:query:list-tokens:v1 | P00.04.b → P04.02.a |
| `src/skm/schemas/access/queries/whoami.v1.json` | urn:skm:access:query:whoami:v1 | P00.04.b → P04.02.a |
| `src/skm/schemas/access/results/bootstrap-local-owner.v1.json` | urn:skm:access:result:bootstrap-local-owner:v1 | P00.04.b → P04.02.a |
| `src/skm/schemas/access/results/create-principal.v1.json` | urn:skm:access:result:create-principal:v1 | P00.04.b → P04.02.a |
| `src/skm/schemas/access/results/create-token.v1.json` | urn:skm:access:result:create-token:v1 | P00.04.b → P04.02.a |
| `src/skm/schemas/access/results/disable-principal.v1.json` | urn:skm:access:result:disable-principal:v1 | P00.04.b → P04.02.a |
| `src/skm/schemas/access/results/grant-membership.v1.json` | urn:skm:access:result:grant-membership:v1 | P00.04.b → P04.02.a |
| `src/skm/schemas/access/results/revoke-membership.v1.json` | urn:skm:access:result:revoke-membership:v1 | P00.04.b → P04.02.a |
| `src/skm/schemas/access/results/revoke-token.v1.json` | urn:skm:access:result:revoke-token:v1 | P00.04.b → P04.02.a |
| `src/skm/schemas/access/results/rotate-token.v1.json` | urn:skm:access:result:rotate-token:v1 | P00.04.b → P04.02.a |
| `src/skm/schemas/access/views/get-principal.v1.json` | urn:skm:access:view:get-principal:v1 | P00.04.b → P04.02.a |
| `src/skm/schemas/access/views/list-memberships.v1.json` | urn:skm:access:view:list-memberships:v1 | P00.04.b → P04.02.a |
| `src/skm/schemas/access/views/list-principals.v1.json` | urn:skm:access:view:list-principals:v1 | P00.04.b → P04.02.a |
| `src/skm/schemas/access/views/list-tokens.v1.json` | urn:skm:access:view:list-tokens:v1 | P00.04.b → P04.02.a |
| `src/skm/schemas/access/views/membership.v1.json` | urn:skm:access:view:membership:v1 | P00.04.b → P04.02.a → P04.02.c |
| `src/skm/schemas/access/views/principal-summary.v1.json` | urn:skm:access:view:principal-summary:v1 | P00.04.b → P04.02.a → P04.02.c |
| `src/skm/schemas/access/views/principal.v1.json` | urn:skm:access:view:principal:v1 | P00.04.b → P04.02.a → P04.02.c |
| `src/skm/schemas/access/views/token-summary.v1.json` | urn:skm:access:view:token-summary:v1 | P00.04.b → P04.02.a → P04.02.c |
| `src/skm/schemas/access/views/whoami.v1.json` | urn:skm:access:view:whoami:v1 | P00.04.b → P04.02.a |
| `src/skm/schemas/artifacts/commands/add-file-version.v1.json` | urn:skm:artifacts:command:add-file-version:v1 | P00.04.b → P06.03.a |
| `src/skm/schemas/artifacts/commands/add-file.v1.json` | urn:skm:artifacts:command:add-file:v1 | P00.04.b → P06.03.a |
| `src/skm/schemas/artifacts/commands/expire-staged-blobs.v1.json` | urn:skm:artifacts:command:expire-staged-blobs:v1 | P00.04.b → P06.03.a |
| `src/skm/schemas/artifacts/commands/prune-orphan-objects.v1.json` | urn:skm:artifacts:command:prune-orphan-objects:v1 | P00.04.b → P06.03.a |
| `src/skm/schemas/artifacts/commands/record-staged-blob.v1.json` | urn:skm:artifacts:command:record-staged-blob:v1 | P00.04.b → P06.03.a |
| `src/skm/schemas/artifacts/commands/restore-file.v1.json` | urn:skm:artifacts:command:restore-file:v1 | P00.04.b → P06.03.a |
| `src/skm/schemas/artifacts/commands/trash-file.v1.json` | urn:skm:artifacts:command:trash-file:v1 | P00.04.b → P06.03.a |
| `src/skm/schemas/artifacts/defs.v1.json` | urn:skm:artifacts:defs:v1 | P00.04.b → P06.03.a |
| `src/skm/schemas/artifacts/events/file-added.v1.json` | urn:skm:artifacts:event:file-added:v1 | P00.04.b → P06.01.a |
| `src/skm/schemas/artifacts/events/file-restored.v1.json` | urn:skm:artifacts:event:file-restored:v1 | P00.04.b → P06.01.a |
| `src/skm/schemas/artifacts/events/file-trashed.v1.json` | urn:skm:artifacts:event:file-trashed:v1 | P00.04.b → P06.01.a |
| `src/skm/schemas/artifacts/events/file-version-added.v1.json` | urn:skm:artifacts:event:file-version-added:v1 | P00.04.b → P06.01.a |
| `src/skm/schemas/artifacts/host/materialize-files.v1.json` | urn:skm:artifacts:host:materialize-files:v1 | P00.04.b → P06.03.a |
| `src/skm/schemas/artifacts/host/upload-file.v1.json` | urn:skm:artifacts:host:upload-file:v1 | P00.04.b → P06.03.a |
| `src/skm/schemas/artifacts/host-results/materialize-files.v1.json` | urn:skm:artifacts:host-result:materialize-files:v1 | P00.04.b → P06.03.a |
| `src/skm/schemas/artifacts/host-results/upload-file.v1.json` | urn:skm:artifacts:host-result:upload-file:v1 | P00.04.b → P06.03.a |
| `src/skm/schemas/artifacts/queries/find-orphan-blobs.v1.json` | urn:skm:artifacts:query:find-orphan-blobs:v1 | P00.04.b → P06.03.a |
| `src/skm/schemas/artifacts/queries/get-file-version.v1.json` | urn:skm:artifacts:query:get-file-version:v1 | P00.04.b → P06.03.a |
| `src/skm/schemas/artifacts/queries/get-file.v1.json` | urn:skm:artifacts:query:get-file:v1 | P00.04.b → P06.03.a |
| `src/skm/schemas/artifacts/queries/list-file-versions.v1.json` | urn:skm:artifacts:query:list-file-versions:v1 | P00.04.b → P06.03.a |
| `src/skm/schemas/artifacts/queries/list-files.v1.json` | urn:skm:artifacts:query:list-files:v1 | P00.04.b → P06.03.a |
| `src/skm/schemas/artifacts/queries/open-file-version-content.v1.json` | urn:skm:artifacts:query:open-file-version-content:v1 | P00.04.b → P06.03.a |
| `src/skm/schemas/artifacts/results/add-file-version.v1.json` | urn:skm:artifacts:result:add-file-version:v1 | P00.04.b → P06.03.a |
| `src/skm/schemas/artifacts/results/add-file.v1.json` | urn:skm:artifacts:result:add-file:v1 | P00.04.b → P06.03.a |
| `src/skm/schemas/artifacts/results/expire-staged-blobs.v1.json` | urn:skm:artifacts:result:expire-staged-blobs:v1 | P00.04.b → P06.03.a |
| `src/skm/schemas/artifacts/results/prune-orphan-objects.v1.json` | urn:skm:artifacts:result:prune-orphan-objects:v1 | P00.04.b → P06.03.a |
| `src/skm/schemas/artifacts/results/record-staged-blob.v1.json` | urn:skm:artifacts:result:record-staged-blob:v1 | P00.04.b → P06.03.a |
| `src/skm/schemas/artifacts/results/restore-file.v1.json` | urn:skm:artifacts:result:restore-file:v1 | P00.04.b → P06.03.a |
| `src/skm/schemas/artifacts/results/trash-file.v1.json` | urn:skm:artifacts:result:trash-file:v1 | P00.04.b → P06.03.a |
| `src/skm/schemas/artifacts/views/file-summary.v1.json` | urn:skm:artifacts:view:file-summary:v1 | P00.04.b → P06.01.a → P06.03.c → P06.03.a → P06.04.a |
| `src/skm/schemas/artifacts/views/file-version.v1.json` | urn:skm:artifacts:view:file-version:v1 | P00.04.b → P06.01.a → P06.03.c → P06.03.a → P06.04.a |
| `src/skm/schemas/artifacts/views/file.v1.json` | urn:skm:artifacts:view:file:v1 | P00.04.b → P06.01.a → P06.03.c → P06.03.a → P06.04.a |
| `src/skm/schemas/artifacts/views/find-orphan-blobs.v1.json` | urn:skm:artifacts:view:find-orphan-blobs:v1 | P00.04.b → P06.03.a → P06.03.d |
| `src/skm/schemas/artifacts/views/get-file-version.v1.json` | urn:skm:artifacts:view:get-file-version:v1 | P00.04.b → P06.03.a |
| `src/skm/schemas/artifacts/views/get-file.v1.json` | urn:skm:artifacts:view:get-file:v1 | P00.04.b → P06.03.a |
| `src/skm/schemas/artifacts/views/list-file-versions.v1.json` | urn:skm:artifacts:view:list-file-versions:v1 | P00.04.b → P06.03.a |
| `src/skm/schemas/artifacts/views/list-files.v1.json` | urn:skm:artifacts:view:list-files:v1 | P00.04.b → P06.03.a |
| `src/skm/schemas/artifacts/views/open-file-version-content.v1.json` | urn:skm:artifacts:view:open-file-version-content:v1 | P00.04.b → P06.03.a |
| `src/skm/schemas/config/bootstrap.v1.json` | urn:skm:config:bootstrap:v1 | P00.04.b → P02.01 → P11.07 |
| `src/skm/schemas/config/entry.v1.json` | urn:skm:config:entry:v1 | P00.04.b → P02.01 |
| `src/skm/schemas/config/explain.v1.json` | urn:skm:config:explain:v1 | P00.04.b → P02.01 → P02.04.b |
| `src/skm/schemas/config/frozen.v1.json` | urn:skm:config:frozen:v1 | P00.04.b → P02.01 → P02.04.b |
| `src/skm/schemas/config/key-spec.v1.json` | urn:skm:config:key-spec:v1 | P00.04.b → P02.01 |
| `src/skm/schemas/config/secret-ref.v1.json` | urn:skm:config:secret-ref:v1 | P00.04.b → P02.01 |
| `src/skm/schemas/context/assemble-request.v1.json` | urn:skm:context:assemble-request:v1 | P00.04.d → P09.04.a → P09.04.d → P09.09.a |
| `src/skm/schemas/context/commands/finalize-manifest.v1.json` | urn:skm:context:command:finalize-manifest:v1 | P00.04.d |
| `src/skm/schemas/context/commands/record-research-result.v1.json` | urn:skm:context:command:record-research-result:v1 | P00.04.d |
| `src/skm/schemas/context/defs.v1.json` | urn:skm:context:defs:v1 | P00.04.d → P09.04.a → P09.04.d → P09.09.a |
| `src/skm/schemas/context/draft.v1.json` | urn:skm:context:draft:v1 | P00.04.d → P09.04.a → P09.04.d → P09.09.a |
| `src/skm/schemas/context/finalized-context.v1.json` | urn:skm:context:finalized-context:v1 | P00.04.d → P09.04.a → P09.04.d → P09.09.a |
| `src/skm/schemas/context/host/research-query.v1.json` | urn:skm:context:host:research-query:v1 | P00.04.d |
| `src/skm/schemas/context/host-results/research-query.v1.json` | urn:skm:context:host-result:research-query:v1 | P00.04.d |
| `src/skm/schemas/context/manifest.v1.json` | urn:skm:context:manifest:v1 | P00.04.d |
| `src/skm/schemas/context/queries/check-research-access.v1.json` | urn:skm:context:query:check-research-access:v1 | P09.09.a → I-11.2 |
| `src/skm/schemas/context/queries/diff-contexts.v1.json` | urn:skm:context:query:diff-contexts:v1 | P00.04.d |
| `src/skm/schemas/context/queries/explain-context.v1.json` | urn:skm:context:query:explain-context:v1 | P00.04.d |
| `src/skm/schemas/context/queries/find-research-cache.v1.json` | urn:skm:context:query:find-research-cache:v1 | P00.04.d |
| `src/skm/schemas/context/queries/get-context-text.v1.json` | urn:skm:context:query:get-context-text:v1 | P00.04.d |
| `src/skm/schemas/context/queries/get-research-query.v1.json` | urn:skm:context:query:get-research-query:v1 | P00.04.d |
| `src/skm/schemas/context/queries/list-external-sources.v1.json` | urn:skm:context:query:list-external-sources:v1 | P00.04.d |
| `src/skm/schemas/context/research-result.v1.json` | urn:skm:context:research-result:v1 | P00.04.d |
| `src/skm/schemas/context/results/finalize-manifest.v1.json` | urn:skm:context:result:finalize-manifest:v1 | P00.04.d |
| `src/skm/schemas/context/results/record-research-result.v1.json` | urn:skm:context:result:record-research-result:v1 | P00.04.d |
| `src/skm/schemas/context/selection.v1.json` | urn:skm:context:selection:v1 | P00.04.d → P09.04.a → P09.04.d → P09.09.a |
| `src/skm/schemas/context/views/check-research-access.v1.json` | urn:skm:context:view:check-research-access:v1 | P09.09.a → I-11.2 |
| `src/skm/schemas/context/views/diff-contexts.v1.json` | urn:skm:context:view:diff-contexts:v1 | P00.04.d → P09.04.c |
| `src/skm/schemas/context/views/explain-context.v1.json` | urn:skm:context:view:explain-context:v1 | P00.04.d → P09.04.c |
| `src/skm/schemas/context/views/find-research-cache.v1.json` | urn:skm:context:view:find-research-cache:v1 | P00.04.d → P09.09.a |
| `src/skm/schemas/context/views/get-context-text.v1.json` | urn:skm:context:view:get-context-text:v1 | P00.04.d → P09.04.c |
| `src/skm/schemas/context/views/get-research-query.v1.json` | urn:skm:context:view:get-research-query:v1 | P00.04.d → P09.09.a |
| `src/skm/schemas/context/views/list-external-sources.v1.json` | urn:skm:context:view:list-external-sources:v1 | P00.04.d → P09.09.a |
| `src/skm/schemas/execution/blocking-reason-catalog.v1.json` | urn:skm:execution:blocking-reason-catalog:v1 | P00.04.d → P07.02 |
| `src/skm/schemas/execution/blocking-reason.v1.json` | urn:skm:execution:blocking-reason:v1 | P00.04.d → P07.02 |
| `src/skm/schemas/execution/commands/approve-revision.v1.json` | urn:skm:execution:command:approve-revision:v1 | P07.05.b → I-11.1 |
| `src/skm/schemas/execution/commands/accept-deviation.v1.json` | urn:skm:execution:command:accept-deviation:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/commands/acquire-integration-slot.v1.json` | urn:skm:execution:command:acquire-integration-slot:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/commands/answer-decision-request.v1.json` | urn:skm:execution:command:answer-decision-request:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/commands/autopilot-tick.v1.json` | urn:skm:execution:command:autopilot-tick:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/commands/begin-stage.v1.json` | urn:skm:execution:command:begin-stage:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/commands/cancel-run.v1.json` | urn:skm:execution:command:cancel-run:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/commands/carry-forward-result.v1.json` | urn:skm:execution:command:carry-forward-result:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/commands/claim-assignment.v1.json` | urn:skm:execution:command:claim-assignment:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/commands/detect-stalls.v1.json` | urn:skm:execution:command:detect-stalls:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/commands/drain-autopilot.v1.json` | urn:skm:execution:command:drain-autopilot:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/commands/enforce-timeouts.v1.json` | urn:skm:execution:command:enforce-timeouts:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/commands/expire-leases.v1.json` | urn:skm:execution:command:expire-leases:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/commands/mark-environments-removed.v1.json` | urn:skm:execution:command:mark-environments-removed:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/commands/pause-autopilot.v1.json` | urn:skm:execution:command:pause-autopilot:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/commands/pause-run.v1.json` | urn:skm:execution:command:pause-run:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/commands/reconcile-external-effect.v1.json` | urn:skm:execution:command:reconcile-external-effect:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/commands/reconfigure-run.v1.json` | urn:skm:execution:command:reconfigure-run:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/commands/record-external-effect.v1.json` | urn:skm:execution:command:record-external-effect:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/commands/record-manual-verdict.v1.json` | urn:skm:execution:command:record-manual-verdict:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/commands/record-stage-result.v1.json` | urn:skm:execution:command:record-stage-result:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/commands/record-step-note.v1.json` | urn:skm:execution:command:record-step-note:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/commands/release-assignment.v1.json` | urn:skm:execution:command:release-assignment:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/commands/release-integration-slot.v1.json` | urn:skm:execution:command:release-integration-slot:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/commands/renew-lease.v1.json` | urn:skm:execution:command:renew-lease:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/commands/report-attempt-failure.v1.json` | urn:skm:execution:command:report-attempt-failure:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/commands/request-review.v1.json` | urn:skm:execution:command:request-review:v1 | P00.04.d → P07.05.a → P09.10 |
| `src/skm/schemas/execution/commands/restart-task.v1.json` | urn:skm:execution:command:restart-task:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/commands/resume-run.v1.json` | urn:skm:execution:command:resume-run:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/commands/schedule-ready-tasks.v1.json` | urn:skm:execution:command:schedule-ready-tasks:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/commands/seal-output.v1.json` | urn:skm:execution:command:seal-output:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/commands/skip-task.v1.json` | urn:skm:execution:command:skip-task:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/commands/start-autopilot.v1.json` | urn:skm:execution:command:start-autopilot:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/commands/start-run.v1.json` | urn:skm:execution:command:start-run:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/commands/stop-autopilot.v1.json` | urn:skm:execution:command:stop-autopilot:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/commands/validate-for-execution.v1.json` | urn:skm:execution:command:validate-for-execution:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/decision-record.v1.json` | urn:skm:execution:decision-record:v1 | P00.04.d → P07.03.a |
| `src/skm/schemas/execution/defs.v1.json` | urn:skm:execution:defs:v1 | P00.04.d |
| `src/skm/schemas/execution/diagnostic-codes.v1.json` | urn:skm:execution:diagnostic-codes:v1 | P00.04.d |
| `src/skm/schemas/execution/events/acceptance-decided.v1.json` | urn:skm:execution:event:acceptance-decided:v1 | P00.04.d → P07.02 |
| `src/skm/schemas/execution/events/assignment-leased.v1.json` | urn:skm:execution:event:assignment-leased:v1 | P00.04.d → P07.02 |
| `src/skm/schemas/execution/events/attempt-ownership-lost.v1.json` | urn:skm:execution:event:attempt-ownership-lost:v1 | P00.04.d → P07.02 |
| `src/skm/schemas/execution/events/attempt-started.v1.json` | urn:skm:execution:event:attempt-started:v1 | P00.04.d → P07.02 |
| `src/skm/schemas/execution/events/autopilot-state-changed.v1.json` | urn:skm:execution:event:autopilot-state-changed:v1 | P00.04.d → P07.02 |
| `src/skm/schemas/execution/events/budget-exhausted.v1.json` | urn:skm:execution:event:budget-exhausted:v1 | P00.04.d → P07.02 |
| `src/skm/schemas/execution/events/check-completed.v1.json` | urn:skm:execution:event:check-completed:v1 | P00.04.d → P07.02 |
| `src/skm/schemas/execution/events/decision-answered.v1.json` | urn:skm:execution:event:decision-answered:v1 | P00.04.d → P07.02 |
| `src/skm/schemas/execution/events/decision-requested.v1.json` | urn:skm:execution:event:decision-requested:v1 | P00.04.d → P07.02 |
| `src/skm/schemas/execution/events/deviation-accepted.v1.json` | urn:skm:execution:event:deviation-accepted:v1 | P00.04.d → P07.02 |
| `src/skm/schemas/execution/events/external-effect-outcome-unknown.v1.json` | urn:skm:execution:event:external-effect-outcome-unknown:v1 | P00.04.d → P07.02 |
| `src/skm/schemas/execution/events/external-effect-recorded.v1.json` | urn:skm:execution:event:external-effect-recorded:v1 | P00.04.d → P07.02 |
| `src/skm/schemas/execution/events/followups-created.v1.json` | urn:skm:execution:event:followups-created:v1 | P00.04.d → P07.02 |
| `src/skm/schemas/execution/events/integration-completed.v1.json` | urn:skm:execution:event:integration-completed:v1 | P00.04.d → P07.02 |
| `src/skm/schemas/execution/events/lease-expired.v1.json` | urn:skm:execution:event:lease-expired:v1 | P00.04.d → P07.02 |
| `src/skm/schemas/execution/events/manual-verdict-recorded.v1.json` | urn:skm:execution:event:manual-verdict-recorded:v1 | P00.04.d → P07.02 |
| `src/skm/schemas/execution/events/monitor-evaluated.v1.json` | urn:skm:execution:event:monitor-evaluated:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/events/output-sealed.v1.json` | urn:skm:execution:event:output-sealed:v1 | P00.04.d → P07.02 |
| `src/skm/schemas/execution/events/readiness-reported.v1.json` | urn:skm:execution:event:readiness-reported:v1 | P00.04.d → P07.02 |
| `src/skm/schemas/execution/events/recovery-circuit-opened.v1.json` | urn:skm:execution:event:recovery-circuit-opened:v1 | P00.04.d → P07.02 |
| `src/skm/schemas/execution/events/review-completed.v1.json` | urn:skm:execution:event:review-completed:v1 | P00.04.d → P07.02 |
| `src/skm/schemas/execution/events/review-requested.v1.json` | urn:skm:execution:event:review-requested:v1 | P00.04.d → P07.02 |
| `src/skm/schemas/execution/events/run-cancelled.v1.json` | urn:skm:execution:event:run-cancelled:v1 | P00.04.d → P07.02 |
| `src/skm/schemas/execution/events/run-created.v1.json` | urn:skm:execution:event:run-created:v1 | P00.04.d → P07.02 |
| `src/skm/schemas/execution/events/run-finished.v1.json` | urn:skm:execution:event:run-finished:v1 | P00.04.d → P07.02 |
| `src/skm/schemas/execution/events/run-paused.v1.json` | urn:skm:execution:event:run-paused:v1 | P00.04.d → P07.02 |
| `src/skm/schemas/execution/events/run-reconfigured.v1.json` | urn:skm:execution:event:run-reconfigured:v1 | P00.04.d → P07.02 |
| `src/skm/schemas/execution/events/run-resumed.v1.json` | urn:skm:execution:event:run-resumed:v1 | P00.04.d → P07.02 |
| `src/skm/schemas/execution/events/run-started.v1.json` | urn:skm:execution:event:run-started:v1 | P00.04.d → P07.02 |
| `src/skm/schemas/execution/events/run-waiting.v1.json` | urn:skm:execution:event:run-waiting:v1 | P00.04.d → P07.02 |
| `src/skm/schemas/execution/events/runtime-start-admitted.v1.json` | urn:skm:execution:event:runtime-start-admitted:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/events/stage-completed.v1.json` | urn:skm:execution:event:stage-completed:v1 | P00.04.d → P07.02 |
| `src/skm/schemas/execution/events/stage-recovered.v1.json` | urn:skm:execution:event:stage-recovered:v1 | P00.04.d → P07.02 |
| `src/skm/schemas/execution/events/stage-started.v1.json` | urn:skm:execution:event:stage-started:v1 | P00.04.d → P07.02 |
| `src/skm/schemas/execution/events/step-observation-recorded.v1.json` | urn:skm:execution:event:step-observation-recorded:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/events/task-accepted.v1.json` | urn:skm:execution:event:task-accepted:v1 | P00.04.d → P07.02 |
| `src/skm/schemas/execution/events/task-assigned.v1.json` | urn:skm:execution:event:task-assigned:v1 | P00.04.d → P07.02 |
| `src/skm/schemas/execution/events/task-created.v1.json` | urn:skm:execution:event:task-created:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/events/task-failed.v1.json` | urn:skm:execution:event:task-failed:v1 | P00.04.d → P07.02 |
| `src/skm/schemas/execution/events/task-ready.v1.json` | urn:skm:execution:event:task-ready:v1 | P00.04.d → P07.02 |
| `src/skm/schemas/execution/events/task-rework-required.v1.json` | urn:skm:execution:event:task-rework-required:v1 | P00.04.d → P07.02 |
| `src/skm/schemas/execution/events/task-skipped.v1.json` | urn:skm:execution:event:task-skipped:v1 | P00.04.d → P07.02 |
| `src/skm/schemas/execution/events/task-wait-changed.v1.json` | urn:skm:execution:event:task-wait-changed:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/execution-bundle.v1.json` | urn:skm:execution:execution-bundle:v1 | P00.04.d → P07.02 |
| `src/skm/schemas/execution/execution-history.v1.json` | urn:skm:execution:execution-history:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/fix-brief.v1.json` | urn:skm:execution:fix-brief:v1 | P00.04.d → P07.04.a |
| `src/skm/schemas/execution/host/clean-environments.v1.json` | urn:skm:execution:host:clean-environments:v1 | P00.04.d |
| `src/skm/schemas/execution/host/request-review.v1.json` | urn:skm:execution:host:request-review:v1 | P00.04.d |
| `src/skm/schemas/execution/host/worker-loop.v1.json` | urn:skm:execution:host:worker-loop:v1 | P00.04.d |
| `src/skm/schemas/execution/host-results/clean-environments.v1.json` | urn:skm:execution:host-result:clean-environments:v1 | P00.04.d |
| `src/skm/schemas/execution/host-results/request-review.v1.json` | urn:skm:execution:host-result:request-review:v1 | P00.04.d |
| `src/skm/schemas/execution/host-results/worker-loop.v1.json` | urn:skm:execution:host-result:worker-loop:v1 | P00.04.d |
| `src/skm/schemas/execution/pending-continuation.v1.json` | urn:skm:execution:pending-continuation:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/queries/explain-autopilot.v1.json` | urn:skm:execution:query:explain-autopilot:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/queries/get-attempt.v1.json` | urn:skm:execution:query:get-attempt:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/queries/get-autopilot-status.v1.json` | urn:skm:execution:query:get-autopilot-status:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/queries/get-fix-brief.v1.json` | urn:skm:execution:query:get-fix-brief:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/queries/get-readiness-report.v1.json` | urn:skm:execution:query:get-readiness-report:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/queries/get-revision-visa.v1.json` | urn:skm:execution:query:get-revision-visa:v1 | P07.05.b → I-11.4 |
| `src/skm/schemas/execution/queries/get-review-receipt.v1.json` | urn:skm:execution:query:get-review-receipt:v1 | P00.04.d → P07.05.a → P09.10 |
| `src/skm/schemas/execution/queries/get-run-budget.v1.json` | urn:skm:execution:query:get-run-budget:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/queries/get-review-roi.v1.json` | urn:skm:execution:query:get-review-roi:v1 | P00.04.d → I-12.3 |
| `src/skm/schemas/execution/queries/get-run-health.v1.json` | urn:skm:execution:query:get-run-health:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/queries/get-run-history.v1.json` | urn:skm:execution:query:get-run-history:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/queries/get-run-timeline.v1.json` | urn:skm:execution:query:get-run-timeline:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/queries/get-run.v1.json` | urn:skm:execution:query:get-run:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/queries/get-execution-detail.v1.json` | urn:skm:execution:query:get-execution-detail:v1 | P12.05.a |
| `src/skm/schemas/execution/queries/get-step.v1.json` | urn:skm:execution:query:get-step:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/queries/verify-stage-access.v1.json` | urn:skm:execution:query:verify-stage-access:v1 | P07.05.a, W03 |
| `src/skm/schemas/execution/queries/get-task.v1.json` | urn:skm:execution:query:get-task:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/queries/list-decision-requests.v1.json` | urn:skm:execution:query:list-decision-requests:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/queries/list-execution-environments.v1.json` | urn:skm:execution:query:list-execution-environments:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/queries/list-runs.v1.json` | urn:skm:execution:query:list-runs:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/queries/list-task-attempts.v1.json` | urn:skm:execution:query:list-task-attempts:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/queries/list-tasks.v1.json` | urn:skm:execution:query:list-tasks:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/readiness-report.v1.json` | urn:skm:execution:readiness-report:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/results/approve-revision.v1.json` | urn:skm:execution:result:approve-revision:v1 | P07.05.b → I-11.1 |
| `src/skm/schemas/execution/results/accept-deviation.v1.json` | urn:skm:execution:result:accept-deviation:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/results/acquire-integration-slot.v1.json` | urn:skm:execution:result:acquire-integration-slot:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/results/answer-decision-request.v1.json` | urn:skm:execution:result:answer-decision-request:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/results/autopilot-tick.v1.json` | urn:skm:execution:result:autopilot-tick:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/results/begin-stage.v1.json` | urn:skm:execution:result:begin-stage:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/results/cancel-run.v1.json` | urn:skm:execution:result:cancel-run:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/results/carry-forward-result.v1.json` | urn:skm:execution:result:carry-forward-result:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/results/claim-assignment.v1.json` | urn:skm:execution:result:claim-assignment:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/results/detect-stalls.v1.json` | urn:skm:execution:result:detect-stalls:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/results/drain-autopilot.v1.json` | urn:skm:execution:result:drain-autopilot:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/results/enforce-timeouts.v1.json` | urn:skm:execution:result:enforce-timeouts:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/results/expire-leases.v1.json` | urn:skm:execution:result:expire-leases:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/results/mark-environments-removed.v1.json` | urn:skm:execution:result:mark-environments-removed:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/results/pause-autopilot.v1.json` | urn:skm:execution:result:pause-autopilot:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/results/pause-run.v1.json` | urn:skm:execution:result:pause-run:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/results/reconcile-external-effect.v1.json` | urn:skm:execution:result:reconcile-external-effect:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/results/reconfigure-run.v1.json` | urn:skm:execution:result:reconfigure-run:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/results/record-external-effect.v1.json` | urn:skm:execution:result:record-external-effect:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/results/record-manual-verdict.v1.json` | urn:skm:execution:result:record-manual-verdict:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/results/record-stage-result.v1.json` | urn:skm:execution:result:record-stage-result:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/results/record-step-note.v1.json` | urn:skm:execution:result:record-step-note:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/results/release-assignment.v1.json` | urn:skm:execution:result:release-assignment:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/results/release-integration-slot.v1.json` | urn:skm:execution:result:release-integration-slot:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/results/renew-lease.v1.json` | urn:skm:execution:result:renew-lease:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/results/report-attempt-failure.v1.json` | urn:skm:execution:result:report-attempt-failure:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/results/request-review.v1.json` | urn:skm:execution:result:request-review:v1 | P00.04.d → P07.05.a → P09.10 |
| `src/skm/schemas/execution/results/restart-task.v1.json` | urn:skm:execution:result:restart-task:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/results/resume-run.v1.json` | urn:skm:execution:result:resume-run:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/results/schedule-ready-tasks.v1.json` | urn:skm:execution:result:schedule-ready-tasks:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/results/seal-output.v1.json` | urn:skm:execution:result:seal-output:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/results/skip-task.v1.json` | urn:skm:execution:result:skip-task:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/results/start-autopilot.v1.json` | urn:skm:execution:result:start-autopilot:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/results/start-run.v1.json` | urn:skm:execution:result:start-run:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/results/stop-autopilot.v1.json` | urn:skm:execution:result:stop-autopilot:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/results/validate-for-execution.v1.json` | urn:skm:execution:result:validate-for-execution:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/role-result-advisor.v1.json` | urn:skm:execution:role-result:advisor:v1 | P00.04.d → P07.04.a |
| `src/skm/schemas/execution/role-result-executor.v1.json` | urn:skm:execution:role-result:executor:v1 | P00.04.d → P07.04.a |
| `src/skm/schemas/execution/role-result-registrar.v1.json` | urn:skm:execution:role-result:registrar:v1 | P00.04.d → P07.04.a |
| `src/skm/schemas/execution/role-result-researcher.v1.json` | urn:skm:execution:role-result:researcher:v1 | P00.04.d → P07.04.a |
| `src/skm/schemas/execution/role-result-reviewer.v1.json` | urn:skm:execution:role-result:reviewer:v1 | P00.04.d → P07.04.a |
| `src/skm/schemas/execution/role-result-scout.v1.json` | urn:skm:execution:role-result:scout:v1 | P00.04.d → P07.04.a |
| `src/skm/schemas/execution/role-result-triager.v1.json` | urn:skm:execution:role-result:triager:v1 | P00.04.d → P07.04.a |
| `src/skm/schemas/execution/route-snapshot.v1.json` | urn:skm:execution:route-snapshot:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/stage-outcome-acceptance-gate.v1.json` | urn:skm:execution:stage-outcome-acceptance-gate:v1 | P00.04.d → P07.05.a → P07.08.a → P07.05.c |
| `src/skm/schemas/execution/stage-outcome-advisor-consult.v1.json` | urn:skm:execution:stage-outcome-advisor-consult:v1 | P00.04.d |
| `src/skm/schemas/execution/stage-outcome-agent-review.v1.json` | urn:skm:execution:stage-outcome-agent-review:v1 | P00.04.d |
| `src/skm/schemas/execution/stage-outcome-agent-step.v1.json` | urn:skm:execution:stage-outcome-agent-step:v1 | P00.04.d |
| `src/skm/schemas/execution/stage-outcome-integrate.v1.json` | urn:skm:execution:stage-outcome-integrate:v1 | P00.04.d → P07.08.b |
| `src/skm/schemas/execution/stage-outcome-phase-gate.v1.json` | urn:skm:execution:stage-outcome-phase-gate:v1 | P00.04.d |
| `src/skm/schemas/execution/stage-outcome-plan-acceptance.v1.json` | urn:skm:execution:stage-outcome-plan-acceptance:v1 | P00.04.d |
| `src/skm/schemas/execution/stage-outcome-prepare-environment.v1.json` | urn:skm:execution:stage-outcome-prepare-environment:v1 | P00.04.d |
| `src/skm/schemas/execution/stage-outcome-run-checks.v1.json` | urn:skm:execution:stage-outcome-run-checks:v1 | P00.04.d → P07.11 |
| `src/skm/schemas/execution/stop-codes.v1.json` | urn:skm:execution:stop-codes:v1 | P00.04.d → P07.03.a |
| `src/skm/schemas/execution/views/explain-autopilot.v1.json` | urn:skm:execution:view:explain-autopilot:v1 | P00.04.d → P07.05.a → P08.12 |
| `src/skm/schemas/execution/views/get-attempt.v1.json` | urn:skm:execution:view:get-attempt:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/views/get-autopilot-status.v1.json` | urn:skm:execution:view:get-autopilot-status:v1 | P00.04.d → P07.05.a → P08.12 |
| `src/skm/schemas/execution/views/get-fix-brief.v1.json` | urn:skm:execution:view:get-fix-brief:v1 | P00.04.d → P07.05.a → P08.10 |
| `src/skm/schemas/execution/views/get-readiness-report.v1.json` | urn:skm:execution:view:get-readiness-report:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/views/revision-visa-status.v1.json` | urn:skm:execution:view:revision-visa-status:v1 | P07.05.b → I-11.4 |
| `src/skm/schemas/execution/views/get-review-receipt.v1.json` | urn:skm:execution:view:get-review-receipt:v1 | P00.04.d → P07.05.a → P09.10 |
| `src/skm/schemas/execution/views/get-run-budget.v1.json` | urn:skm:execution:view:get-run-budget:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/views/get-review-roi.v1.json` | urn:skm:execution:view:get-review-roi:v1 | P00.04.d → I-12.3 |
| `src/skm/schemas/execution/views/get-run-health.v1.json` | urn:skm:execution:view:get-run-health:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/views/get-run-history.v1.json` | urn:skm:execution:view:get-run-history:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/views/get-run-timeline.v1.json` | urn:skm:execution:view:get-run-timeline:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/views/get-run.v1.json` | urn:skm:execution:view:get-run:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/views/get-execution-detail.v1.json` | urn:skm:execution:view:get-execution-detail:v1 | P12.05.a |
| `src/skm/schemas/execution/views/get-step.v1.json` | urn:skm:execution:view:get-step:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/views/verify-stage-access.v1.json` | urn:skm:execution:view:verify-stage-access:v1 | P07.05.a, W03 |
| `src/skm/modules/execution/generated/_views_stage_access_view.py` | Generated StageAccessView | P07.05.a, W03 |
| `src/skm/schemas/execution/views/get-task.v1.json` | urn:skm:execution:view:get-task:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/views/list-decision-requests.v1.json` | urn:skm:execution:view:list-decision-requests:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/views/list-execution-environments.v1.json` | urn:skm:execution:view:list-execution-environments:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/views/list-runs.v1.json` | urn:skm:execution:view:list-runs:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/views/list-task-attempts.v1.json` | urn:skm:execution:view:list-task-attempts:v1 | P00.04.d → P07.05.a |
| `src/skm/schemas/execution/views/list-tasks.v1.json` | urn:skm:execution:view:list-tasks:v1 | P00.04.d → P07.05.a |

### I-12.2 Live control and tool-call metering

| File | Contract | Owner |
|---|---|---|
| `src/skm/schemas/execution/commands/abort-step.v1.json` | urn:skm:execution:command:abort-step:v1 | P07.05.b → I-12.2 |
| `src/skm/schemas/execution/commands/override-actor.v1.json` | urn:skm:execution:command:override-actor:v1 | P07.05.b → I-12.2 |
| `src/skm/schemas/execution/commands/reroute-task.v1.json` | urn:skm:execution:command:reroute-task:v1 | P07.05.b → I-12.2 |
| `src/skm/schemas/execution/commands/steer-task.v1.json` | urn:skm:execution:command:steer-task:v1 | P07.05.b → I-12.2 |
| `src/skm/schemas/execution/queries/get-task-live-control.v1.json` | urn:skm:execution:query:get-task-live-control:v1 | P07.05.b → I-12.2 |
| `src/skm/schemas/execution/results/live-control.v1.json` | urn:skm:execution:result:live-control:v1 | P07.05.b → I-12.2 |
| `src/skm/schemas/execution/views/task-live-control-view.v1.json` | urn:skm:execution:view:task-live-control-view:v1 | P07.05.b → I-12.2 |
