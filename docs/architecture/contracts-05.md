# Contract inventory, part 5

| Признак | Control plane (bus handlers, подписчики) | Host operations |
|---|---|---|
| `src/skm/schemas/workspace/remote-normalization-vectors.v1.json` | urn:skm:workspace:remote-normalization-vectors:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/results/add-repository-remote.v1.json` | urn:skm:workspace:result:add-repository-remote:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/results/archive-project.v1.json` | urn:skm:workspace:result:archive-project:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/results/archive-workspace.v1.json` | urn:skm:workspace:result:archive-workspace:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/results/attach-repository.v1.json` | urn:skm:workspace:result:attach-repository:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/results/bind-checkout.v1.json` | urn:skm:workspace:result:bind-checkout:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/results/create-project.v1.json` | urn:skm:workspace:result:create-project:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/results/create-workspace.v1.json` | urn:skm:workspace:result:create-workspace:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/results/detach-repository.v1.json` | urn:skm:workspace:result:detach-repository:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/results/record-checkout-verification.v1.json` | urn:skm:workspace:result:record-checkout-verification:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/results/record-worker-heartbeat.v1.json` | urn:skm:workspace:result:record-worker-heartbeat:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/results/register-host.v1.json` | urn:skm:workspace:result:register-host:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/results/register-repository.v1.json` | urn:skm:workspace:result:register-repository:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/results/register-worker.v1.json` | urn:skm:workspace:result:register-worker:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/results/exchange-pairing-token.v1.json` | urn:skm:workspace:result:exchange-pairing-token:v1 | P00.04.b → I-10.1a |
| `src/skm/schemas/workspace/results/set-worker-state.v1.json` | urn:skm:workspace:result:set-worker-state:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/views/attach-decision.v1.json` | urn:skm:workspace:view:attach-decision:v1 | P00.04.b → P04.04.a → P04.06 |
| `src/skm/schemas/workspace/views/checkout-binding.v1.json` | urn:skm:workspace:view:checkout-binding:v1 | P00.04.b → P04.04.a → P04.06 |
| `src/skm/schemas/workspace/views/checkout-location.v1.json` | urn:skm:workspace:view:checkout-location:v1 | P00.04.b → P04.04.a → P04.06 |
| `src/skm/schemas/workspace/views/host.v1.json` | urn:skm:workspace:view:host:v1 | P00.04.b → P04.04.a → P04.06 |
| `src/skm/schemas/workspace/views/list-hosts.v1.json` | urn:skm:workspace:view:list-hosts:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/views/list-project-repositories.v1.json` | urn:skm:workspace:view:list-project-repositories:v1 | P04.04.a |
| `src/skm/schemas/workspace/views/list-projects.v1.json` | urn:skm:workspace:view:list-projects:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/views/list-repositories.v1.json` | urn:skm:workspace:view:list-repositories:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/views/list-workers.v1.json` | urn:skm:workspace:view:list-workers:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/views/list-workspaces.v1.json` | urn:skm:workspace:view:list-workspaces:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/views/mount.v1.json` | urn:skm:workspace:view:mount:v1 | P00.04.b → P04.04.a → P04.06 |
| `src/skm/schemas/workspace/views/project-repositories.v1.json` | urn:skm:workspace:view:project-repositories:v1 | P00.04.b → P04.04.a → P04.06 |
| `src/skm/schemas/workspace/views/project-summary.v1.json` | urn:skm:workspace:view:project-summary:v1 | P00.04.b → P04.04.a → P04.06 |
| `src/skm/schemas/workspace/views/project.v1.json` | urn:skm:workspace:view:project:v1 | P00.04.b → P04.04.a → P04.06 |
| `src/skm/schemas/workspace/views/repository.v1.json` | urn:skm:workspace:view:repository:v1 | P00.04.b → P04.04.a → P04.06 |
| `src/skm/schemas/workspace/views/worker.v1.json` | urn:skm:workspace:view:worker:v1 | P00.04.b → P04.04.a → P04.06 |
| `src/skm/schemas/workspace/views/workspace-summary.v1.json` | urn:skm:workspace:view:workspace-summary:v1 | P00.04.b → P04.04.a → P04.06 |
| `src/skm/schemas/workspace/views/workspace.v1.json` | urn:skm:workspace:view:workspace:v1 | P00.04.b → P04.04.a → P04.06 |
| `src/skm/schemas/workspace/worker-capabilities.v1.json` | urn:skm:workspace:worker-capabilities:v1 | P00.04.b → P04.04.a |
| `resources/README.md` | resource slot | P00.04.f → P09.02.a |
| `resources/overlays/README.md` | resource slot | P00.04.f → P09.03 → P09.06 |
| `resources/packs/core/README.md` | resource slot | P00.04.f → P09.02.a |
| `resources/packs/core/agent-profiles/README.md` | resource slot | P00.04.f → P09.02.a → P09.02.b |
| `resources/packs/core/agent-profiles/advisor.toml` | builtin core agent profile (`advisor`) | P09.02.a |
| `resources/packs/core/agent-profiles/executor-transparent.toml` | builtin core agent profile (`executor-transparent`) | P09.02.a |
| `resources/packs/core/agent-profiles/executor.toml` | builtin core agent profile (`executor`) | P09.02.a |
| `resources/packs/core/agent-profiles/registrar.toml` | builtin core agent profile (`registrar`) | P09.02.a |
| `resources/packs/core/agent-profiles/researcher.toml` | builtin core agent profile (`researcher`) | P09.02.a |
| `resources/packs/core/agent-profiles/reviewer.toml` | builtin core agent profile (`reviewer`) | P09.02.a |
| `resources/packs/core/agent-profiles/scout.toml` | builtin core agent profile (`scout`) | P09.02.a |
| `resources/packs/core/agent-profiles/triager.toml` | builtin core agent profile (`triager`) | P09.02.a |
| `resources/packs/core/pack.toml` | builtin core pack manifest (`core`) | P09.02.a |
| `resources/packs/core/plan-templates/README.md` | resource slot | P00.04.f → P09.02.b → P09.08 |
| `resources/packs/core/prompts/README.md` | resource slot | P00.04.f → P09.02.a → P09.02.b |
| `resources/packs/core/prompts/advisor/result_contract.md` | builtin core prompt block (`advisor/result_contract`) | P09.02.a |
| `resources/packs/core/prompts/advisor/role.md` | builtin core prompt block (`advisor/role`) | P09.02.a |
| `resources/packs/core/prompts/executor/result_contract.md` | builtin core prompt block (`executor/result_contract`) | P09.02.a |
| `resources/packs/core/prompts/executor/role.md` | builtin core prompt block (`executor/role`) | P09.02.a |
| `resources/packs/core/prompts/executor/task_contract.md` | builtin core prompt block (`executor/task_contract`) | P09.02.a |
| `resources/packs/core/prompts/registrar/result_contract.md` | builtin core prompt block (`registrar/result_contract`) | P09.02.a |
| `resources/packs/core/prompts/registrar/role.md` | builtin core prompt block (`registrar/role`) | P09.02.a |
| `resources/packs/core/prompts/researcher/result_contract.md` | builtin core prompt block (`researcher/result_contract`) | P09.02.a |
| `resources/packs/core/prompts/researcher/role.md` | builtin core prompt block (`researcher/role`) | P09.02.a |
| `resources/packs/core/prompts/reviewer/result_contract.md` | builtin core prompt block (`reviewer/result_contract`) | P09.02.a |
| `resources/packs/core/prompts/reviewer/role.md` | builtin core prompt block (`reviewer/role`) | P09.02.a |
| `resources/packs/core/prompts/scout/result_contract.md` | builtin core prompt block (`scout/result_contract`) | P09.02.a |
| `resources/packs/core/prompts/scout/role.md` | builtin core prompt block (`scout/role`) | P09.02.a |
| `resources/packs/core/prompts/shared/block_wrapper.md` | builtin core prompt block (`shared/block_wrapper`) | P09.02.a |
| `resources/packs/core/prompts/shared/raw_block.md` | builtin core prompt block (`shared/raw_block`) | P09.02.a |
| `resources/packs/core/prompts/shared/resume_note.md` | builtin core prompt block (`shared/resume_note`) | P09.02.a |
| `resources/packs/core/prompts/shared/run_rules.md` | builtin core prompt block (`shared/run_rules`) | P09.02.a |
| `resources/packs/core/prompts/shared/system_constraints.md` | builtin core prompt block (`shared/system_constraints`) | P09.02.a |
| `resources/packs/core/prompts/shared/task_contract.md` | builtin core prompt block (`shared/task_contract`) | P09.02.a |
| `resources/packs/core/prompts/shared/work_policy.md` | builtin core prompt block (`shared/work_policy`) | P09.02.a |
| `resources/packs/core/prompts/triager/result_contract.md` | builtin core prompt block (`triager/result_contract`) | P09.02.a |
| `resources/packs/core/prompts/triager/role.md` | builtin core prompt block (`triager/role`) | P09.02.a |
| `resources/packs/core/runtimes/README.md` | resource slot | P00.04.f → P09.02.a |
| `resources/packs/core/runtimes/models.toml` | builtin core runtime model catalog (`models`) | P09.02.a |
| `resources/packs/core/model-guidelines/claude-opus-5-5.toml` | builtin core model guideline (`claude-opus-5-5`) | P09.04 (I-06.1) |
| `resources/packs/core/model-guidelines/claude-sonnet-5-5.toml` | builtin core model guideline (`claude-sonnet-5-5`) | P09.04 (I-06.1) |
| `resources/packs/core/model-guidelines/gemini-3-8-flash.toml` | builtin core model guideline (`gemini-3-8-flash`) | P09.04 (I-06.1) |
| `resources/packs/core/model-guidelines/gemini-4-argon.toml` | builtin core model guideline (`gemini-4-argon`) | P09.04 (I-06.1) |
| `resources/packs/core/model-guidelines/gemini-4-carbon.toml` | builtin core model guideline (`gemini-4-carbon`) | P09.04 (I-06.1) |
| `resources/packs/core/model-guidelines/gemini-4-hydrogen.toml` | builtin core model guideline (`gemini-4-hydrogen`) | P09.04 (I-06.1) |
| `resources/packs/core/model-guidelines/gemini-4-neon.toml` | builtin core model guideline (`gemini-4-neon`) | P09.04 (I-06.1) |
| `resources/packs/core/model-guidelines/gpt-6-astra.toml` | builtin core model guideline (`gpt-6-astra`) | P09.04 (I-06.1) |
| `resources/packs/core/model-guidelines/gpt-6-luna.toml` | builtin core model guideline (`gpt-6-luna`) | P09.04 (I-06.1) |
| `resources/packs/core/model-guidelines/gpt-6-sol.toml` | builtin core model guideline (`gpt-6-sol`) | P09.04 (I-06.1) |
| `resources/packs/core/model-guidelines/gpt-oss-120b.toml` | builtin core model guideline (`gpt-oss-120b`) | P09.04 (I-06.1) |
| `resources/packs/core/model-guidelines/grok-4-7.toml` | builtin core model guideline (`grok-4-7`) | P09.04 (I-06.1) |
| `src/skm/schemas/runtimes/model-guideline.v1.json` | model guideline profile contract | P09.04 (I-06.1) |
| `resources/packs/core/skills/README.md` | resource slot | P00.04.f → P09.02.b |
| `resources/packs/core/steering/README.md` | resource slot | P00.04.f → P09.02.b |
| `resources/packs/core/workflows/README.md` | resource slot | P00.04.f → P09.02.a → P09.02.b |
| `resources/packs/core/workflows/quick-fix.toml` | builtin core workflow (`quick-fix`) | P09.02.a |
| `resources/packs/core/workflows/research-only.toml` | builtin core workflow (`research-only`) | P09.02.a |
| `resources/packs/core/workflows/reviewed-development.toml` | builtin core workflow (`reviewed-development`) | P09.02.a |
| `docs/architecture/contracts.md` | contract inventory | P00.04.a → P00.04.b → P00.04.c → P00.04.d → P00.04.e → P00.04.f → P00.06 |
| `tests/architecture/test_contract_imports.py` | import, DAG, boundary and offline schema smoke | P00.04.f |
| `tests/architecture/test_cli_thin.py` | facade-only CLI imports, negative examples and static reference generation/closure | P02.08.b (bounded partial) |
| `tests/architecture/test_settings_declared.py` | declared settings keys/views, positive and negative examples | P02.08.b (bounded partial) |
| `tests/unit/entrypoints/cli/test_config.py` | config commands through explicit test composition; scope, CAS, import/export, permissions (target-scope schema read) and safe output | P02.08.b (bounded partial) |
| `docs/reference/config.md` | schema and CLI configuration reference generated by tools/gen.py | P01.05.a → P02.08.b (bounded partial) |
| `docs/reference/cli.md` | CLI declarations reference generated by tools/codegen/cli_reference.py through tools/gen.py | P02.08.b (bounded partial) |
| Контекст | `CommandContext`, `QueryContext`, `SubscriberContext` (`application_bus/context.py`) | `HostContext` (`application_bus/host.py`) |
| Шлюзы | `GatewayTable(kind="control_plane_gateway")` | `GatewayTable(kind="host_gateway")` |
| Маркер порта | `@control_plane_gateway`, `@shared_gateway` | `@host_gateway`, `@shared_gateway` |
| Состояние | `uow.repo(Port)`, фасады по `depends_on` | только `ctx.client.dispatch/ask/upload_blob/open_file_version_content` |
| Регистрация | `CommandSpec`/`QuerySpec`/`SubscriberSpec`/`ExternalConsumerSpec` в манифесте | `HostOperationSpec` в `ModuleManifest.host_operations` |
| Сигнатура | `handle(dto, ctx, uow) -> Result` | `run(ctx: HostContext, request) -> Result` |

