# Каталог контрактов

Инвентарь общих контрактов kernel/application_bus, владельцев 14 модулей, портов и межмодульных маршрутов.
Документ — инвентарь, а не альтернативная архитектура: смысл задают код модуля-владельца и схемы в `src/skm/schemas/`; при расхождении прав они.

Нормативные страницы репозитория: [layers and modules](layers-and-modules.md),
[ADR 0003](../adr/0003-module-graph.md), [`kernel/`](../../src/skm/kernel/) и
[`application_bus/`](../../src/skm/application_bus/). Колонка владельцев файлов — [codebase map](CODEBASE-MAP.md).

## 1. Правила маршрутов

P07.03.a реализует чистые правила execution, а не bus handlers. Правила проверки человека
(`PrincipalKind.HUMAN` и `actor_role` manual check) не доказывают право на run. Точные владельцы
проверок перед вызовом домена:

| Команда-владелец (execution §7.1) | Право | Scope из сохранённой сущности |
|---|---|---|
| `execution.record_manual_verdict` | `check.verdict` | run проверяемого check execution |
| `execution.accept_deviation` | `deviation.accept` | run задачи |
| `execution.answer_decision_request` | `inbox.answer` | run decision request |

Их будущие handlers принадлежат `src/skm/modules/execution/application/commands/`; текущие
`application/registry.py` и `module.py` не регистрируют команды execution. Поэтому доменные тесты
не являются проверкой действующего permission enforcement. Approval intent отвечает только
`policy.approve_intent`; `accept_deviation` из ответа дополнительно требует `deviation.accept`,
а `raise_budget` — `run.control`. Эти проверки остаются ответственностью команды-владельца.

Вызов `decide_acceptance` требует `required_checks` из контракта задачи, чтобы отсутствие всех
check executions не давало приёмку. Для `findings_only` вызывающий код передаёт реальные sealed
`outputs` попытки и факт H7; `report` требует `review_req.run_kind = review_request`. Это факты
приложения, а не поля отчёта агента. `DecisionRequest.answer_id` связывает доменную проекцию с
текущей строкой ответа: при чтении её восстанавливает вызывающий код, при повторном открытии
домен очищает её. Без этой связи ответ нельзя применить или записать как решение.

Для reuse `decide_audience(validate_answer=...)` вызывает переданный валидатор с текущими
`answer_schema` и значением ответа; приложение использует `platform.schema`. Отсутствие
валидатора запрещает reuse для схемного вопроса, старый флаг `schema_ok` разрешения не даёт.
Значение одновременно должно соответствовать опциям вопроса. `make_decision_record` не
придумывает категорию, `question_key` или input digest для совета о checks/findings: вызывающий
путь применения совета должен передать категоризованный запрос с этими фактами, иначе
`SCHEMA_INVALID`. Применение такого совета приложением в P07.03.a не реализовано.

Каждый межмодульный вызов имеет одного владельца и один публичный маршрут:

| Маршрут | Кто вызывает | Как | Ограничение |
|---|---|---|---|
| Фасад | bus handler, подписчик, фасад другого модуля | `skm.modules.<owner>.public.<fn>(uow, …)` или чистая функция | только по `depends_on` вызывающего; одна транзакция, фасад не коммитит |
| Команда/запрос bus | поверхности, host operations, фоновые службы | `SkmClient.dispatch/ask` (`ctx.client` на хосте), `Bus.dispatch/ask` | DTO — generated-классы схем владельца |
| Событие | подписчик любого модуля | `SubscriberSpec.event_types` по URN владельца события | зависимости не создаёт |
| Репозиторный порт | только код модуля-владельца и его адаптеры | `uow.repo(Port)` | `@repository_port`; чужой модуль — только через фасад |
| Control-plane gateway | bus handlers, подписчики | `ctx.gateways.get(Port)` | `@control_plane_gateway`/`@shared_gateway`; таблица `kind="control_plane_gateway"` |
| Host gateway | host operations | `ctx.gateways.get(Port)` | `@host_gateway`/`@shared_gateway`; таблица `kind="host_gateway"` |
| Host operation | поверхности, worker, hook | `HostServices.run("<m>.host.<op>", request, …)` | `public.py` host operations не реэкспортирует |

