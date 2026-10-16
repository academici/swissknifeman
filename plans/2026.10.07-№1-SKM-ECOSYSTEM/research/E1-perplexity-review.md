<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

# [https://github.com/academici/swissknifeman](https://github.com/academici/swissknifeman)

изучи plans/2026.10.07-№1-SKM-ECOSYSTEM

В общем, смотри, я хочу. Текущий монорепозиторий разбить на вот такие вот отдельные компоненты. Я хочу, чтобы ты проанализировал план и прямо сюда мне выдал подробный отчёт с рекомендациями: что стоит улучшить, что. То есть, ищи какие-то готовые решения, ищи какие-то свежие идеи. То есть для меня нужна вот такая вот идеальная экосистема, где. Расширяемая, настраиваемая, то есть тут от тебя важны идеи, подходы, практики, что может в дальнейшем понадобиться, чтобы самые лучшие из этого мы зафиксировали. Делай в несколько итераций, мне важен объём от тебя. То есть какие-то открытые репозитории, референсы давай, там, всё что может помочь для дальнейшего. Реализации. Чтобы. Мы сразу подчеркнули всё самое лучшее.@GitHub

План в целом сильный: границы компонентов уже намечены разумно, контракты и отрицательная область ответственности описаны лучше, чем в большинстве подобных миграций. Но в текущем виде я бы **не начинал физическое разделение репозиториев**: сначала нужно устранить несколько противоречий владения, вынести общие контракты в отдельный артефакт и определить модель расширений, совместимости, конфигурации, событий и сборки экосистемы.

## Ключевой вердикт

Главная опасность плана — получить не экосистему, а **семь независимо версионируемых репозиториев со скрытой распределённой связанностью**. Сейчас многое хорошо разделено на уровне директорий, но некоторые важнейшие обязанности одновременно заявлены у `skm-orchestrator`, `swissknife-engine`, `skm-provider-integrations` и `skm-workflow-runtime`.

Моя рекомендуемая целевая модель:

1. **Не семь, а девять логических продуктов**: семь запланированных компонентов, отдельный `skm-contracts` и интеграционный `skm-ecosystem`.
2. **Контракты — language-neutral**: JSON Schema, протокол событий, manifests, compatibility policy; Python-типы генерируются или реализуют этот контракт, а не являются единственным источником истины.
3. **Каждый runtime имеет ровно одного владельца выполнения**: orchestrator компилирует граф, engine исполняет локальный запуск, workflow runtime обеспечивает durable execution.
4. **Расширения подключаются через capability manifests и порты**, а не через прямые импорты соседних репозиториев.
5. **Экосистема собирается из совместимых версий через lock/catalog**, а не через ветки и копии исходников.
6. **Текущий монорепозиторий используется как strangler-shell во время миграции**, а не как вечный integration-monorepo и не как папка с замороженными копиями новых проектов.

## Что уже хорошо