Маркеры ставят атрибут `__skm_port_kind__` (`kernel.ports_uow.PORT_KIND_ATTRIBUTE`, тип `PortKind`).
`GatewayTable.get` (P01.09.a) принимает только порт с маркером своего `kind` или `shared_gateway`, иначе
`TypeError`; отсутствующий порт — `CapabilityUnavailable(CAPABILITY_UNAVAILABLE)`.

### P07.05.a: bounded generated execution partitions

| Materialized file | Contracts | Declaration → implementation/refinement leaves |
|---|---|---|
| `src/skm/modules/execution/generated/_events_acceptance_decided.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_events_assignment_leased.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_events_attempt_ownership_lost.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_events_attempt_started.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_events_autopilot_state_changed.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_events_budget_exhausted.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_events_check_completed.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_events_decision_answered.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_events_decision_requested.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_events_deviation_accepted.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_events_execution_history.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_events_external_effect_outcome_unknown.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_events_external_effect_recorded.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_events_followups_created.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_events_integration_completed.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_events_lease_expired.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_events_manual_verdict_recorded.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_events_monitor_evaluated.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_events_output_sealed.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_events_readiness_reported.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_events_recovery_circuit_opened.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_events_review_completed.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_events_review_requested.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_events_run_cancelled.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_events_run_created.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_events_run_finished.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_events_run_paused.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_events_run_reconfigured.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_events_run_resumed.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_events_run_started.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_events_run_waiting.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_events_runtime_observation.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_events_runtime_start_admitted.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_events_stage_completed.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_events_stage_recovered.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_events_stage_started.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_events_step_observation_recorded.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_events_task_accepted.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_events_task_assigned.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_events_task_created.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_events_task_failed.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_events_task_ready.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_events_task_rework_required.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_events_task_skipped.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_events_task_wait_changed.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_views_defs.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_views_explain_autopilot.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_views_get_attempt.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_views_get_autopilot_status.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_views_get_fix_brief.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_views_get_readiness_report.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_views_get_review_receipt.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_views_get_run.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_views_get_run_budget.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_views_get_run_health.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_views_get_run_history.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_views_get_run_timeline.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_views_get_step.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_views_get_task.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_views_list_decision_requests.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_views_list_execution_environments.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_views_list_runs.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_views_list_task_attempts.py` | generator-owned execution contract partition | P07.05.a |
| `src/skm/modules/execution/generated/_views_list_tasks.py` | generator-owned execution contract partition | P07.05.a |

