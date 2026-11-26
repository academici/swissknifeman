# Архивные примеры SQL

Файлы в этом каталоге используются тестами corpus как самостоятельные примеры. Выпуск
0.1.0 создаёт проектную и машинную базы из действующих миграций в
`src/skm/adapters/postgres/migrations/`. Их проверяют `make sql-check` и
PostgreSQL-тесты свежей установки.

## Каталог исторических примеров

Фазы и номера фиксируют происхождение примеров.

| Файл | Прежнее имя в материалах Opus | Фаза | Исходный пункт | Схема | Таблицы | Отложенные FK |
|---|---|---|---|---|---|---|
| `0001_core_roles.sql` | `0001_core_roles.sql` | P03 | P03.01 | `skm_core` | — (роли `skm_app`/`skm_migrator`, функции `grant_app`, `forbid_mutation`, `forbid_update`) | — |
| `0002_core_scopes.sql` | `0002_core_scopes.sql` | P03 | P03.02 | `skm_core` | `scopes` | — |
| `0003_core_events.sql` | `0003_core_events.sql` | P03 | P03.02 | `skm_core` | `event_streams`, `workspace_event_counters`, `domain_events`, `outbox`, `consumer_receipts` | — |
| `0004_core_idempotency_audit.sql` | `0004_core_idempotency_audit.sql` | P03 | P03.02 | `skm_core` | `idempotency_receipts`, `audit_records` | — |
| `0005_settings_config_entries.sql` | `0005_config_entries.sql` | P03 | P03.06 | `skm_config` (модуль `settings`) | `entries`, `entry_history`, `generation` | — |
| `0006_access_principals_tokens.sql` | `0006_access.sql` | P04 | P04.02 | `skm_access` | `principals`, `principal_identities`, `api_tokens`, `memberships` | — |
| `0007_workspace_core.sql` | `0007_workspace.sql` | P04 | P04.04 | `skm_workspace` | `workspaces`, `projects`, `repositories`, `repository_remotes`, `project_repositories`, `hosts`, `checkout_bindings`, `workers` | — |
| `0008_planning_identity.sql` | `0012_planning_identity.sql` | P05 | P05.05 | `skm_planning` | `plans`, `project_plan_counters`, `plan_aliases`, `plan_revisions`, `revision_payloads`, `plan_drafts`, `plan_entity_identities`, `revision_members` | — |
| `0009_planning_spec.sql` | `0013_planning_spec.sql` | P05 | P05.05 | `skm_planning` | 25: `revision_specs`, `phase_specs`, `batch_specs`, `item_specs`, `unit_specs`, `requirement_specs`, `check_specs`, `acceptance_criteria`, `decision_specs`, `decision_supersessions`, `decision_bindings`, `material_specs`, `material_bindings`, `entity_requirement_links`, `dependency_edges`, `entity_relations`, `batch_members`, `entity_check_bindings`, `criterion_check_bindings`, `review_requirements`, `entity_path_specs`, `artifact_specs`, `entity_read_specs`, `entity_skill_requirements`, `plan_relations` | — |
| `0010_artifacts_files_blobs.sql` | `0008_artifacts.sql` | P06 | P06.03 | `skm_artifacts` | `storage_backends`, `staged_blobs`, `blobs`, `blob_locations`, `files`, `file_versions`, `access_grants` | — |
| `0011_planning_file_bindings.sql` | `0014_planning_file_bindings.sql` | P06 | P06.04 | `skm_planning` | `revision_file_bindings` (+ триггер «материал `file_version` обязан иметь пин») | — (сам FK на `skm_artifacts.file_versions`, созданный в 0010, допустим) |
| `0012_policy_core.sql` | `0010_policy.sql` | P07 | P07.01 | `skm_policy` | `tool_intents`, `approvals`, `decision_audit` | — |
| `0013_execution_runs.sql` | `0016_execution_runs.sql` | P07 | P07.05 | `skm_execution` | 7: `readiness_reports`, `review_requests`, `runs`, `execution_bundles`, `run_reconfigurations`, `run_tasks`, `run_task_edges` | — (в 0013 снят `fk_runs__resource_versions`, см. ниже) |
| `0014_execution_attempts.sql` | `0017_execution_attempts.sql` | P07 | P07.05 | `skm_execution` | 11: `attempts`, `execution_environments`, `attempt_stages`, `attempt_steps`, `assignments`, `assignment_leases`, `step_notes`, `attempt_outputs`, `attempt_file_bindings`, `output_file_bindings`, `run_recoveries` | внутрисхемные, были и раньше: `fk_run_tasks__current_attempt`, `fk_run_tasks__accepted_attempt`, `fk_run_tasks__accepted_output` (колонки `run_tasks` из 0013), `fk_attempts__current_output`, `fk_attempts__execution_environments`; в 0014 снят `fk_attempt_steps__context_manifests` |
| `0015_execution_checks_reviews.sql` | `0018_execution_checks_reviews.sql` | P07 | P07.05 | `skm_execution` | 10: `check_executions`, `manual_check_verdicts`, `check_evidence_bindings`, `reviews`, `review_findings`, `finding_resolutions`, `review_evidence_bindings`, `fix_briefs`, `acceptance_decisions`, `deviation_acceptances` | — (в 0015 снят `fk_reviews__resource_versions`) |
| `0016_execution_budgets_decisions_effects.sql` | `0019_execution_budgets_decisions_effects.sql` | P07 | P07.05 | `skm_execution` | 10: `budget_accounts`, `budget_reservations`, `decision_requests`, `decision_answers`, `decision_records`, `external_effects`, `integration_slots`, `run_integration_hosts`, `result_carry_forwards`, `autopilot_states` | — |
| `0017_runtimes_host_capabilities.sql` | `0011_runtimes.sql` | P08 | P08.01 | `skm_runtimes` | `host_runtimes`, `capability_verifications`, `canonical_models`, `provider_model_offerings`, `model_guidelines`, `host_model_availability` | — |
| `0018_extensions_resources.sql` | `0009_extensions.sql` | P09 | P09.01 | `skm_extensions` | `packs`, `pack_versions`, `resources`, `resource_versions`, `resource_files`, `resource_quarantine` | `skm_execution.runs.fk_runs__resource_versions`, `skm_execution.reviews.fk_reviews__resource_versions`, `skm_runtimes.model_guidelines.fk_model_guidelines__resource_versions` |
| `0019_context_manifests.sql` | `0015_context.sql` | P09 | P09.04 | `skm_context` | `texts`, `context_manifests`, `context_blocks`, `research_queries`, `external_sources` | `skm_execution.attempt_steps.fk_attempt_steps__context_manifests` |
| `0020_integrations_projections.sql` | `0020_integrations.sql` | P10 | P10.01 | `skm_integrations` | `projections`, `projection_files` | — |
| `0021_knowledge_memory_lessons.sql` | `0021_knowledge.sql` | P13 | P13.01 | `skm_knowledge` | `memory_entries`, `lessons`, `graph_indexes`, `graph_nodes`, `graph_edges` | — |
| `0022_learning_core.sql` | `0022_learning.sql` | P13 | P13.03 | `skm_learning` | `activity_records`, `candidates`, `signals`, `candidate_reviews` | — |
| `0023_exports_core.sql` | — (новый) | P13 | P13.04 | `skm_exports` | `vault_notes`, `vault_note_writes` | — |
| `0025_core_event_parent.sql` | — | P01/P03 | P03.03.a | `skm_core` | — (nullable parent_causation_id у domain_events; без backfill) | — |
| `0026_execution_observations.sql` | — | P07/P08 | P07.05.a | `skm_execution` | — (bounded route_snapshot/runtime_observation у attempt_steps; write-once guard) | — |
| `0027_execution_continuation.sql` | — | P07 | P07.05.a | `skm_execution` | — (bounded server-private attempts.continuation; без backfill) | — |
| `0028_execution_reconcile_assignments.sql` | — | P07 | P07.05.a/P07.08.b | `skm_execution` | — (immutable nullable assignments.reconcile_effect_id; no backfill; one active read-only reconcile assignment per effect) | scoped assignments→external_effects by run/task/attempt/effect |
| `0029_work_policy.sql` | — | P05/P07 | P05.05.b/P07.05.a | `skm_planning`, `skm_execution` | — (nullable item/unit work_policy, immutable readiness/bundle work_policies and readiness.start_request; old NULL diagnostic-only) | schema validation remains application-owned |
| `0030_execution_effect_indexes.sql` | — | P07 | — | `skm_execution` | — (UNIQUE(run_id, kind, request_digest) у external_effects; partial index нерешённых эффектов вместо outcome_unknown-only; индекс decision_records по request_id) | — |