[`InteractiveLauncher`](../../src/skm/adapters/runtimes/interactive.py) управляет локальными терминальными
сессиями выбранного профиля. `skm session start` выбирает runtime и модель через `runtimes.explain_routing`,
читает `runtimes.binaries` на scope хоста и синхронизирует проекции проекта перед запуском CLI в его checkout.
Клиент использует свои обычные локальные credentials и настройки интерактивного режима.
`list`, `attach` и `stop` работают с локальным состоянием без подключения к backend. К одной сессии
можно подключить один терминал. `Ctrl-]` отсоединяет терминал, сохраняя сессию.
На Linux запись сессии хранится с правами `0600` в каталоге `0700`. Перед остановкой через pidfd
launcher проверяет PID, start ticks, boot ID и принадлежность каталога сессии процессу-супервизору.

Доступ к шлюзу — только типизированный `ctx.gateways.get(Port)` с импортом Protocol из `ports.py` владельца.
Строковых ключей, generic locator и атрибутов вида `ctx.gateways.blob_store` нет; такой доступ
читается как `get(BlobStore)`.

P00.05.a проверяет эти маршруты через AST в `tests/architecture/rules.py`: `layer-imports`,
`module-facade`, `module-graph`, `import-cycles`, `domain-purity`, `host-boundary`, `application-boundary`, `host-io`.
`import-cycles` запрещает циклы импортов уровня модуля везде, а в `domain`/`ports` одного модуля — и через
импорты внутри функций: общий тип выносится в нижний модуль, а не прячется в отложенный импорт.
Guardrail `private-imports` пускает `_private` модуль или имя только внутри пакета-владельца (для
`skm.modules.<name>` владелец — весь модуль); известные исключения перечислены в `allowlist.toml`.
Относительные импорты, `from … import …`, alias и реэкспорты сохраняют владельца символа;
repository/control-plane gateways и функции фасада с `uow` недоступны host-коду.
Host-стадии не получают `HostContext`, `SkmClient` или атрибут `client` (DI-8).

Исключения для аннотаций перечислены точными парами source/symbol в `ANNOTATION_CONTRACTS`,
`VALUE_ANNOTATIONS` и `PATH_CONTRACTS`: DTO/ID владельцев для полей domain, типы сигнатур execution §6,
`StageDeps` для конкретных host-стадий и `Path` для объявленных FS-контрактов. Один `TYPE_CHECKING`
не даёт разрешения: вызов, default, базовый класс или присваивание импортированного имени проверяются
как runtime dependency. Вызовы IO через параметр/поле с аннотацией `Path` также запрещены.
Runtime-реэкспорты `StageRequest`/`StageOutcome` (execution §13), `StageClient` (execution §6.3),
`PERMISSIONS` (access §13) и binding `HttpSkmClient` (adapters §8) сохраняют явные owner-контракты;
они перечислены отдельно в `DECLARATION_CONTRACTS` и не разрешают импорт остальных host/bus API.
`_manifests.py` читает фактические `module.py:MODULE` через существующий `MODULE_CATALOG`, пока
`bootstrap.modules.MANIFESTS` не материализован; после появления использует `MANIFESTS`.
Формат allowlist — `[[allow]]` с обязательными `rule`, `path`, `detail`, `reason`, `adr` и необязательным
`until`: путь допускает glob из нормативного примера, detail совпадает с конкретным символом/вызовом,
истёкшая запись является ошибкой. Маленькие bad/good trees и регрессии находятся в root `tests/architecture/`.

## 2. Модули

`src/skm/bootstrap/modules.py: MODULE_CATALOG` хранит этот граф в топологическом порядке. Фактические
`module.py` создают группы P00.04.b–e; P00.04.f проверяет DAG фактических manifests против каталога,
импортируя их напрямую из файлов владельцев без изменения исключённого `bootstrap/modules.py`.