## 4. Kernel (P00.04.a — чистые декларации, K20)

Kernel импортирует только stdlib и kernel; ни runtime-, ни `TYPE_CHECKING`-импортов `modules`,
`application_bus`, `bootstrap`, `platform` нет. Функции с логикой — только маркеры портов.

| Файл | Объявлено P00.04.a | Логику добавляет |
|---|---|---|
| `json_types.py` | `JsonScalar`, `JsonValue`, `JsonObject` | — |
| `ids.py` | 18 NewType ID, `UUID7_MAX_RAND_A/B` | `uuid7`, `uuid7_timestamp_ms`, `parse_uuid` — P01.01 |
| `versions.py` | `RowVersion`, `SchemaVersion`, `RevisionNo`, `StreamSeq`, `ExpectedVersion` | проверка `value >= 1` — P01.01; `check_expected` — P01.02 |
| `actor.py` | `PrincipalKind`, `TokenGrant`, `Actor`, `SYSTEM_PRINCIPAL_ID` | — |
| `events.py` | `STREAM_KINDS`, `DomainEvent` (ABC), `EventEnvelope` | `to_json`/`from_json`, валидация envelope — P01.07 |
| `clock.py`, `id_generator.py`, `entropy.py` | `Clock`, `Monotonic`, `IdGenerator`, `EntropySource` | реализации `platform/system_{clock,ids,entropy}.py` — P01.02 |
| `tokens.py` | `@control_plane_gateway TokenEstimator` | `platform/tokens/heuristic.py` (`heuristic-v1`) — P09.04.a |
| `scopes.py` | `ScopeKind`, `ALLOWED_PARENTS`, `ScopeRef`, `ScopeRecord`, `@repository_port ScopeRegistry` | адаптеры `adapters/{memory,postgres}/core/scopes.py` — P01.08.b, P03.02 |
| `ports_uow.py` | `Surface`, `Isolation`, `RequestMeta`, `OutboxEnqueuer`, `UnitOfWork`, `UnitOfWorkFactory`, `PORT_KIND_ATTRIBUTE`, `PortKind`, маркер `repository_port` | UoW memory — P01.08.b, PostgreSQL — P03.03.a |
| `gateways.py` | `Gateways`, `GatewayTable` (`entries`, `kind`), `GatewayTableKind`, маркеры `control_plane_gateway`, `host_gateway`, `shared_gateway` | `GatewayTable.get/has` — P01.09.a (до этого `NotImplementedError`) |
| `cancel.py` | `CancelToken`, `Cancelled` | `CancelSource`, конструктор `Cancelled` — P01.06.c |
| `module_manifest.py` | `ModuleManifest` (все поля §2.12), `HostOperationSpec` | — |

`ModuleManifest.commands/queries/subscribers/external_consumers/doctor_checks` типизированы `tuple[object, ...]`:
kernel не зависит от `application_bus`/`bootstrap`, типы элементов проверяют `BusRegistry.build` (P01.08.a) и
`DoctorCheckRegistry` (P00.04.f, P01.09.a). Не в P00.04.a: `errors.py`, `error_codes.py`, `outcomes.py`,
`generated/` (P01.02, P01.05.a), `pagination.py`, `isolation.py` (P01.01).

## 5. application_bus (P00.04.a)

| Файл | Объявлено P00.04.a | Реализацию добавляет |
|---|---|---|
| `context.py` | `CommandContext`, `QueryContext`, `SubscriberContext`, `ExternalConsumerContext` | сборка контекстов — `bus.py` P01.08.a, relay P03.05.b |
| `registry.py` | `IdempotencyMode`, `CommandSpec[C, R]`, `QuerySpec[Q, R]`, `SubscriberSpec`, `ExternalConsumerSpec` | `BusRegistry` — P01.08.a |
| `ports.py` | `Authorizer`, `AuthzDecision`, `ScopeChainResolver`, `IdempotencyReceipt`, `IdempotencyStore`, `AuditRecord`, `AuditLog`, `EventReader`, `OutboxState`, `OutboxItem`, `OutboxEntry`, `OutboxStore`, `ConsumerReceipts`, `DeliveryPlan`, `Sent`, `RetryAt`, `GiveUp`, `SendResult`, `ExternalConsumer` | адаптеры core — P01.08.b, P03.02, P03.03.a/b, P03.05, P03.05.b |
| `client.py` | `SkmClient`, `QueryMeta`, `StagedBlobRef` | `EmbeddedClient` — P01.08.a, P06.03.c; `HttpSkmClient` — P11.04 |
| `host.py` | `HostContext` | `HostServices` — P01.09.a; `bootstrap/host_services.py` — P01.09.a |

Не в P00.04.a: `middleware.py`, `bus.py` (`Bus`, `request_digest`) — P01.08.a/b; `subscribers.py` (`deliver`) — P03.05.
Неисполненные handlers нигде не регистрируются, фиктивных успешных результатов нет.

Размещение, уточнённое этим каталогом (владелец файлов — kernel-platform):

- `ExternalConsumer` объявлен в `application_bus/ports.py`;
  старый комментарий о размещении называет `subscribers.py`. Вместе с ним в `ports.py` лежат типы его
  сигнатуры `DeliveryPlan`, `Sent`, `RetryAt`, `GiveUp`, `SendResult` (§4.1): `registry.py` импортирует их из
  `ports.py`, обратной зависимости нет.
- `QueryMeta` (kernel-platform §4.4, блок `bus.py`) объявлен в `client.py`: он нужен `SkmClient.ask_with_meta`,
  а `bus.py` появляется в P01.08.a и импортирует `QueryMeta` оттуда.