В [README плана](https://github.com/academici/swissknifeman/blob/main/plans/2026.10.07-%E2%84%961-SKM-ECOSYSTEM/README.md) правильно зафиксированы несколько базовых принципов:

- Сначала контракты и границы, затем extraction.
- Каждый standalone-репозиторий должен собираться и тестироваться самостоятельно.
- Нельзя сохранять скрытые импорты из исходного монорепозитория.
- Для каждого компонента описывается не только то, чем он является, но и то, чем он **не должен становиться**.
- Для будущих проектов сохраняется thin-bootstrap вместо ручного копирования инфраструктуры.
- Провайдерские адаптеры отделяются от engine-neutral orchestration.

Особенно полезны документы [`component-contracts.md`](https://github.com/academici/swissknifeman/blob/main/plans/2026.10.07-%E2%84%961-SKM-ECOSYSTEM/design-notes/component-contracts.md), [`dependency-graph.md`](https://github.com/academici/swissknifeman/blob/main/plans/2026.10.07-%E2%84%961-SKM-ECOSYSTEM/design-notes/dependency-graph.md), [`versioning-and-compatibility.md`](https://github.com/academici/swissknifeman/blob/main/plans/2026.10.07-%E2%84%961-SKM-ECOSYSTEM/design-notes/versioning-and-compatibility.md) и [`config-precedence.md`](https://github.com/academici/swissknifeman/blob/main/plans/2026.10.07-%E2%84%961-SKM-ECOSYSTEM/design-notes/config-precedence.md). Они показывают, что разделение задумано именно как архитектурная миграция, а не как механический перенос файлов.

Отдельно хорош текущий [`EnginePort`](https://github.com/academici/swissknifeman/blob/main/packages/orch/docs/engine-port.md): там уже есть важные идеи — один workflow owner на run, capability negotiation, явные ошибки, attempt-aware reducer, запрет считать окончание event stream успехом и защита от событий после terminal state. Это следует не переписывать в каждом проекте, а превратить в основу общего execution protocol.

## Оценка зрелости

| Область | Оценка | Комментарий |
| :-- | --: | :-- |
| Границы компонентов | 8/10 | Хороший старт, но есть несколько пересечений владения |
| Контракты | 8/10 | Много полезных заготовок, но нет отдельного contract product |
| Независимость репозиториев | 6/10 | Заявлена, но пока не обеспечена проверяемыми правилами |
| Расширяемость | 5/10 | Нет единой модели plugins, manifests, discovery и compatibility |
| Версионирование | 6/10 | SemVer упомянут, но не определена совместимость экосистемы |
| Конфигурация | 6/10 | Precedence намечен, но нет provenance, patch semantics и secret references |
| Durable execution | 7/10 | Хорошая модель событий, не хватает lease/fencing/idempotency |
| Supply-chain security | 4/10 | Нет подписей, provenance, SBOM, release verification |
| Миграционная безопасность | 6/10 | Нужны shadow-run, dual compatibility и rollback criteria |
| Документирование решений | 5/10 | Есть design notes, но нет ADR lifecycle и архитектурных fitness checks |

## Главные противоречия

### Orchestrator и skills

В dependency graph заявлено, что `skm-orchestrator` не зависит от `skm-skills`, но в дизайн-заметках orchestration использует `SkillRouter` для role resolution. Это создаёт скрытую зависимость:

```text
orchestrator -> concrete SkillRouter -> skills
```

Исправление:

```text
orchestrator -> RoleResolverPort
skills -> SkillRoleResolver implements RoleResolverPort
ecosystem/composition-root -> wires them together
```

В минимальной установке orchestrator должен принимать уже разрешённый `RoleSpec`, а интеграция с каталогом skills должна быть optional adapter:

```toml
skm-orchestrator
skm-orchestrator[skills]
skm-orchestrator[temporal]
```

При этом extra не должен превращаться в обязательную runtime-зависимость базового пакета.

### Orchestrator и engine

В [`component-contracts.md`](https://github.com/academici/swissknifeman/blob/main/plans/2026.10.07-%E2%84%961-SKM-ECOSYSTEM/design-notes/component-contracts.md) orchestrator называется thin layer и не должен владеть subprocess management. Но в этапах миграции ему добавляется `SubprocessBackend`, который уже владеет запуском процессов.

Нужно разделить два понятия:

- **Orchestration compiler**: строит `ExecutionPlan`, проверяет capabilities, routes, policies, dependencies и approvals.
- **Execution backend**: исполняет stage, управляет subprocess/container/remote call и возвращает события.

То есть `SubprocessBackend` должен жить либо в `swissknife-engine`, либо в отдельном adapter package внутри orchestrator-репозитория, который не входит в orchestrator core:

```text
skm.orchestrator.core
skm.orchestrator.adapters.engine
skm.orchestrator.adapters.subprocess
skm.orchestrator.adapters.temporal
```


### Workflow и providers

План одновременно говорит:

- `skm-provider-integrations` владеет provider adapters;
- `skm-workflow-runtime` владеет provider SDK paths и backend selection.

Это почти гарантированно приведёт к дублированию auth, retry, rate-limit и error mapping.

Правильнее:

```text
workflow runtime
    -> ActivityPort
        -> ProviderClientPort
            -> provider adapter
```

Workflow runtime должен владеть:

- durable state;
- timers;
- activity scheduling;
- retries на уровне durable workflow;
- heartbeats;
- compensation;
- replay-safe orchestration.

Provider integrations должны владеть:

- SDK invocation;
- provider authentication;
- нормализацией provider errors;
- provider-specific rate-limit metadata;
- model/catalog discovery;
- streaming transport.

**Backend selection должен принадлежать composition layer**, а не Temporal workflow code. Иначе replay workflow начнёт зависеть от изменяемого окружения или provider catalog.

### Engine и workflow

`swissknife-engine` уже близок к самостоятельному execution runtime, а `skm-workflow-runtime` — второй execution runtime. Здесь нельзя оставлять двусмысленность.

Рекомендую зафиксировать:

- Engine — **ephemeral/local execution owner**.
- Workflow runtime — **durable execution owner**.
- Orchestrator — **plan owner до запуска**, но не runtime owner после передачи.
- Один run никогда не исполняется одновременно engine и workflow runtime.
- Workflow runtime может запускать отдельные activities через engine adapter, но engine тогда не владеет общим workflow state.
- Переключение runtime происходит до `run.start`, а не посреди run.

Ваше текущее правило «one run has one workflow owner» из [`engine-port.md`](https://github.com/academici/swissknifeman/blob/main/packages/orch/docs/engine-port.md) нужно поднять в нормативный ecosystem contract.

## Новая карта продуктов

Я бы зафиксировал следующую структуру.


| Продукт | Владеет | Не владеет |
| :-- | :-- | :-- |
| `skm-contracts` | Schemas, IDs, events, errors, manifests, compatibility | Runtime, storage, providers |
| `skm-skills` | Skill discovery, normalization, materialization, provenance | Agent execution |
| `skm-doctor` | Read-only probes, diagnostics, repair plans | Routing, provider execution |
| `skm-provider-integrations` | Provider adapters, auth state, SDK normalization | Workflow retries, orchestration |
| `swissknife-engine` | Local execution, subprocess/container backends, run state | Durable workflow ownership |
| `skm-orchestrator` | Plan compilation, role/policy/capability resolution | Provider SDK logic, long-term state |
| `skm-workflow-runtime` | Durable workflows, activities, timers, compensation | Skill discovery, provider-specific business logic |
| `skm-presets` | User-facing presets, templates, generated tasks | Generic runtime primitives |
| `skm-ecosystem` | Tested version catalog, umbrella CLI, profiles, integration tests | Реализация внутренних функций компонентов |

### Почему нужен `skm-contracts`

Сейчас contracts фактически распределены между `orch`, engine docs, JSON schemas и планом. После split это приведёт либо к копированию, либо к зависимости всех компонентов от orchestrator.

В `skm-contracts` нужно вынести:

- `ExecutionInput`;
- `ExecutionPlan`;
- `RunEvent`;
- `RunResult`;
- `StageResult`;
- `CapabilityManifest`;
- `PluginManifest`;
- `ProviderDescriptor`;
- `SkillDescriptor`;
- `HealthCheckDescriptor`;
- `PolicyDecision`;
- `EffectRequest`;
- `EffectReceipt`;
- error taxonomy;
- canonical digest algorithm;
- schema evolution rules.

Схемы должны содержать конкретные `$schema` и `$id`: официальные рекомендации JSON Schema советуют указывать конкретный version URI и уникальный identifier, а не неявный «latest».[^1_1]

Python package можно назвать `skm-contracts`, но использовать единое namespace:

```python
from skm.contracts import RunEvent
from skm.engine import Engine
from skm.orchestrator import PlanCompiler
from skm.providers import ProviderRegistry
```

Это позволит позднее написать adapters на Go, TypeScript или Rust без необходимости импортировать Python-классы как нормативный контракт.

### Почему нужен `skm-ecosystem`

Независимые репозитории не должны означать отсутствие центра интеграции. Нужен репозиторий, который содержит не реализации, а:

- ecosystem compatibility catalog;
- full-stack integration tests;
- Docker Compose/devcontainer;
- example applications;
- release train manifests;
- `skm.lock`;
- reference profiles;
- документацию верхнего уровня;
- migration guides;
- umbrella installer;
- smoke tests против опубликованных wheel/OCI artifacts.

Это похожая идея на custom distribution в OpenTelemetry Collector: отдельные компоненты остаются независимыми, а конечная сборка выбирает нужные receivers/processors/exporters/extensions без модификации core.[^1_2][^1_3]

## Модель расширений

Сейчас план говорит об adapters, engines и integrations, но не определяет единый extension protocol. Это надо сделать до split, иначе каждый репозиторий изобретёт свой registry.

### Три уровня

| Уровень | Механизм | Когда использовать |
| :-- | :-- | :-- |
| In-process | Python entry points | Доверенные легковесные расширения |
| Out-of-process | JSON-RPC/stdio или local socket | Изоляция, другой runtime, независимый lifecycle |
| Remote | HTTP/gRPC transport adapter | Distributed execution и managed services |

Python entry points специально предназначены для того, чтобы установленный distribution рекламировал компоненты, которые другие приложения могут обнаруживать через стандартизированную metadata-модель.[^1_4]

Пример:

```toml
[project.entry-points."skm.providers"]
anthropic = "skm_anthropic:provider_plugin"

[project.entry-points."skm.skills.sources"]
claude = "skm_skills_claude:source_plugin"

[project.entry-points."skm.doctor.checks"]
anthropic_auth = "skm_anthropic:doctor_checks"

[project.entry-points."skm.engine.backends"]
docker = "skm_engine_docker:backend_plugin"
```


### Plugin manifest

Каждое расширение должно публиковать manifest до загрузки кода:

```yaml
manifest_version: skm.plugin/v1
id: provider.anthropic
version: 2.1.0
kind: provider
protocol:
  name: skm-provider
  min_version: 1
  max_version: 2
requires:
  contracts: ">=1.4,<2"
provides:
  - capability: provider.chat
    stability: stable
  - capability: provider.streaming
    stability: beta
permissions:
  network:
    - api.anthropic.com:443
  secrets:
    - ref: provider.anthropic.api_key
  filesystem: []
entrypoint: skm_anthropic:plugin
```

Manifest должен позволять ecosystem resolver отклонить несовместимый plugin **до импорта Python-модуля**.

### Protocol handshake

Для out-of-process plugins полезен подход HashiCorp `go-plugin`: host запускает plugin, проверяет handshake, согласует app protocol version и только затем устанавливает RPC-соединение. Не нужно копировать реализацию, но нужно заимствовать семантику:[^1_5]

```json
{
  "core_protocol": 1,
  "application_protocol": "skm-provider/2",
  "plugin_id": "provider.anthropic",
  "plugin_version": "2.1.0",
  "capabilities_digest": "sha256:...",
  "transport": "stdio-jsonrpc"
}
```

Обязательно различать:

- plugin package version;
- manifest version;
- wire protocol version;
- contract schema version;
- capability version.

Один SemVer не способен корректно выражать все эти уровни.

## Capability model

Текущий `EnginePort.capabilities()` — хороший фундамент, но capability должна быть не строкой, а версионируемым объектом.

```yaml
id: execution.resume
version: 1
support: supported
source: probed
constraints:
  after_process_restart: true
  max_age_seconds: 86400
evidence:
  checked_at: 2026-10-07T18:00:00Z
  probe: temporal.server.capabilities
```

Для каждого capability нужны:

- ID;
- semantic version или monotonic revision;
- `supported | unsupported | unknown | degraded`;
- `declared | probed | inferred`;
- ограничения;
- срок актуальности probe;
- evidence;
- stability;
- remediation URL.

Особенно важно разделить:

- **feature capability** — поддерживается ли resume;
- **resource capability** — доступна ли сейчас quota;
- **policy permission** — разрешено ли действие;
- **health state** — работает ли зависимость сейчас.

Иначе `CAPABILITY_UNSUPPORTED`, rate limit, policy refusal и provider outage начнут смешиваться.

## Execution protocol

Текущий event reducer уже содержит хорошие идеи, но перед extraction я бы усилил модель следующими полями:

```json
{
  "specversion": "skm.events/v1",
  "id": "evt_01...",
  "source": "skm://engine/native/worker-4",
  "type": "skm.stage.completed",
  "time": "2026-10-07T18:32:11.102Z",
  "run_id": "run_01...",
  "stage_id": "stage_review",
  "attempt": 2,
  "seq": 184,
  "correlation_id": "run_01...",
  "causation_id": "evt_01_previous",
  "owner_epoch": 7,
  "schema": "https://schemas.swissknifeman.dev/events/stage-completed/v1",
  "data": {}
}
```

CloudEvents полезен как референс envelope: он стандартизирует общий формат контекста события отдельно от payload и предназначен для совместимости между сервисами и платформами. Не обязательно делать SKM полностью CloudEvents-compliant, но поля `id`, `source`, `type`, `time`, `subject`, `dataschema` и отделение envelope от data стоит заимствовать.[^1_6][^1_7]

### Обязательные свойства

- `run_id` глобально уникален.
- `stage_id` стабилен внутри plan.
- `attempt` монотонен для stage.
- `seq` монотонен в рамках event stream owner.
- `event.id` обеспечивает deduplication.
- `causation_id` связывает команду и результат.
- `owner_epoch` является fencing token.
- Terminal state монотонен.
- Повторная доставка того же события идемпотентна.
- Событие предыдущего owner epoch отклоняется.
- `cancel` является request, а не доказательством остановки.
- `cancelled` появляется только после подтверждённого прекращения execution.
- `unknown_outcome` не преобразуется автоматически в `failed`.


### Lease и fencing

Правила `seq` недостаточно при worker failover. Нужны:

- owner lease;
- owner epoch;
- heartbeat;
- lease expiration;
- fencing token в каждой записи;
- compare-and-set при смене owner.

Без fencing старый worker после сетевой паузы сможет продолжить писать события уже после того, как run забрал другой worker.

### Idempotency

Для команд нужны независимые ключи:

```text
submission_id
plan_digest
run_id
stage_execution_id
effect_id
```

Инварианты:

- Повторный `prepare` с теми же входами даёт тот же `plan_digest`.
- Повторный `run(plan, submission_id)` возвращает существующий run.
- Повторный side effect с тем же `effect_id` не выполняется заново.
- Повторный `cancel` безопасен.
- Resume создаёт новый owner epoch, но не новый логический run.
- Effect receipt хранит фактический provider/resource identifier.


## Plan compiler

`skm-orchestrator` лучше рассматривать как **компилятор декларативного workflow**, а не как imperative coordinator.

Pipeline:

```text
Raw request
  -> schema validation
  -> config resolution
  -> role resolution
  -> skill resolution
  -> policy evaluation
  -> capability matching
  -> route resolution
  -> dependency graph validation
  -> effect classification
  -> approval planning
  -> immutable ExecutionPlan
```

`ExecutionPlan` должен быть полностью самодостаточным и неизменяемым:

- normalized inputs;
- resolved component versions;
- digests;
- selected runtime;
- selected providers/models;
- capability evidence;
- role and skill digests;
- policy decisions;
- approvals;
- effect declarations;
- artifact references;
- timeouts;
- retry budgets.

После запуска нельзя молча пересобирать plan из текущих конфигов. Если разрешён adaptive re-planning, он должен создавать `PlanRevision` с отдельным digest и событием, объясняющим причину.

## Skills как артефакты

`skm-skills` сейчас выглядит как resolver и materializer, но для долгосрочной экосистемы ему нужна полноценная artifact model.

Skill должен иметь:

```yaml
api_version: skm.skill/v1
id: review.security
version: 3.2.0
digest: sha256:...
source:
  type: git
  repository: https://github.com/example/security-skills
  revision: 8f4d...
license: Apache-2.0
compatibility:
  contracts: ">=1.4,<2"
  agents:
    claude-code: ">=2"
    codex: ">=1"
inputs_schema: schemas/input.json
outputs_schema: schemas/output.json
capabilities:
  required:
    - tool.filesystem.read
  optional:
    - tool.github.review
instructions:
  path: SKILL.md
```


### Нужные операции

- `discover`;
- `inspect`;
- `validate`;
- `resolve`;
- `materialize`;
- `lock`;
- `verify`;
- `explain`;
- `diff`;
- `vendor`;
- `publish`.


### Обязательные свойства

- Content-addressed digest.
- Provenance: откуда получен skill.
- Conflict resolution.
- Explicit source precedence.
- License metadata.
- Schema validation.
- Tool permission declaration.
- Compatibility declaration.
- Mutable aliases отдельно от immutable versions.
- Lock-файл с точной revision.
- Возможность offline materialization.

Не стоит материализовывать skill напрямую в рабочую директорию без manifest и receipt. Иначе невозможно доказать, какая именно версия инструкций участвовала в run.

## Doctor как платформа

`skm-doctor` не должен знать внутренности всех компонентов. Каждый component/plugin должен публиковать read-only health checks через extension point.

```python
class HealthCheck(Protocol):
    id: str
    severity: Severity

    def probe(self, context: ProbeContext) -> CheckResult: ...
    def remediation(self, result: CheckResult) -> RepairPlan | None: ...
```

Check result:

```json
{
  "check_id": "provider.anthropic.auth",
  "status": "fail",
  "category": "auth",
  "observed": {},
  "evidence": [],
  "remediation": {
    "automatic": false,
    "commands": [],
    "documentation": "..."
  }
}
```

Нужно жёстко разделить:

- `probe` — только чтение;
- `plan-repair` — построение плана;
- `apply-repair` — effectful operation с подтверждением;
- `verify-repair` — повторная проверка.

Это позволит doctor оставаться безопасным по умолчанию и не превращаться в привилегированный универсальный скрипт.

## Provider integrations

Я бы разделил этот репозиторий минимум на четыре слоя:

```text
skm.providers.contracts
skm.providers.registry
skm.providers.auth
skm.providers.adapters.*
```


### Нормализованные ошибки

Provider error должен содержать:

```json
{
  "class": "quota",
  "provider": "anthropic",
  "provider_code": "rate_limit_error",
  "retryable": true,
  "retry_after_ms": 12000,
  "scope": "organization",
  "safe_message": "Provider rate limit exceeded",
  "diagnostic_ref": "artifact://..."
}
```

Основные классы:

- `authentication`;
- `authorization`;
- `quota`;
- `rate_limit`;
- `invalid_request`;
- `model_unavailable`;
- `content_policy`;
- `transport`;
- `provider_internal`;
- `timeout`;
- `unknown`.

Workflow runtime принимает решения на основе нормализованного класса и retry metadata, но не парсит тексты provider exceptions.

### Секреты

Provider repo может владеть схемой `AuthProfile`, но не самим secret store. В профиле должны находиться handles:

```yaml
provider: anthropic
credentials:
  api_key:
    secret_ref: env://ANTHROPIC_API_KEY
```

или:

```yaml
secret_ref: keyring://skm/anthropic/default
```

Raw secret не должен попадать в:

- `ExecutionPlan`;
- events;
- logs;
- doctor report;
- cached manifests;
- effect receipts;
- telemetry attributes.


## Конфигурация

Текущую идею precedence нужно расширить до полноценного resolver с provenance.

Рекомендуемый порядок:

```text
schema defaults
< component defaults
< ecosystem profile
< user config
< workspace config
< environment overlay
< invocation config
< CLI flags
```

Для каждого итогового значения команда `config explain` должна показывать источник:

```text
providers.anthropic.model = claude-sonnet-...
source: workspace
file: /project/.skm/config.yaml
line: 18
overrode:
  - user config: ~/.config/skm/config.yaml
  - component default
```

Нужно заранее определить семантику:

- отсутствующее поле;
- `null`;
- удалить значение;
- заменить массив;
- объединить map;
- добавить элемент;
- запретить override;
- secret reference;
- unknown field.

Для overlays можно заимствовать сам принцип OpenAPI Overlay: отдельный документ хранит упорядоченный набор детерминированных изменений к исходному документу, не изменяя original. Сам OpenAPI Overlay не следует напрямую применять к произвольной SKM-конфигурации, но его модель `target + update/remove/copy` полезна как референс.[^1_8][^1_9]

## Ecosystem lock

Нужен единый `skm.lock`, создаваемый resolver:

```yaml
lock_version: 1
contracts: 1.6.0
components:
  engine:
    version: 2.4.1
    artifact: pypi:swissknife-engine@2.4.1
    digest: sha256:...
  orchestrator:
    version: 1.8.0
    artifact: pypi:skm-orchestrator@1.8.0
    digest: sha256:...
plugins:
  provider.anthropic:
    version: 2.1.0
    digest: sha256:...
skills:
  review.security:
    version: 3.2.0
    digest: sha256:...
schemas:
  run_event: skm.run-event/v1
profile:
  source: profiles/development.yaml
  digest: sha256:...
```

Это решит сразу несколько задач:

- воспроизводимость;
- диагностику;
- bug reports;
- offline installation;
- rollback;
- проверку совместимости;
- audit trail;
- повторное выполнение старого run.


## Версионирование

Одного SemVer каждого репозитория недостаточно. Нужны четыре независимых compatibility dimensions.


| Уровень | Пример | Breaking change |
| :-- | :-- | :-- |
| Package API | `skm-orchestrator 2.1.0` | Удаление публичного Python API |
| Contract schema | `skm.run-event/v1` | Изменение значения или обязательности поля |
| Wire protocol | `skm-provider/2` | Несовместимое RPC-поведение |
| Capability | `execution.resume@1` | Изменение семантики capability |

Добавление необязательного поля обычно совместимо, но удаление поля, сужение enum или изменение семантики — нет. OpenTelemetry отдельно маркирует telemetry conventions уровнями зрелости и запрещает стабильным producers произвольно менять форму стабильной telemetry; похожий lifecycle полезен и для ваших contracts:[^1_10][^1_11]

```text
development -> alpha -> beta -> release_candidate -> stable -> deprecated
```

Для каждого schema major нужно определить:

- сколько предыдущих версий читает consumer;
- сколько версий пишет producer;
- кто выполняет upcast;
- разрешён ли downcast;
- срок поддержки deprecated schemas;
- что происходит при unknown fields;
- как публикуются migration fixtures.


## Umbrella CLI

Я бы сохранил независимые команды:

```text
skm-skills
skm-doctor
skm-engine
skm-orchestrator
skm-workflow
skm-presets
```

Но добавил необязательный umbrella CLI:

```text
skm skills ...
skm doctor ...
skm run ...
skm workflow ...
skm preset ...
skm plugins ...
skm config ...
skm ecosystem ...
```

Subcommands должны обнаруживаться через entry points, а не импортироваться жёстким списком. Тогда installation profile сможет включать только нужные компоненты:

```bash
pip install skm
pip install "skm[local]"
pip install "skm[temporal]"
pip install "skm[full]"
```

При этом `skm` должен быть composition package, а не восьмым местом для бизнес-логики.

## Наблюдаемость

Нужна единая semantic convention для logs, traces, metrics и events. OpenTelemetry semantic conventions как раз решают задачу общего именования attributes между библиотеками и платформами.[^1_12][^1_13]

Предлагаемые attributes:

```text
skm.component.name
skm.component.version
skm.contract.version
skm.run.id
skm.stage.id
skm.stage.attempt
skm.runtime.kind
skm.binding
skm.provider.name
skm.model.id
skm.route.class
skm.plan.digest
skm.skill.digest
skm.policy.decision
skm.effect.kind
```

Но `run.id`, `stage.id`, prompt digest и model response ID нельзя бездумно помещать в metric labels из-за высокой cardinality. Они подходят для spans/logs/events, а metrics должны использовать bounded dimensions.

Минимальный набор spans:

```text
skm.plan.compile
skm.run.execute
skm.stage.execute
skm.provider.invoke
skm.skill.resolve
skm.policy.evaluate
skm.effect.apply
skm.artifact.write
```


## Артефакты запуска

Нельзя хранить большие prompts, outputs и reports внутри event stream. Нужен `ArtifactStorePort` с content-addressed objects:

```text
artifact://sha256/<digest>
```

Event содержит только:

- artifact reference;
- media type;
- byte size;
- digest;
- sensitivity;
- retention class;
- encryption metadata.

Это позволит использовать filesystem, S3-compatible storage, database blob storage или remote artifact service без изменения execution contracts.

Для чувствительных данных нужны классы:

```text
public
internal
confidential
secret
regulated
```

Policy engine должен решать, можно ли артефакт:

- логировать;
- передавать внешнему provider;
- сохранять;
- кэшировать;
- экспортировать;
- использовать при replay.


## Безопасность расширений

In-process plugin фактически получает права host process. Поэтому по умолчанию:

- third-party plugins должны поддерживать out-of-process mode;
- permissions объявляются в manifest;
- secrets выдаются только по разрешённым references;
- filesystem ограничивается workspace roots;
- network destinations декларируются;
- shell execution считается отдельной capability;
- effectful operations требуют policy decision;
- неподписанный plugin помечается как untrusted;
- doctor показывает provenance и verification status.

Нужна возможность запускать plugin в:

- subprocess с очищенным environment;
- container;
- restricted user;
- read-only filesystem;
- network-disabled sandbox.


## Supply-chain

Каждый release должен публиковать:

- sdist;
- wheel;
- checksums;
- SBOM;
- provenance;
- signature;
- changelog;
- compatibility manifest;
- schema bundle.

CycloneDX предназначен не только для списка пакетов, но и для представления зависимостей, сервисов и supply-chain relationships. SLSA provenance фиксирует, какой builder, invocation и materials произвели артефакт, и связывает output с digest.[^1_14][^1_15][^1_16][^1_17]

Для подписей можно использовать Sigstore/Cosign: keyless signing связывает короткоживущий сертификат с OIDC identity, а событие подписи регистрируется в transparency log. Это особенно полезно, если plugins, profiles и skills позднее будут устанавливаться из внешних репозиториев.[^1_18][^1_19]

## CI каждого репозитория

Текущий монорепозиторий уже содержит центральные workflows в [`.github/workflows`](https://github.com/academici/swissknifeman/tree/main/.github/workflows). После split нельзя просто скопировать их семь раз и затем поддерживать вручную.

Лучше создать организационный `.github`/workflow-template repository с reusable workflows:

```text
python-quality.yml
python-test.yml
contract-compatibility.yml
build-wheel.yml
wheel-smoke.yml
security.yml
release.yml
ecosystem-integration.yml
```


### Обязательная матрица

Для каждого component repo:

1. Lint и formatting.
2. Type checking.
3. Unit tests.
4. Build sdist и wheel.
5. Установка wheel в чистое окружение.
6. Запуск тестов вне checkout.
7. Проверка CLI.
8. Contract fixtures.
9. Oldest supported dependencies.
10. Latest compatible dependencies.
11. Минимальная и максимальная поддерживаемая contract version.
12. Secret scan.
13. Dependency audit.
14. SBOM generation.
15. Provenance/signature при release.

Изолированные test environments важны именно потому, что обнаруживают hidden dependencies на локальные пакеты; tox isolated build используется для сборки и установки distribution в отдельное окружение. Критическая проверка должна тестировать **опубликованную форму пакета**, а не source checkout.[^1_20][^1_21]

### Consumer-driven contracts

Для каждой пары producer/consumer нужны fixtures:

```text
producer emits v1
consumer reads v1
consumer ignores additive v1 fields
consumer rejects malformed v1
consumer upcasts supported legacy form
producer never emits deprecated form after cutoff
```

Запускать весь декартов product версий не нужно. Достаточно:

- oldest supported;
- latest stable;
- next pre-release;
- ecosystem pinned set.


## Документация решений

Текущие design notes нужно сохранить, но перевести ключевые решения в ADR:

```text
0001-split-monorepo.md
0002-introduce-contracts-repository.md
0003-single-runtime-owner.md
0004-plugin-discovery.md
0005-event-envelope.md
0006-config-precedence.md
0007-artifact-store.md
0008-ecosystem-lock.md
0009-release-compatibility.md
0010-supply-chain-verification.md
```

ADR хранит решение, контекст, alternatives и последствия, а при изменении старое решение не удаляется, а supersede-ится новым. `adr-tools` поддерживает нумерованные Markdown ADR и явное superseding предыдущего решения.[^1_22]

Для архитектурной карты я бы добавил Structurizr DSL/C4. Его преимущество здесь в том, что model, diagrams, Markdown docs и ADR могут храниться как текст в Git, а это создаёт удобный источник контекста для coding agents.[^1_23][^1_24]

## Архитектурные проверки

Главные утверждения плана должны стать executable fitness functions.

Примеры:

```text
orchestrator-core must not import provider SDKs
engine-core must not import Temporal
workflow definitions must not perform filesystem/network I/O
doctor probes must not mutate state
contracts must not import implementations
plugins must declare manifests
all schemas must have stable IDs
events must contain run_id, attempt and owner_epoch
secrets must not serialize into events
presets must pass generated-project smoke test
```

Реализовать можно комбинацией:

- import graph tests;
- forbidden dependencies;
- schema lint;
- static AST checks;
- wheel-content assertions;
- subprocess smoke tests;
- event property tests.

Это важнее документа «не должно владеть»: документ устареет, а проверка остановит PR.

## Миграционная стратегия

Я бы изменил порядок extraction.

### Этап ноль

До переноса кода:

- Зафиксировать component ownership table.
- Создать ADR.
- Создать contract schemas.
- Собрать dependency/import graph.
- Зафиксировать golden CLI fixtures.
- Зафиксировать event fixtures.
- Написать architecture fitness tests.
- Определить rollback criteria.
- Создать reusable CI.


### Этап один

Создать `skm-contracts`:

- schemas;
- generated/handwritten Python models;
- canonical serialization;
- digests;
- error taxonomy;
- compatibility tests;
- schema registry layout.

Все существующие компоненты в монорепозитории сначала должны перейти на эти контракты.

### Этап два

Извлечь наиболее leaf-like компоненты:

1. `skm-skills`;
2. `skm-provider-integrations`;
3. `skm-doctor`.

Но каждый сначала подключается обратно в монорепозиторий как установленный wheel. Не через editable path в итоговой CI-проверке.

### Этап три

Извлечь `swissknife-engine`:

- local execution;
- state reducer;
- artifact port;
- subprocess/container backends;
- event protocol;
- cancellation/resume semantics.


### Этап четыре

Извлечь `skm-orchestrator` как pure plan compiler. Runtime adapters выделить отдельно от core.

### Этап пять

Извлечь `skm-workflow-runtime`, причём workflow definitions должны использовать только contracts и activity interfaces. Provider SDKs подключаются внутри activities/adapters.

### Этап шесть

Извлечь `skm-presets` и оставить его consumer-driven: он не должен становиться местом для shared runtime logic.

### Этап семь

Создать `skm-ecosystem`:

- pinned compatibility profile;
- full-stack tests;
- umbrella CLI;
- examples;
- docs;
- installation profiles;
- release catalog.


## Strangler вместо snapshot

Папка `integrations/sources/<component>/` с frozen snapshots полезна только как временный migration instrument. Если сохранить её надолго, она станет вторым источником истины.

Безопаснее:

```text
старый import/CLI
    -> compatibility facade
        -> установленный standalone package
```

Переход каждого компонента:

1. Extract package.
2. Опубликовать pre-release.
3. Подключить wheel в старый monorepo.
4. Прогнать golden tests.
5. Запустить shadow mode.
6. Сравнить планы, события и результаты.
7. Переключить default.
8. Сохранить legacy adapter на один compatibility window.
9. Удалить старую реализацию.
10. Оставить migration note и tag.

Для execution components shadow mode не должен выполнять реальные side effects дважды. Сравнивать можно compiled plans или использовать fake effect backend.

## Release train

Полностью независимые releases удобны, но пользователю нужен ответ на вопрос: «какой набор версий гарантированно работает вместе?».

Предлагаю два уровня:

### Independent releases

Каждый repo выпускается самостоятельно по SemVer.

### Ecosystem releases

Периодически публикуется:

```yaml
ecosystem: 2026.10
contracts: 1.6.0
skills: 2.3.1
doctor: 1.4.0
providers: 3.0.2
engine: 2.5.0
orchestrator: 1.9.0
workflow: 1.3.0
presets: 2.1.0
```

Ecosystem release означает:

- набор протестирован end-to-end;
- lock подписан;
- известные ограничения опубликованы;
- upgrade path проверен;
- поддерживается определённое время.

Это не требует синхронного изменения версий всех компонентов.

## Fresh ideas

### Capability graph

Вместо плоского списка capabilities создать граф:

```text
preset.codex-review
  requires role.resolve
  requires execution.durable
  requires provider.openai.responses
  requires effect.github.review
```

Resolver объясняет не только «не поддерживается», но и полную цепочку:

```text
preset unavailable
because execution.durable unavailable
because temporal server unreachable
because TLS certificate expired
```


### Execution explain

Для любого run:

```bash
skm run explain run_123
```

Результат должен показывать:

- почему выбран runtime;
- почему выбран provider/model;
- какие policies сработали;
- какие capabilities использованы;
- какие настройки победили по precedence;
- какие версии components участвовали;
- какие fallbacks были запрещены;
- какие approvals потребовались.


### Dry-run с proof

`prepare --dry-run` должен возвращать не просто plan, а explanation/proof bundle:

```text
input digest
config digest
policy digest
capability snapshot
resolver decisions
plan digest
warnings
refusals
```


### Policy packs

Policies лучше оформить как versioned artifacts:

```text
policy.safe-local
policy.no-external-data
policy.github-review
policy.production
```

Они должны иметь manifest, schema, digest и тестовые cases. Policy evaluation возвращает структурированное решение, а не boolean.

### Profile bundles

Пользовательские сборки:

```text
profile.local
profile.claude-only
profile.codex
profile.temporal
profile.team
profile.enterprise
```

Profile указывает components, plugins, policies и config overlays, а resolver создаёт lock.

### Conformance kit

`skm-contracts` должен поставлять готовый test kit:

```bash
skm-conformance provider ./my-plugin
skm-conformance engine ./my-engine
skm-conformance skill-source ./my-source
```

Это сильно упростит появление сторонних extensions.

### Compatibility service

Позднее можно публиковать machine-readable catalog:

```text
https://compat.swissknifeman.dev/v1/catalog.json
```

CLI сможет проверять:

- известные несовместимости;
- security advisories;
- deprecated components;
- рекомендуемый ecosystem release;
- наличие новых schema migrations.

Каталог должен быть кэшируемым и необязательным: offline execution не должен зависеть от доступности сервиса.

## Что изменить немедленно

Я бы добавил в текущий plan отдельные обязательные пункты:

- [ ] Создать `skm-contracts` как самостоятельный repository/package.
- [ ] Создать `skm-ecosystem` как integration repository.
- [ ] Устранить противоречие `orchestrator -> SkillRouter`.
- [ ] Уточнить владельца subprocess execution.
- [ ] Уточнить границу workflow runtime и provider integrations.
- [ ] Формализовать single runtime owner.
- [ ] Добавить lease, owner epoch и fencing.
- [ ] Добавить command idempotency model.
- [ ] Добавить artifact store contract.
- [ ] Добавить plugin manifest.
- [ ] Добавить Python entry-point groups.
- [ ] Добавить out-of-process handshake.
- [ ] Разделить package, schema, protocol и capability versions.
- [ ] Добавить config provenance и `config explain`.
- [ ] Добавить `skm.lock`.
- [ ] Добавить ecosystem release catalog.
- [ ] Добавить schema compatibility CI.
- [ ] Тестировать установленный wheel вне checkout.
- [ ] Добавить architecture fitness tests.
- [ ] Добавить shadow migration.
- [ ] Убрать долгоживущие source snapshots.
- [ ] Добавить SBOM, provenance и signatures.
- [ ] Ввести ADR lifecycle.
- [ ] Добавить C4/Structurizr model.
- [ ] Ввести component-owned doctor checks.
- [ ] Добавить structured effect requests/receipts.
- [ ] Формализовать secret references и data classification.
- [ ] Добавить conformance test kit.
- [ ] Сделать umbrella CLI только composition layer.
- [ ] Опубликовать reference profiles и full-stack examples.

Самое важное решение перед началом работ: **разделять нужно не исходники, а ответственность, протоколы и release lifecycle**. Если сначала появятся `skm-contracts`, plugin model, immutable plan, ecosystem lock и executable boundary tests, физический split станет почти механическим; если начать с репозиториев, эти же вопросы придётся решать уже через несовместимые релизы и migration debt.

<span style="display:none">[^1_25][^1_26][^1_27][^1_28][^1_29][^1_30][^1_31][^1_32][^1_33][^1_34][^1_35][^1_36][^1_37][^1_38][^1_39][^1_40][^1_41][^1_42][^1_43][^1_44][^1_45][^1_46][^1_47][^1_48][^1_49][^1_50][^1_51][^1_52][^1_53][^1_54][^1_55][^1_56][^1_57][^1_58][^1_59][^1_60][^1_61][^1_62][^1_63][^1_64][^1_65][^1_66][^1_67][^1_68][^1_69][^1_70][^1_71][^1_72][^1_73][^1_74][^1_75][^1_76][^1_77][^1_78][^1_79][^1_80][^1_81][^1_82][^1_83][^1_84][^1_85][^1_86][^1_87][^1_88][^1_89][^1_90]</span>

<div align="center">⁂</div>

[^1_1]: https://json-schema.org/understanding-json-schema/basics?highlight=version

[^1_2]: https://opentelemetry.io/docs/collector/

[^1_3]: https://opentelemetry.io/docs/collector/configuration/

[^1_4]: https://packaging.python.org/en/latest/specifications/entry-points/

[^1_5]: https://github.com/hashicorp/go-plugin/blob/main/docs/internals.md

[^1_6]: https://github.com/cloudevents/spec

[^1_7]: https://github.com/cloudevents/spec/blob/main/cloudevents/spec.md

[^1_8]: https://spec.openapis.org/overlay/latest.html

[^1_9]: https://spec.openapis.org/overlay/v1.1.0.html

[^1_10]: https://opentelemetry.io/docs/specs/otel/telemetry-stability/

[^1_11]: https://opentelemetry.io/docs/specs/semconv/general/semantic-convention-groups/

[^1_12]: https://opentelemetry.io/docs/specs/semconv/

[^1_13]: https://opentelemetry.io/docs/concepts/semantic-conventions/

[^1_14]: https://github.com/CycloneDX

[^1_15]: https://cyclonedx.org/capabilities/sbom/

[^1_16]: https://slsa.dev/spec/v1.2/build-requirements

[^1_17]: https://slsa.dev/spec/v1.2/build-provenance

[^1_18]: https://docs.sigstore.dev/cosign/signing/overview/

[^1_19]: https://docs.sigstore.dev/about/overview/

[^1_20]: https://docs.dissect.tools/en/latest/contributing/tooling.html

[^1_21]: https://packaging-guide.openastronomy.org/en/latest/tox.html

[^1_22]: https://github.com/npryce/adr-tools

[^1_23]: https://docs.structurizr.com/dsl

[^1_24]: https://docs.structurizr.com/as-code

[^1_25]: https://opentelemetry.io/docs/collector/components/

[^1_26]: https://opentelemetry.io/docs/collector/components/extension/

[^1_27]: https://opentelemetry.io/docs/collector/components/connector/

[^1_28]: https://opentelemetry.io/docs/collector/extend/custom-component/connector/

[^1_29]: https://backstage.io/docs/frontend-system/architecture/plugins/

[^1_30]: https://backstage.io/docs/backend-system/architecture/modules/

[^1_31]: https://docs.redhat.com/en/documentation/red_hat_build_of_opentelemetry/3.8/html-single/configuring_the_collector/index

[^1_32]: https://backstage.io/docs/backend-system/architecture/extension-points/

[^1_33]: https://docs.redhat.com/en/documentation/red_hat_build_of_opentelemetry/3.11/html/configuring_the_collector/otel-configuration-of-otel-intro_otel-configuration-of-otel-intro

[^1_34]: https://backstage.io/docs/overview/architecture-overview/

[^1_35]: https://docs.redhat.com/en/documentation/openshift_container_platform/4.12/html/red_hat_build_of_opentelemetry/configuring-the-collector

[^1_36]: https://opentelemetry.io/docs/collector/architecture/

[^1_37]: https://opentelemetry.io/docs/specs/otel/schemas/

[^1_38]: https://docs.cloud.google.com/eventarc/docs/cloudevents

[^1_39]: https://docsopensource.github.io/docs/CNCF Projects/5.21_CloudEvents

[^1_40]: https://github.com/epc/cloudevents-spec

[^1_41]: https://github.com/api-evangelist/events/blob/main/apis.yml

[^1_42]: https://github.com/open-telemetry/opentelemetry-specification/blob/main/oteps/4815-semantic-conventions-schema-v2.md

[^1_43]: https://opentelemetry.io/docs/specs/semconv/how-to-write-conventions/

[^1_44]: https://opentelemetry.io/docs/specs/otel/semantic-conventions/

[^1_45]: https://spec.openapis.org/overlay/

[^1_46]: https://www.openapis.org/blog

[^1_47]: https://spdx.dev/wp-content/uploads/sites/31/2024/12/SPDX-3.0.1-1.pdf

[^1_48]: https://github.com/json-schema-org/json-schema-spec/blob/main/specs/jsonschema-core.md

[^1_49]: https://docs.json-everything.net/schema/basics/

[^1_50]: https://one.sourcemeta.com/guide/evolution/

[^1_51]: https://www.openapis.org/blog/2026/02/10/openapi-initiative-newsletter-february-2026

[^1_52]: https://learn.openapis.org/overlay/

[^1_53]: https://www.openapis.org/blog/2026/06/09/openapi-initiative-newsletter-june-2026

[^1_54]: https://spec.openapis.org/overlay/v1.0.0.html

[^1_55]: https://spec.openapis.org/

[^1_56]: https://spdx.github.io/spdx-spec/v3.0.1/model/Software/Classes/Sbom/

[^1_57]: https://slsa.dev/spec/v0.2/provenance

[^1_58]: https://github.com/sigstore/cosign

[^1_59]: https://slsa.dev/spec/v1.2-rc1/build-provenance

[^1_60]: https://github.com/sigstore/cosign/blob/main/README.md

[^1_61]: https://docs.sigstore.dev/cosign/signing/other_types/

[^1_62]: https://docs.sigstore.dev/cosign/signing/signing_with_containers/

[^1_63]: https://docs.sigstore.dev/quickstart/quickstart-cosign/

[^1_64]: https://docs.sigstore.dev/

[^1_65]: https://docs.sigstore.dev/cosign/verifying/verify/

[^1_66]: https://docs.structurizr.com/dsl/adrs

[^1_67]: https://docs.structurizr.com/ui/decisions/

[^1_68]: https://docs.structurizr.com/server/decisions

[^1_69]: https://adr.github.io/adr-tooling/

[^1_70]: https://github.com/adr

[^1_71]: https://mitlibraries.github.io/guides/misc/adr.html

[^1_72]: https://ceur-ws.org/Vol-2072/paper9.pdf

[^1_73]: https://embeddedartistry.com/blog/2018/04/05/documenting-architectural-decisions-within-our-repositories/

[^1_74]: https://www.structurizr.com/embed/39459

[^1_75]: https://docs.structurizr.com/lite

[^1_76]: https://docs.structurizr.com/dsl/parser

[^1_77]: https://adr.github.io/

[^1_78]: https://docs.dissect.tools/en/stable/contributing/tooling.html

[^1_79]: https://hatch.readthedocs.io/en/latest/articles/users/tutorials/01-getting-started/03-install-package/

[^1_80]: https://hatch.pypa.io/1.16/environment/

[^1_81]: https://pypi.org/project/tox-wheel/

[^1_82]: https://github.com/fastmachinelearning/qonnx/blob/main/tox.ini

[^1_83]: https://hatch.pypa.io/1.12/environment/

[^1_84]: https://github.com/biopragmatics/debio/blob/main/tox.ini

[^1_85]: https://hatch.pypa.io/1.5/environment/

[^1_86]: https://github.com/pypa/hatch/blob/master/docs/config/environment/advanced.md

[^1_87]: https://www.jetbrains.com/help/pycharm/hatch.html

[^1_88]: https://hatch.readthedocs.io/en/stable/articles/users/tutorials/01-getting-started/03-install-package/

[^1_89]: https://github.com/tox-dev/tox/blob/main/pyproject.toml

[^1_90]: https://www.explainx.ai/blog/what-are-monorepos-101