## Отложенные ссылки

0018 добавляет runs.workflow_resource_version_id, reviews.profile_version_id и
model_guidelines.resource_version_id → extensions.resource_versions.
0019 добавляет attempt_steps.context_manifest_id → context.context_manifests. В ранних файлах остаются колонки.
Каждое ограничение добавляется NOT VALID и тут же VALIDATE. Цепочка применяется целиком в P03.02.b, поэтому FK
существуют раньше первой строки execution; фиктивные идентификаторы запрещены.

## Строки, засеянные миграциями (seed)

| Таблица | Строка | Миграция | Правило тестовой очистки (`../../spec/testing.md` §5) |
|---|---|---|---|
| `skm_config.generation` | `(id=1, value=0)` | `0005_settings_config_entries.sql` | не TRUNCATE: `UPDATE skm_config.generation SET value = 0 WHERE id = 1` |
| `skm_artifacts.storage_backends` | `('local-primary', 'local', 'paths.blobs_root')` | `0010_artifacts_files_blobs.sql` | не TRUNCATE (справочник неизменен в тестах) |

Новая миграция с `INSERT` seed-данных дописывает строку в эту таблицу; `tests/support/pg.py` берёт список отсюда
(константа `SEEDED_TABLES`), а не из угадывания.

## Закрытые расхождения