- Core-порты, которые читаются через `uow.repo()` (`ScopeRegistry`, `IdempotencyStore`, `AuditLog`,
  `EventReader`, `OutboxStore`, `ConsumerReceipts`; `CORE_PORTS` kernel-platform §5.2), помечены
  `@repository_port`; `Authorizer` и `ScopeChainResolver` — объекты bus, без маркера.

## 6. Отложенные типы

Поля, тип которых объявляет ещё не созданный владелец, временно типизированы `object`. Следующий владелец
файла сужает тип до нормативного после появления декларации; новых контрактов здесь не вводится.

| Где | Сейчас | Нормативный тип | Декларация (leaf) | Сужает (leaf) |
|---|---|---|---|---|
| `CommandContext/QueryContext/SubscriberContext.config`, `SubscriberContext.config_for` → | `object` | `EffectiveConfig` (`platform/config/effective.py`) | P00.04.b | P01.08.a |
| `CommandContext/QueryContext/SubscriberContext/ExternalConsumerContext.log` | `object` | `StructLogger` (`platform/logging/logger.py`) | P00.04.b | P01.08.a |
| `ExternalConsumerContext.secrets` | `object` | `SecretResolver` (`platform/config/secrets.py`) | P00.04.b | P03.05.b |
| `HostContext.config`, `HostContext.log` | `object` | `EffectiveConfig`, `StructLogger` | P00.04.b | P01.09.a |
| `ModuleManifest.commands/queries/subscribers/external_consumers` | `tuple[object, ...]` | `CommandSpec`/`QuerySpec`/`SubscriberSpec`/`ExternalConsumerSpec` | P00.04.a | остаётся (kernel ↛ application_bus) |
| `ModuleManifest.doctor_checks` | `tuple[object, ...]` | `DoctorCheckSpec` (`bootstrap/doctor.py`) | P00.04.f | остаётся (kernel ↛ bootstrap) |
| `SkmClient.dispatch/ask` | `object` | generated DTO команды/запроса | P01.05.a | остаётся (протокол общий для всех DTO) |

## 7. Порты

Колонки: вид (`repo` — `@repository_port`, `cp` — control-plane gateway, `host` — host gateway, `shared` —
`@shared_gateway`, `bus` — объект конвейера, `kernel` — сервис ядра, `narrow` — узкий контракт без таблицы
шлюзов); потребители; реализация. Декларацию делает leaf группы модуля (§2), реализации — leaf из §2 и
указанные ниже. Репозиторные порты модуля потребляют только его handlers, подписчики и `public.py`;
адаптеры — `adapters/{memory,postgres}/<module>/` ([`src/skm/adapters/`](../../src/skm/adapters/)).

### 7.1 kernel и application_bus (P00.04.a)

| Порт | Вид | Владелец | Потребители | Реализация (leaf) |
|---|---|---|---|---|
| `Clock`, `Monotonic` | kernel | `kernel/clock.py` | контексты, адаптеры, службы | `platform/system_clock.py` (P01.02) |
| `IdGenerator` | kernel | `kernel/id_generator.py` | контексты, UoW, клиенты | `platform/system_ids.py: Uuid7Generator` (P01.02) |
| `EntropySource` | kernel | `kernel/entropy.py` | `CommandContext.entropy`, `Uuid7Generator`, генераторы секретов | `platform/system_entropy.py` (P01.02) |
| `TokenEstimator` | cp | `kernel/tokens.py` | context (`assemble_draft`; host `finalize` получает аргументом) | `platform/tokens/heuristic.py` (P09.04.a), плагины `token_estimator` |
| `ScopeRegistry` | repo | `kernel/scopes.py` | workspace/planning/execution handlers (создание scope), `ScopeChain` | `adapters/{memory,postgres}/core/scopes.py` (P01.08.b, P03.02) |
| `UnitOfWork`, `UnitOfWorkFactory`, `OutboxEnqueuer` | kernel | `kernel/ports_uow.py` | bus, relay, handlers, подписчики | memory UoW (P01.08.b), PostgreSQL UoW (P03.03.a) |
| `Gateways` | kernel | `kernel/gateways.py` | `CommandContext`, `QueryContext`, `SubscriberContext`, `HostContext` | `GatewayTable` (P01.09.a), сборка в `bootstrap/composition.py`, `host_services.py` |
| `CancelToken` | kernel | `kernel/cancel.py` | host operations, `ExternalConsumer.send`, службы | `CancelSource` (P01.06.c) |
| `Authorizer` | bus | `application_bus/ports.py` | шаг `authorize` bus | `access.public.RbacAuthorizer` (P04.02.c) |
| `ScopeChainResolver` | bus | `application_bus/ports.py` | шаг `resolve_scope` bus | `workspace.public.ScopeChain` (P04.04.a) |
| `DoctorRunner` | cp | `application_bus/ports.py` | `platform.doctor` (`ctx.gateways`) | `bootstrap/composition.py: _DoctorRunner` over the reports of `bootstrap/doctor.py: DoctorCheckCollector` (kernel-platform §5.2a, §5.6) with the provisional `ServingProcessObserver` beneath it (P02.08.b) |
| `CurrentProcessObserver` | narrow | `application_bus/ports.py` | `DoctorRunner.observe` (no gateway marker of its own) | `_DoctorRunner.observe` (P02.08.b) |
| `IdempotencyStore` | repo | `application_bus/ports.py` | шаги `idempotency`/`receipt`, janitor `idempotency_gc` | `adapters/memory/core` (P01.08.b), `adapters/postgres/core/idempotency.py` (P03.02, P03.03.b) |
| `AuditLog` | repo | `application_bus/ports.py` | шаг `audit`, denied audit | `adapters/postgres/core/audit.py` (P03.02, P03.03.b), memory (P01.08.b) |
| `EventReader` | repo | `application_bus/ports.py` | SSE, `EmbeddedClient.events`, relay, `ask` (`events_cursor`) | `adapters/postgres/core/events_store.py` (P03.02, P03.03.a), memory (P01.08.b) |
| `OutboxStore` | repo | `application_bus/ports.py` | relay, janitor `outbox_gc`, `platform.list_dead_outbox/retry_outbox`, `integrations.list_hook_deliveries` (только префикс `hook:`) | `adapters/{memory,postgres}/core/outbox.py` (P01.08.b, P03.02, P03.05, P03.05.b) |
| `ConsumerReceipts` | repo | `application_bus/ports.py` | relay (дедупликация), janitor | `adapters/memory/core/audit.py` (P01.08.b), `adapters/postgres/core/consumer_receipts.py` (P03.05, P03.05.b) |
| `ExternalConsumer` | narrow | `application_bus/ports.py` | relay (`ExternalConsumerSpec.factory`) | `modules/integrations/application/hook_delivery.py: HookDeliveryConsumer`, префикс `hook` (P10.01.b, P10.08.b) |
| `SkmClient` | narrow | `application_bus/client.py` | host operations (`ctx.client`), CLI, MCP, worker | `EmbeddedClient` (P01.08.a, P06.03.c), `HttpSkmClient` (P11.04) |
| `BackgroundService` | narrow | `background/service_runner.py` | `ServiceRunner` | службы §4.16 conventions (P01.09.b и далее) |