| Модуль | `depends_on` | Опц. | Схема БД | Секции настроек | Декларации (`module.py`, `ports.py`, `public.py`) | Реализация `ports.py`/`public.py` |
|---|---|:-:|---|---|---|---|
| `access` | — | | `skm_access` | `access` | P00.04.b | P04.02.a, P04.02.c |
| `settings` | — | | `skm_config` | — | P00.04.b | P02.07.a, P02.07.b |
| `workspace` | `access` | | `skm_workspace` | `workspace` | P00.04.b | P04.04.a, P04.06 |
| `artifacts` | `workspace` | | `skm_artifacts` | `artifacts` | P00.04.b | P06.01.a, P06.03.a, P06.03.c, P06.04.a |
| `policy` | `access`, `workspace` | | `skm_policy` | `policy` | P00.04.c | P07.01.a, P07.01.b, P10.05.a |
| `extensions` | `workspace`, `policy` | | `skm_extensions` | `extensions` | P00.04.c | P09.01.a |
| `runtimes` | `workspace`, `extensions` | | `skm_runtimes` | `runtimes` | P00.04.c | P08.01.a, P08.01.b, P08.11 |
| `planning` | `workspace`, `artifacts`, `extensions` | | `skm_planning` | `planning` | P00.04.c | P05.04.a, P05.10, P06.04.b |
| `context` | `planning`, `extensions`, `artifacts` | | `skm_context` | `context` | P00.04.d | P09.04.a, P09.04.d, P09.09.a |
| `execution` | `access`, `workspace`, `artifacts`, `extensions`, `policy`, `runtimes`, `planning`, `context` | | `skm_execution` | `execution`, `budgets`, `worker`, `checks` | P00.04.d | P07.05.a, P07.05.c, P07.08.a |
| `integrations` | `workspace`, `artifacts`, `extensions`, `policy`, `runtimes` | | `skm_integrations` | `integrations`, `hooks` | P00.04.e | P10.01.b |
| `knowledge` | `workspace` | ✓ | `skm_knowledge` | `knowledge` | P00.04.e | P13.01.b, P13.03.b |
| `learning` | `workspace`, `runtimes`, `execution`, `knowledge` | ✓ | `skm_learning` | `learning` | P00.04.e | P13.03.b, P13.03.c |
| `exports` | `workspace`, `planning`, `execution` | ✓ | `skm_exports` | `exports` | P00.04.e | P13.04.a |

Псевдомодуль `platform` (kernel-platform §5.6) не входит в каталог: `PLATFORM_MANIFEST` в
`bootstrap/platform_module.py` (P00.04.b, P03.01.b, P03.05, P15.01.a) всегда включён, владеет секциями
`modules`, `plugins`, `logging`, `storage`, `events`, `background`, `api`, `ui` и таблицами `skm_core`.
`settings_sections` содержит id секций; schema URN разрешает `bootstrap/modules.py` по `x-skm-section.id`
(второго списка URN в манифесте нет).

The inventory is split into bounded documents; all existing sections and owner rows are retained.

- [contracts-01.md](contracts-01.md)
- [contracts-02.md](contracts-02.md)
- [contracts-03.md](contracts-03.md)
- [contracts-04.md](contracts-04.md)
- [contracts-05.md](contracts-05.md)
- [contracts-06.md](contracts-06.md)
- [contracts-07.md](contracts-07.md)
- [contracts-08.md](contracts-08.md)
- [Shared integration projections](contracts-09.md)
- [Artifact storage internals](contracts-10.md)
- [Architecture test implementation](contracts-11.md)
- [Agent navigation and preflight](contracts-12.md)

## 3. Два вида прикладного кода — проверяемые типы

[Section contents](contracts-01.md).

## 4. Kernel (P00.04.a — чистые декларации, K20)

[Section contents](contracts-05.md).

## 5. application_bus (P00.04.a)

[Section contents](contracts-05.md).

## 6. Отложенные типы

[Section contents](contracts-05.md).

## 7. Порты

[Section contents](contracts-05.md).

### 7.1 kernel и application_bus (P00.04.a)

[Section contents](contracts-05.md).

### 7.2 platform

[Section contents](contracts-05.md).

### 7.3 Порты модулей

[Section contents](contracts-05.md).

## 8. Межмодульные вызовы

[Section contents](contracts-05.md).

## 9. Расхождения источников, разрешённые по владельцу

[Section contents](contracts-05.md).

## 10. Группа P00.04.b — корневые модули и platform

[Section contents](contracts-05.md).

### 10.1 Схемы и владельцы

[Section contents](contracts-05.md).

### 10.2 Явные JsonObject и отложенные представления

[Section contents](contracts-06.md).

### 10.3 Отложенные ссылки до P00.04.f

[Section contents](contracts-06.md).

## 11. Группа P00.04.c — policy, extensions, runtimes, planning

[Section contents](contracts-06.md).

### 11.1 Владение и временные JsonObject

[Section contents](contracts-06.md).

### 11.2 Схемы и ссылки

[Section contents](contracts-06.md).

## 12. P00.04.d — context and execution contracts

[Section contents](contracts-06.md).

### 12.1 Ports and ownership

[Section contents](contracts-06.md).

### 12.2 Domain declarations and deferred Python wire types

[Section contents](contracts-06.md).

### 12.3 Schema inventory and reference closure

[Section contents](contracts-06.md).

### 12.4 Codegen symbol inventory and wire corrections

[Section contents](contracts-06.md).

## P00.04.e — integrations, knowledge, learning, exports

[Section contents](contracts-06.md).