- Outbox: pending/failed/delivered/dead; захват через claimed_at/claimed_by и visibility timeout, без delivering.
- idempotency_receipts.scope_key — GENERATED ALWAYS; в INSERT его нет, в поиске он используется.
- Instance event имеет global_position, workspace event — workspace_seq. Instance counter хранится отдельной
  записью event_streams(instance_feed, instance_scope_id), блокируется до обычного stream counter в той же транзакции.
- destination=sse разрешён CHECK outbox (одна строка на workspace-событие, `../../spec/kernel-platform.md` §2.11). Все append-only таблицы закрыты от UPDATE/DELETE для skm_app; триггеры остаются.
- consumer_receipts не append-only: UPDATE запрещён триггером `forbid_row_update`, DELETE разрешён только janitor-задаче
  outbox_gc (после удаления строк outbox пары и срока `events.outbox.delivered_retention_hours`); delivered строки outbox
  удаляет та же задача (индекс `ix_outbox__delivered_at`).
- Все CHECK planning именованы ck_<table>__<rule>.
- step_notes: current claim/fencing + scoped FK на run/attempt/step/assignment; kind=question вместо отдельной ask_question.
- Budget reserve атомарно проверяет лимит; settle сохраняет фактический расход, в том числе превышение.
  Общий CHECK spent+reserved<=limit удалён: иначе ошибка записи скрыла бы реальный расход.
- assignments.required_isolation_profiles принимает четыре встроенных профиля и <plugin_id>:<name>, отвергает NULL/пустые элементы.
- projection_files.pre_image_file_version_id проверяется artifacts.require_ready_versions для workspace проекции
  на application boundary; физический FK одноколоночный. lessons.candidate_id не имеет обратного FK на learning:
  это provenance, исключающий цикл knowledge→learning.

## Исторический результат проверки

Показатели относятся к архивному снимку примеров.

| Применено до | Таблиц | FK | Результат |
|---|---:|---:|---|
| `runner_bootstrap.sql` | 1 | 0 | OK |
| `0001_core_roles.sql` | 1 | 0 | OK |
| `0002_core_scopes.sql` | 2 | 1 | OK |
| `0003_core_events.sql` | 7 | 5 | OK |
| `0004_core_idempotency_audit.sql` | 9 | 7 | OK |
| `0005_settings_config_entries.sql` | 12 | 9 | OK |
| `0006_access_principals_tokens.sql` | 16 | 18 | OK |
| `0007_workspace_core.sql` | 24 | 31 | OK |
| `0008_planning_identity.sql` | 32 | 47 | OK |
| `0009_planning_spec.sql` | 57 | 89 | OK |
| `0010_artifacts_files_blobs.sql` | 64 | 104 | OK |
| `0011_planning_file_bindings.sql` | 65 | 106 | OK |
| `0012_policy_core.sql` | 68 | 112 | OK |
| `0013_execution_runs.sql` | 75 | 136 | OK |
| `0014_execution_attempts.sql` | 86 | 176 | OK |
| `0015_execution_checks_reviews.sql` | 96 | 205 | OK |
| `0016_execution_budgets_decisions_effects.sql` | 106 | 232 | OK |
| `0017_runtimes_host_capabilities.sql` | 108 | 234 | OK |
| `0018_extensions_resources.sql` | 114 | 245 | OK |
| `0019_context_manifests.sql` | 119 | 257 | OK |
| `0020_integrations_projections.sql` | 121 | 261 | OK |
| `0021_knowledge_memory_lessons.sql` | 126 | 279 | OK |
| `0022_learning_core.sql` | 130 | 289 | OK |
| `0023_exports_core.sql` | 132 | 293 | OK |

Невалидированных ограничений, неименованных planning CHECK и доступных на запись immutable таблиц:0.
Отрицательные пробы isolation (5), instance cursor и SSE destination прошли.