`ScopeRegistry.list_scopes(*, after: ScopeId | None = None, limit: int = 100) -> tuple[ScopeRecord, ...]`
is an internal inventory for the authorized `platform.Doctor` handler. It reads the current UoW snapshot,
including all six scope kinds, scopes without configuration, and retained scope rows independently of
entity lifecycle. Results are ordered by ascending UUID; `after` is an exclusive boundary and need not
name an existing row. Empty and exhausted inventories return `()`. Limits use the kernel bounds 1..500
(default 100); invalid argument types raise `TypeError`, and limits outside the bounds raise `ValueError`.
This inventory has memory (`adapters/memory/core/scopes.py`) and PostgreSQL (`adapters/postgres/core/scopes.py`) implementations.
It adds no client or bus endpoint. The doctor handler must authorize access before consuming it; restart
coverage is limited to the serving process, with an explicit unknown result when no snapshot exists.

`platform.doctor` (P02.08.b, `application_bus/platform/doctor.py`) is the public query over the existing
`urn:skm:platform:query:doctor:v1` → `urn:skm:platform:result:doctor:v1` DTOs; no schema or generated code
changed. Permission `config.read`, `scope_of=None` (instance), REPEATABLE_READ: the bus authorizes at instance
in the read-only UoW before the handler, so a denied actor causes no inventory or configuration read. The
handler then reads `ScopeRegistry.list_scopes` pages of 500 until an empty page (non-ascending or oversized
pages fail closed with `INTERNAL_ERROR`) and calls `diagnose_config` with `ctx.config.registry` and the
`ConfigStore`/`ScopeTree`/`PackConfigSource` of the same UoW; it opens no UoW and does no host IO. Its only
gateway is `DoctorRunner` (`PLATFORM_MANIFEST.gateway_ports=(DoctorRunner,)`), which serves recorded reports
and executes nothing (kernel-platform §5.2a: bus handlers do not execute registered checks; host IO stays in
bootstrap/host doctor). The `DoctorCheckSpec`s of the enabled manifests and the platform run only in
`App.doctor.collect(redactor=..., only=None)` (`DoctorCheckCollector`): host-side, outside every unit of work
(inside one of the composition's memory UoWs it raises `RuntimeError` and runs nothing), with a
bootstrap-built opaque `DoctorContext` and no UoW or ports passed. Collection buffers each check atomically
(`DoctorCheckRegistry.reports`): a raise, a finding of the wrong runtime type (non-string or empty id,
non-string title/detail, hint other than string/null, target other than `TargetId`, path other than
string/path/null, unknown level) makes that check `failed` without findings and leaves its siblings intact.
Every string of every finding then passes the caller's process `Redactor` (registered revealed secrets and
the default token patterns) with the §5.2a field mapping kept; each check's owner remains responsible for
building findings from facts, identifiers and paths only (integrations §5.6), the redactor is the enforced
second layer, not a sandbox. The recorded `RegisteredCheckReport(check_id, state, findings)` keeps the
registration id as provenance; a later collection replaces that check's report. Until the host doctor leaf
calls `collect`, a registered check has no report and the query answers `warn` (`reason=not_collected`), never
`ok`; a recorded report reflects its collection, not the request. Registered ids may not reuse `CHECK_IDS`
(`build_app` answers `CONFIG_INVALID`, `reserved_check_id`), and neither may their findings: a report whose
findings use an id of `CHECK_IDS` or of another registered check is impersonation and yields one `warn` under
its registration id (`reason=reserved_check_id`), none of its findings. Other finding ids, the check's own or
a free one, are returned: a selector names the registration id and selects all findings of that report. A
`failed` report, an unknown state or a finding of the wrong runtime shape (re-checked in the handler) yields
one `warn` under the registration id (`reason=check_failed`); a gateway that raises or returns anything but a
tuple of `RegisteredCheckReport` with distinct, selected ids yields one `warn` per selected id
(`reason=runner_failed`); no error text is projected. An absent gateway, a catalog that raises, or one that is
not a set of non-empty strings outside `CHECK_IDS` is unknown registered coverage, never an empty catalog: one
`warn` `doctor.registered_checks` (`REGISTERED_CHECKS`, `state=unknown`,
`reason=runner_unavailable|catalog_failed|catalog_invalid`) for an omitted selection, for that id, or for a
selector outside `CHECK_IDS`, which then is not refused because it is not provably unknown; with a readable
catalog that id has no findings. The engine's `config.restart_pending` placeholder is
replaced by `DoctorRunner.observe`, the observation of the current process (instance work chain and the
captured host chain only, rooted at a host or at the process's own instance). Any state but `observed`, an
absent gateway, an observer exception, an observation for another instance, a malformed observation (state,
identity, generation, host target or pending collection/items of the wrong type), or a pending key outside
those two chains yields one `warn` check with `state=unknown` and a closed `reason`
(`snapshot_missing|uncommitted|instance_mismatch|observer_unavailable|observation_failed|observation_invalid`);
metadata is projected only after its type is checked. An observed process yields `ok` or one check per
pending key (`code=CONFIG_RESTART_PENDING`, `chain`, `key`, `severity`) whose status maps the provider's
diagnostic severity by kernel-platform §5.2a (settings §B.7 `info` → `ok`; `warning` → `warn`; `error` →
`fail`); the message and restart hint stay visible with `ok`, while unknown coverage stays `warn`.
Restart details are deterministic JSON of identifiers (`coverage=current_process`, instance, host, process
generation); values and exception texts are never projected. `only` selects exact ids from `CHECK_IDS` and
the registered ids after authorization: omitted selects every check, an empty list (schema-valid) selects
none and returns `checks=[]`, duplicates select once, a known id without findings returns no check, and an
unknown id answers `SCHEMA_INVALID` (`details.reason=unknown_check_id`, the rejected text is not echoed)
while the registered catalog is readable. A selected registered check returns all findings of its recorded
report. The composition's Postgres guard of `DoctorCheckCollector.collect` is `_OpenUnits.holds` (a per-thread depth entered and left by
`_TrackedUow.__enter__/__exit__`, counted only after the unit of work opened and released even when its exit raises); the memory
guard is `_in_unit_of_work`. `skm config doctor` (CLI §5.3) is a thin consumer of this query and adds no handler, schema or
host IO. Selecting only `config.restart_pending` skips the inventory; selecting only configured checks skips
the observer and the registered reports. Coupling: only
`_DoctorRunner` in composition reads the provisional provider's fields (`state`, `instance_scope_id`,
`host_target`, `process_generation`, `pending[*].key/chain/target/severity`).

### 7.2 platform

| Порт | Вид | Владелец | Потребители | Реализация (leaf) |
|---|---|---|---|---|
| `SecretResolver` | cp | `platform/config/secrets.py` (P00.04.b) | `ConfigLoader`, `ExternalConsumerContext.secrets`, bootstrap | цепочка env/file/keyring (P02.05.b), плагины `secret_resolver` |
| `ConfigStore` | repo | `platform/config/store.py` (P00.04.b) | `ConfigLoader` (шаг `load_config`) | адаптеры settings (P02.06) |
| `ScopeTree` | repo | `platform/config/store.py` (P00.04.b) | `ConfigLoader` | `adapters/postgres/core/scopes.py: PostgresScopeTree` (P03.02), memory (P02.06) |
| `PackConfigSource` | narrow | `platform/config/store.py` (P00.04.b) | `ConfigLoader` (pack-уровень) | `adapters/postgres/extensions/pack_config_source.py` поверх `extensions.public.pack_config_fragments` (P09.03) |
| `MigrationSession` | narrow | `adapters/postgres/migrations/runner.py` | migration runner | соединение мигратора (P03.01.a) |
| `StreamParser` | narrow | [`adapters/runtimes/_cli_session/`](../../src/skm/adapters/runtimes/_cli_session/) (`stream_parser.py` отдельно от `stream.py` / `StreamTail`) | `CliSession` адаптеров runtime | P08.02.b; парсеры провайдеров — P08.03–P08.05 |