### Approved Q2 alignment — first-turn budget host contracts

[Section contents](contracts-06.md).

### Approved Q3 alignment and confirmed review corrections

[Section contents](contracts-06.md).

## 14. P00.04.f — adapter slots, surfaces and final closure

[Section contents](contracts-06.md).

### 14.1 Import, graph and offline-reference proof

[Section contents](contracts-06.md).

### 14.2 Complete materialized-file inventory

[Section contents](contracts-06.md).

### P01.05.a: generated contracts

[Section contents](contracts-06.md).

### P01.05.b: compatibility and generated architecture corrections

[Section contents](contracts-07.md).

## Материализованные файлы P01

[Section contents](contracts-07.md).

### Fake runtime admission and finalization (P08.02.a correction)

[Section contents](contracts-07.md).

### Process ownership (follow-up of P08.02.a; P08.02.a itself stays open)

[Section contents](contracts-07.md).

## Материализованные источники config P02.05.a

[Section contents](contracts-07.md).

### P02.08.b: serving-process restart observation

[Section contents](contracts-07.md).

### Policy follow-up: empty host conjunction and the read-only subset

[Section contents](contracts-07.md).

### P09.01.a: the permission proof and the boundary with P09.01.b

[Section contents](contracts-07.md).

### P09.01.a: an equal digest is no proof of equal files

[Section contents](contracts-07.md).

## P07.08.a — local integration additions

See [execution integration contracts](contracts-execution.md).