### 7.3 Порты модулей

| Порт | Вид | Владелец (`modules/<m>/ports.py`) | Потребители вне модуля | Реализация |
|---|---|---|---|---|
| `PrincipalRepository`, `IdentityRepository`, `TokenRepository`, `MembershipRepository` | repo | access | — (фасады access) | adapters memory/postgres access |
| `TokenPepperSource` | gateway (вид по owner spec §6) | access | — | секрет `token-pepper` в `state_dir` (P03.07) |
| `WorkerHostLookup` | repo | access | — | `adapters/{postgres,memory}/workspace/worker_hosts.py` (реализует workspace; направление workspace → access сохранено) |
| `ConfigEntryRepository`, `ConfigHistoryRepository`, `ConfigGenerationCounter` | repo | settings | — | adapters settings (P02.07.a) |
| `WorkspaceRepository`, `ProjectRepository`, `RepositoryRepository`, `MountRepository`, `HostRepository`, `CheckoutBindingRepository`, `WorkerRepository` | repo | workspace | — (фасады workspace) | adapters workspace (P04.04.a) |
| `RepositoryInspector` | host | workspace | host ops workspace | `adapters/git/repo_inspect.py: GitRepositoryInspector` (P04.06) |
| `ReviewCheckoutPathResolver` | host | execution | managed CLI review requests | `bootstrap/checkout_operations.py` (SKM 0.1.0 A02) |
| `StagedBlobRepository`, `BlobRepository`, `FileRepository`, `FileVersionRepository`, `AccessGrantRepository` | repo | artifacts | — (фасады artifacts) | adapters artifacts (P06.01.a, P06.03.a) |
| `BlobStore` | cp | artifacts | artifacts handlers, `EmbeddedClient.upload_blob/open_file_version_content`, janitor | `adapters/blobs/local/store.py` (P06.02), плагины `blob_backend` |
| `BlobCoordination` | cp | artifacts | upload coordinator (`EmbeddedClient`, API), consume/reference handlers, janitor/prune | `adapters/{postgres,memory}/artifacts/blob_coordination.py` (P06.03.a, P06.03.b, P06.03.c) |
| `MaterialWriter` | host | artifacts | host op `artifacts.host.materialize_files` | `adapters/blobs/local/materializer.py` (P06.05) |
| `ToolIntentRepository`, `ApprovalRepository`, `DecisionAuditRepository` | repo | policy | — (фасады policy) | adapters policy (P07.01.b) |
| `PathFacts` | narrow | policy | чистые ядра policy (hook, worker) | `adapters/git/path_facts.py: GitPathFacts`, domain `StaticPathFacts` |
| `PackRepository`, `ResourceRepository`, `QuarantineRepository` | repo | extensions | — (фасады extensions) | adapters extensions (P09.01.a) |
| `BuiltinPacks` | cp | extensions | `extensions.sync_builtin_packs` | `adapters/resources/builtin_packs.py` (P09.01.a) |
| `RuntimeCatalogSeeder` | cp | extensions | `extensions.sync_builtin_packs` | `runtimes.public.seed_builtin_model_catalog` via composition in the same UoW (I-05.1) |
| `PackReader`, `UpstreamFetcher` | host | extensions | host ops `extensions.host.install_pack/check_upstream` | `adapters/resources/pack_reader.py` (P09.01.b), `adapters/resources/upstream_http.py` (P09.01.c) |
| `HostRuntimeRepository`, `CapabilityVerificationRepository`, `ModelCatalogRepository`, `HostModelAvailabilityRepository` | repo | runtimes | — (фасады runtimes) | adapters runtimes (P08.01.a) |
| `AgentRuntime` | host | runtimes | execution host-стадии через `RuntimeRegistry` | `adapters/runtimes/<provider>/` (P08.03, P08.04, P08.05), плагины `runtime` |
| `RuntimeRegistry` | host | runtimes | execution host-стадии, host op `runtimes.host.detect_runtimes` | `bootstrap/runtimes.py: RUNTIME_FACTORIES` + плагины (P08.03–P08.05) |
| `WorkerModelOfferPolicy` | host | runtimes | host op `runtimes.host.detect_runtimes` | `bootstrap/worker_runtimes.py: WorkerRuntimes` (W02) |
| `CapabilityCatalog` | shared | runtimes | фасады runtimes (сервер), host-стадии | встроенные `capabilities.toml`/`error_rules.toml` ∪ `LoadedPlugin.runtime_data` (P08.01.a, P01.10) |
| `PlanRepository`, `PlanCounters`, `DraftRepository`, `RevisionRepository`, `PlanningQueries` | repo | planning | — (фасады planning) | adapters planning (P05.04.a) |
| `ContextRepository`, `TextStore`, `ResearchRepository` | repo | context | — (фасады context) | adapters context (P09.04.a, P09.09.a) |
| `ContextOwnerGuard` (+ запись `ContextOwnerClaim`) | cp | context | `context.finalize_manifest` | `adapters/execution/context_owner.py` → `execution.public.require_current_context_owner` в той же UoW (P09.04.d); context ↛ execution |
| `MemoryRetriever` | cp | context | `context.public.assemble_draft` | `adapters/knowledge/context_source.py` (P13.01.b) или `adapters/knowledge/null_retriever.py` (P09.05) |
| `LocalEpisodicMemory` | host | knowledge | Trusted embedded MCP and durable local consumption receipts | `adapters/knowledge/local_sqlite_memory.py` (I-09.4) |
| `CheckoutReader`, `ResearchSourceRegistry`, `ResearchSource` | host | context | host-функции context, host op `context.host.research_query` | `CheckoutReader` — adapter checkout FS по owner spec; источники `adapters/research/*` (P09.09.b), плагины `research_source` |
| `RunRepository`, `BundleRepository`, `ReadinessRepository`, `TaskRepository`, `AttemptRepository`, `StageRepository`, `StepRepository`, `AssignmentRepository`, `EnvironmentRepository`, `OutputRepository`, `CheckRepository`, `ReviewRepository`, `AcceptanceRepository`, `BudgetRepository`, `DecisionRepository`, `EffectRepository`, `IntegrationSlotRepository`, `ReviewRequestRepository`, `AutopilotRepository`, `RecoveryRepository`, `EvidenceBindingRepository`, `ExecutionQueries` | repo | execution | — (фасады execution) | adapters execution (P07.05.a и далее) |
| `ExecutionEnvironmentManager`, `Vcs`, `CheckRunner`, `Isolation` | host | execution | host-стадии execution через `StageDeps` | `adapters/git/*` (P07.07.a, P07.08.a), `adapters/checks/registry.py` (P07.07.a), `adapters/sandbox/registry.py` (P08.07.a) |
| `StageHandler`, `StageClient` (+ `StageDeps`, `StageRequest`, `StageOutcome`) | narrow | execution | worker loop, control-plane стадии | встроенные стадии, плагины `stage_handler` (P07/P08) |
| `ProjectionRepository` | repo | integrations | — | adapters integrations (P10.01.b) |
| `IntegrationTarget`, `IntegrationTargetRegistry`, `CheckoutFs`, `UserHomeReader`, `HostCommandRunner` | host | integrations | host ops integrations; `CheckoutFs` — также context/execution через их host-код по owner spec | `adapters/integrations/registry.py` (P10.02–P10.04.b), `adapters/checkout_fs/local.py` (P10.01.c), `adapters/checkout_fs/user_home.py` (P10.07), `adapters/host_commands/subprocess_runner.py` (P10.08.b) |
| `CheckoutGitExcludes`, `ProjectionConfig` | host | integrations | `integrations.host.sync_projections`, `integrations.host.untrack_service_files` | `adapters/git/excludes.py`, `bootstrap/projection_wiring.py` (I-09.1) |
| `MemoryRepository`, `LessonRepository`, `GraphRepository` | repo | knowledge | — (фасады knowledge) | adapters knowledge (P13.01.b) |
| `ActivityRecordRepository`, `CandidateRepository`, `SignalRepository`, `CandidateReviewRepository`, `CandidateProposalRepository` | repo | learning | — | adapters learning (P13.03.b) |
| `VaultNoteRepository` | repo | exports | — | adapters exports (P13.04.a) |
| `VaultFs` | host | exports | host ops exports | `adapters/exports/obsidian/vault_fs.py: LocalVaultFs` (P13.04.b) |

Точный набор методов каждого Protocol — объявление в `ports.py` владельца;
группы P00.04.b–e переносят их с маркерами и отмечают здесь расхождения.

`skm runtime sync` напрямую запускает `runtimes.public.ModelCatalogSyncJob`,
передавая `HttpsCatalogTransport` и карту провайдеров из `bootstrap/catalog_transport.py`.
`CatalogTransport` задаёт интерфейс загрузки для этой зависимости. Реализация использует
`HttpUpstreamFetcher`, а синхронизация работает вне UoW и диспетчеризации команд (I-05.2).

## 8. Межмодульные вызовы

| Поток | Вызывающий | Владелец | Публичный маршрут |
|---|---|---|---|
| Авторизация команды | bus | access, workspace | `access.public.RbacAuthorizer` (`Authorizer`), `workspace.public.ScopeChain` (`ScopeChainResolver`) |
| Конфиг команды | bus (`load_config`) | platform | `platform.config.ConfigLoader` + `ScopeTree` |
| Создание scope | workspace/planning/execution handlers | kernel | `uow.repo(ScopeRegistry).create(...)` |
| Членство создателя scope | workspace handlers | access | `access.public.grant_initial_membership` |
| Проект при создании плана | planning | workspace | `workspace.public.require_active_project` |
| Mounts для checks | planning | workspace | `workspace.public.project_mounts` |
| Skills/модели при валидации | planning | extensions | `extensions.public.known_keys`, `runtime_catalog` |
| Материалы ревизии | planning | artifacts | `artifacts.public.require_ready_versions`, `latest_ready_version` |
| Старт запуска | execution | planning, extensions, policy | `planning.public.require_active_plan`, `get_revision_specification`, `compile_execution_graph`; `extensions.public.resolve_resource`; `policy.public.effective_permissions` |
| Ревью по запросу | execution | planning | `planning.public.publish_review_request_revision` |
| Материалы задачи | execution | planning; событие artifacts | `planning.public.revision_materials`, `assess_material`; `FileVersionAdded` → `execution.material_available` |
| Admission и роутинг | execution | runtimes, context | `runtimes.public.admit` → `route_role` → `context.public.assemble_draft` |
| Финализация контекста | host-стадия execution | context | host-функции `context.public.collect_host_blocks/finalize/finalize_command` → C `context.finalize_manifest` через `ctx.client`; сервер — `context.public.require_final` |
| Владение контекстом | `context.finalize_manifest` | execution | `ContextOwnerGuard` (control-plane gateway context) → адаптер → `execution.public.require_current_context_owner` |
| Токен шага, доступ к файлам | execution | access, artifacts | `access.public.issue_assignment_token/extend_assignment_tokens/revoke_assignment_tokens`; `artifacts.public.grant_access/revoke_grants` |
| Evidence | execution | artifacts | `artifacts.public.register_file_version`; байты — `SkmClient.upload_blob` |
| Внешний эффект | execution | policy | `policy.public.propose_intent`, `require_approved`, `record_outcome` |
| Онлайн-workers | execution | workspace | `workspace.public.list_online_workers` |
| Pack-уровень конфига | `ConfigLoader` | extensions | `PackConfigSource` → `extensions.public.pack_config_fragments` (адаптер в bootstrap) |
| Проекция | host op `integrations.host.plan_projection` | integrations | Q `integrations.get_desired_projection` (фасады extensions, policy, runtimes) → C `integrations.record_projection_applied` |
| Projection sync | host op `integrations.host.sync_projections` | integrations | Resolves active host checkout bindings, reads effective project settings, checks the Git index, and composes exclude updates with projection plan/apply |
| Hook клиента | host op `integrations.host.evaluate_hook` | integrations, policy | Q `integrations.get_hook_policy`, чистые `policy.public` → C `policy.record_tool_decisions` |
| Уроки | learning | knowledge | `knowledge.public.promote_lesson`, `deprecate_lesson` |
| Сигналы попыток | подписчик `learning.task_outcome_signals` | execution, runtimes | `execution.public.get_attempt_activity`, `list_task_attempts_for_learning`; `runtimes.public.model_context_window` |
| Заметки/отчёты | подписчики exports | planning, execution | события `PlanArchived`, `RunFinished`; `planning.public.get_plan_summary`, `execution.public.get_run_report_data`, `latest_run_outcome` |
| Эскалация блокирующего hook | подписчик `execution.escalate_blocking_hook_failure` | integrations | событие `HookDeliveryFailed` |
| Память в контексте | `context.public.assemble_draft` | knowledge (опц.) | `MemoryRetriever` (адаптер поверх `knowledge.public`, без `depends_on`) |

Каждый фасадный вызов идёт по `depends_on` вызывающего (§2); связи против направления графа — только события,
адаптеры (`WorkerHostLookup`, `ContextOwnerGuard`, `MemoryRetriever`, `PackConfigSource`) или команды через клиента.

## 9. Расхождения источников, разрешённые по владельцу

| Место | Расхождение | Принято |
|---|---|---|
| Реестр runtime на хосте | kernel-platform §2.11a/§5.3a и mechanisms/01 называют `AgentRuntimeRegistry`; runtimes §6 и interfaces.md — `RuntimeRegistry` | `RuntimeRegistry` (владелец — runtimes, conventions §0.1) |
| Адаптер `VaultFs` | kernel-platform §5.3a: `adapters/exports/obsidian/vault.py`; exports §6 и tree.md — `vault_fs.py` | `adapters/exports/obsidian/vault_fs.py` |
| `ExternalConsumer` | kernel-platform §4.1: `application_bus/subscribers.py`; interfaces.md: `application_bus/ports.py` | `ports.py` (§5) |
| `QueryMeta` | kernel-platform §4.4 в блоке `bus.py` | `application_bus/client.py` (§5) |
| Доступ к шлюзам | комментарии owner specs вида `ctx.gateways.blob_store`, `HostGateways.pack_reader` | только `ctx.gateways.get(Port)` (§1) |