| File | Responsibility | Leaf |
|---|---|---|
| `src/skm/adapters/git/integration.py` | Local integration contract or implementation | P07.08.a |
| `src/skm/adapters/git/integration_candidate.py` | Local integration contract or implementation | P07.08.a |
| `src/skm/adapters/git/integration_process.py` | Full Git object/ref fsync and journal-bound pidfd-owned ref helper | P07.08.a |
| `src/skm/modules/execution/application/_integration_inputs.py` | Local integration contract or implementation | P07.08.a |
| `src/skm/modules/execution/application/commands/acquire_integration_slot.py` | Local integration contract or implementation | P07.08.a |
| `src/skm/modules/execution/application/commands/record_external_effect.py` | Local integration contract or implementation | P07.08.a |
| `src/skm/modules/execution/application/commands/release_integration_slot.py` | Local integration contract or implementation | P07.08.a |
| `src/skm/modules/execution/generated/_documents_advisor_result_doc.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_advisor_result_doc_checklist_item.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_advisor_result_doc_options_item.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_advisor_result_doc_recommendation.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_advisor_result_doc_sources_item.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_blocking_reason.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_blocking_reason_catalog.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_blocking_reason_catalog_defs_code_entry.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_blocking_reason_defs_json_value.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_decision_record.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_decision_record_defs_json_value.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_defs.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_diagnostic_codes.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_diagnostic_codes_defs_json_value.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_effective_work_policy.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_effective_work_policy_effective.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_effective_work_policy_effective_role_intensity.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_effective_work_policy_emergency_role_seconds.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_effective_work_policy_provenance_item.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_effective_work_policy_requested.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_effective_work_policy_requested_role_intensity.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_effective_work_policy_role_warn_seconds.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_execution_bundle.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_execution_bundle_defs_json_value.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_execution_bundle_frozen_config_doc.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_execution_bundle_resource_pins.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_execution_bundle_resource_pins_resources_item.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_execution_bundle_selection_variant2.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_execution_bundle_selection_variant2_satisfied_item.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_executor_result_doc.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_executor_result_doc_changed_paths_item.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_executor_result_doc_checks_run_item_variant1.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_executor_result_doc_checks_run_item_variant2.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_executor_result_doc_defs_issue.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_executor_result_doc_defs_question.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_executor_result_doc_defs_question_facts.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_executor_result_doc_defs_question_options_item.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_executor_result_doc_recommend_review.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_executor_result_doc_self_check.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_executor_result_doc_self_check_criteria_item.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_executor_result_doc_subagents.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_executor_result_doc_subagents_usage.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_fix_brief.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_fix_brief_defs_json_value.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_fix_brief_items_item.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_fix_brief_items_item_location.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_fix_brief_limits.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_history_page.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_history_page_defs_cause.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_history_page_defs_edge.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_history_page_defs_entity_ref.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_history_page_defs_entry.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_history_page_defs_entry_monitor_evaluation.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_history_page_defs_entry_monitor_evaluation_thresholds_item.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_history_page_defs_entry_wait.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_history_page_defs_node.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_history_page_defs_node_ref.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_history_page_defs_node_timing.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_history_page_defs_nullable_counter.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_history_page_defs_nullable_digest.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_history_page_defs_nullable_utc.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_history_page_defs_nullable_version.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_history_page_runtime_observation_dto.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_history_page_runtime_observation_dto_binding.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_history_page_runtime_observation_dto_capture.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_history_page_runtime_observation_dto_timing.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_history_page_runtime_observation_dto_tools.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_history_page_urn_skm_runtimes_runtime_observation_v1_defs_nullable_counter.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_history_page_urn_skm_runtimes_runtime_observation_v1_defs_nullable_digest.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_history_page_urn_skm_runtimes_runtime_observation_v1_defs_nullable_utc.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_history_page_urn_skm_runtimes_runtime_observation_v1_defs_nullable_version.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_pending_continuation.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_pending_continuation_defs_advance.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_pending_continuation_defs_cause.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_pending_continuation_defs_entity_ref.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_pending_continuation_defs_feedback_refs.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_pending_continuation_defs_json_value.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_pending_continuation_defs_route_ref.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_pending_continuation_defs_semantic_stage.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_pending_continuation_defs_stage.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_pending_continuation_defs_trigger.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_readiness_report.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_readiness_report_defs_json_value.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_readiness_report_findings_item.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_readiness_report_scope.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_readiness_report_start_request_variant2.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_readiness_report_start_request_variant2_selection_variant2.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_registrar_result_doc.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_registrar_result_doc_changelog_entry.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_registrar_result_doc_commit.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_researcher_result_doc.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_researcher_result_doc_claims_item.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_reviewer_result_doc.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_reviewer_result_doc_coverage.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_reviewer_result_doc_defs_finding.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_reviewer_result_doc_defs_finding_location.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_reviewer_result_doc_defs_finding_reproduction.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_route_snapshot.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_route_snapshot_requested.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_route_snapshot_requested_route.py` | Schema-derived execution document shard | P07.08.a → I-05.3 |
| `src/skm/modules/execution/generated/_documents_route_snapshot_resolved.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_route_snapshot_selected_route.py` | Schema-derived execution document shard | P07.08.a → I-05.3 |
| `src/skm/modules/execution/generated/_documents_scout_result_doc.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_scout_result_doc_entry_points_item.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_scout_result_doc_relevant_paths_item.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_scout_result_doc_suggested_checks_item.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_stage_outcome_acceptance_gate.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_stage_outcome_acceptance_gate_defs_json_value.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_stage_outcome_advisor_consult.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_stage_outcome_advisor_consult_defs_json_value.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_stage_outcome_advisor_consult_usage.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_stage_outcome_agent_review.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_stage_outcome_agent_review_defs_json_value.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_stage_outcome_agent_review_usage.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_stage_outcome_agent_step.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_stage_outcome_agent_step_changed_paths_item.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_stage_outcome_agent_step_defs_json_value.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_stage_outcome_agent_step_usage.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_stage_outcome_integrate.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_stage_outcome_integrate_conflict_path_bytes_item.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_stage_outcome_integrate_defs_git_commit_receipt.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_stage_outcome_integrate_defs_json_value.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_stage_outcome_integrate_reconciled_effect.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_stage_outcome_integrate_reconciled_effect_receipt_variant2.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_stage_outcome_phase_gate.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_stage_outcome_phase_gate_defs_json_value.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_stage_outcome_plan_acceptance.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_stage_outcome_plan_acceptance_defs_json_value.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_stage_outcome_prepare_environment.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_stage_outcome_prepare_environment_defs_baseline_entry.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_stage_outcome_prepare_environment_defs_json_value.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_stage_outcome_run_checks.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_stage_outcome_run_checks_results_item.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_stop_codes.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_stop_codes_defs_json_value.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_triager_result_doc.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_triager_result_doc_confirmed_item.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_triager_result_doc_confirmed_item_reproduction.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_triager_result_doc_rejected_item.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_triager_result_doc_rejected_item_reproduction.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_workflow_definition_doc.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_workflow_definition_doc_defs_condition.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_workflow_definition_doc_defs_condition_variant2.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_workflow_definition_doc_defs_condition_variant3.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_workflow_definition_doc_defs_on.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_workflow_definition_doc_defs_params.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_workflow_definition_doc_defs_predicate.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_workflow_definition_doc_defs_predicate_rounds_below.py` | Schema-derived execution document shard | P07.08.a |
| `src/skm/modules/execution/generated/_documents_workflow_definition_doc_defs_stage.py` | Schema-derived execution document shard | P07.08.a |