## 10. Группа P00.04.b — корневые модули и platform

Материализованы объявления `access`, `settings`, `workspace`, `artifacts` и всегда включённый
`bootstrap/platform_module.py: PLATFORM_MANIFEST`. Зависимости и секции соответствуют §2 этого inventory.
Права в [`permissions.py`](../../src/skm/modules/access/permissions.py) и [`roles.py`](../../src/skm/modules/access/domain/roles.py) содержат каталог и декларативные `ROLE_PERMISSIONS` и `ROLE_RANK`.
Ограничения ролей не исполняются до P04.01/P04.02.

| Модуль | Domain-объявления | Репозиторные Protocol | Gateways |
|---|---|---|---|
| access | Principal, PrincipalIdentity, ApiToken, TokenSecret, Membership, Role, AuthzDecision (Allowed/Denied), состояния и TokenId | PrincipalRepository, IdentityRepository, TokenRepository, MembershipRepository, WorkerHostLookup | control-plane: TokenPepperSource |
| settings | ConfigEntry, HistoryRecord, EntryChange, ImportPlan, WriteRequest, WriteContext, EntryOp, ChangeKind, ChangeType, ConfigEntryId | ConfigEntryRepository, ConfigHistoryRepository, ConfigGenerationCounter | — |
| workspace | Workspace, Project, Repository, RepositoryRemote, ProjectRepository (mount), Host, CheckoutBinding, CheckoutMarker, ObservedCheckout (включая dirty), Worker, WorkerCapabilities, Slug, MountName, HostName, NormalizedRemote, AttachDecision и enum-ы | WorkspaceRepository, ProjectRepository, RepositoryRepository, MountRepository, HostRepository, CheckoutBindingRepository, WorkerRepository | host: RepositoryInspector |
| artifacts | StorageBackend, Blob, BlobLocation, StagedBlob, File, FileVersion, VersionSource, AccessGrant, SafetyRules, SafetyFinding, SafetyReport, MaterialEntry, ContentDigest, классификации/роли/состояния и модульные ID | StagedBlobRepository, BlobRepository, FileRepository, FileVersionRepository, AccessGrantRepository | control-plane: BlobStore (типы порта StagingHandle, BlobObjectStat, BlobLocationRef; не domain StagedBlob/BlobLocation), BlobCoordination; host: MaterialWriter |

`workspace.ports.ProjectRepository` — порт, а `workspace.domain.mount.ProjectRepository` — сущность;
порт импортирует сущность под локальным именем `ProjectMount`, не меняя публичных имён владельца.
`RepositoryId` используется из уже объявленного `kernel.ids`, без второго NewType того же идентификатора.
`TokenGrant` реэкспортируется из kernel (access §18.3), не создаётся второй конкурирующий тип.
Расширение kernel TokenGrant полями assignment_id/step_id/scope_ancestors остаётся владельцу P01.01:
эта группа не реализует аутентификацию и не меняет kernel. В `ApiToken` сами binding-поля уже объявлены.

Фасады содержат сигнатуры owner specs §13 на domain/kernel-типах и `JsonObject` (K20).
Их вызов явно бросает `NotImplementedError`; `RbacAuthorizer` пока Protocol. У `TokenSecret` нет
автоматического dataclass repr с секретом; форматирование тоже явно недоступно до P04.01.
Пакеты application существуют, но `commands`, `queries`, `subscribers`, `host_operations` и
`ModuleManifest.events` пусты. Event payload DTO объявлены только схемами; `domain/events.py: EVENT_TYPES`
перечисляет их URN. Python-классы и регистрация событий появятся после генератора P01.05.a в owner leaf.
Нет `generated/`, handlers, `run`-функций host operations, IO или бизнес-реализаций.

Platform содержит пакетные границы `config/sources`, `jsonc`, `schema`, `logging`, `fs`, `process` и
Protocol-объявления `SettingsRegistry`, `EffectiveConfig`, `ConfigLoader`, `ConfigStore`, `ScopeTree`,
`PackConfigSource`, `SecretResolver`, `StructLogger`, `Redactor`. `platform.config` реэкспортирует свои
интерфейсы. Конструкторы/сборщики конкретных реализаций, разрешение значений и обработка секретов — P01/P02.

### 10.1 Схемы и владельцы

Схемы групп kernel/config/platform/settings/access/workspace/artifacts лежат в `src/skm/schemas/` по `$id`, включая `kernel/data/error-codes.json` (данные, не JSON Schema),
26 секций настроек и `settings/document.v1.json`.
Плоские command, query, result, event и settings contracts разложены по каталогам модуля.
DTO команд, запросов, результатов, views, событий и host operations объявлены там же.
`kernel/check-result.v1.json` — нормализованный doctor report.
В `artifacts/defs.v1.json` к списку safety rules добавлены `CS-MEDIA-MISMATCH` и `CS-EXECUTABLE`,
как требуют правила content-safety артефактов. Остальные контракты этих групп сохранены.



### Research authorization (P09.09.a)

`ContextOwnerGuard.research_policy` bridges to `execution.public.require_research_assignment`.
Execution checks the current worker, run/project, task/attempt, assignment/lease and started step;
writes hold the existing ownership locks. The adapter resolves the run configuration from its
frozen bundle and the current live settings. Context does not import execution.

`access.public.workspace_classification_ceiling` reads current memberships on the workspace chain:
Owner/Maintainer → restricted, Member → confidential, Viewer → internal. Worker ceilings come from
the active run. A requested ceiling only narrows these server values. Disabled sources and URL policy
are checked again before cached documents are returned.

Research recording uses a project admission check followed by the active run or current researcher
permission check. `CommandSpec.replay_guard` repeats that resource authorization before returning an
idempotency receipt, including the concurrent-receipt recovery path. It does not append ledger rows.

## Local projection synchronization (I-09.1)

`skm project activate PROJECT` syncs the project's checkouts bound to the current host
and saves the project and workspace CLI context after a successful sync.
`skm workspace sync-projections [WORKSPACE]` syncs active projects with local
bindings. A checkout shared by multiple projects requires explicit project
activation so workspace sync cannot overwrite one project's projection with another's.

Both commands apply the effective project integration defaults and report any
projection conflicts through their normal outcomes. They install an SKM block in
Git's common `info/exclude` for root `.skm`, `.skm-dev`, and exact conflict
sidecar paths identified by the projection plan. The adapter can add and remove
individual allowlisted entries. Sync retains existing managed entries because
linked worktrees share the exclude file and can still need those entries.
Changes use `info/exclude.lock`, a content check, and atomic replacement.
Entries outside the SKM block retain their original bytes and ordering.

A tracked service path blocks sync with `TRACKED_SERVICE_FILE`.
`skm integrations untrack-service-files --project PROJECT [--mount MOUNT]`
adds the service excludes and stages the removal of service paths from that
checkout's index. Git keeps the working copies and enforces its staged-content
checks. The command defaults to the selected project and its `main` mount.
