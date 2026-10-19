Полный аудит привязан к коммиту [`81a4507`](https://github.com/academici/swissknifeman/commit/81a4507e6abeec7c92b042043a460ba11316863a) от 19 октября 2026 года. Архитектурная основа репозитория сильная, но для режима «работает как часы» нужны: capability-based routing вместо жёстких классов моделей, provider/model-specific подготовка контекста, durable-исполнение с идемпотентностью, адаптивные бюджеты и полноценная наблюдаемость через GUI.

Сейчас не удалось прикрепить отдельный скачиваемый файл. Ниже приведён готовый Markdown-документ, который можно сохранить как `swissknifeman-audit.md`.

***

# Аудит стабильности и оркестрации Swiss Knife Man

**Репозиторий:** `academici/swissknifeman`  
**Зафиксированная ревизия:** `81a4507e6abeec7c92b042043a460ba11316863a`  
**Дата анализа:** 19 октября 2026 года  
**Основной фокус:** `orch`, модельный routing, изоляция контекста, конфигурация инструкций, GUI control plane, multi-repository architecture, бюджеты и практики AWS Labs CLI Agent Orchestrator.

## Краткий вердикт

Swiss Knife Man уже располагает большей частью правильных архитектурных примитивов:

- детерминированным conductor;
- закрытыми контрактами результатов;
- ролями scout, executor, reviewer, triager, researcher и advisor;
- layered configuration;
- prompt manifest с происхождением и размером каждого блока;
- независимым review provider;
- resume, журналом запуска и frozen-снимками инструкций;
- декларативным GUI contribution protocol;
- изоляцией плагинов и typed command execution.

При этом система пока не полностью реализует желаемую схему «любая экономная модель может быть руководителем, а сильные модели получают подготовленное именно под них задание». Главные ограничения находятся не в базовой архитектуре, а в текущих контрактах routing, provider coverage и prompt adaptation.

## Главные выводы

| Приоритет | Область | Текущее состояние | Необходимое изменение |
|---|---|---|---|
| P0 | Model routing | Три статических класса: `economy`, `implementation`, `frontier` | Capability-based routing с ценой, latency, context window и role fitness |
| P0 | Provider parity | Grok отсутствует для ряда служебных ролей | Полная матрица role × provider × transport × capabilities |
| P0 | Долгие задачи | Есть resume и журналы, но отсутствует единая durable task abstraction | Server-owned execution, idempotency key, lease, checkpoint и result acknowledgement |
| P0 | Контекст | Хорошая блочная сборка, но нет model-specific prompt profile | Ввести `prompt-profile/v1` и адаптеры Claude/Codex/Grok |
| P0 | Бюджеты | Многие лимиты отключены или являются сигналами | Soft/hard budgets с автоматическим shard/replan вместо аварийной остановки |
| P1 | Конфиги | Есть machine/project stubs | Добавить workspace/package/model-family/task overlays |
| P1 | GUI | Сильная plugin architecture | Добавить orchestration observability, routing simulator и prompt inspector |
| P1 | Multi-repo | Поддерживается через unit registry и внешние extensions | Ввести подписанные catalogs и совместимость contributions между репозиториями |
| P1 | Reliability | Хорошие локальные механизмы | Перенести reconciliation, watchdog и durable workflow практики CAO |
| P2 | Оптимизация | Routing статичен | Shadow routing, сбор telemetry и последующее автоматическое решение |

## Текущая архитектура

Репозиторий разделён на самостоятельные пакеты `aicore`, `analyst`, `brain`, `gui`, `harness`, `maind`, `orch`, `planner`, `skiller` и `workspace`; интеграция выполняется через bridges и контракты, а не через прямые зависимости пакетов.

`orch` владеет execution-контрактами, role manifests, Engine Port, binding capabilities, model catalog integration, run-policy packs и conductor. При этом ядро ограничивает свои импорты стандартной библиотекой, `orch` и `aicore`, а внешние партнёры подключаются через process/bridge boundaries.

Это правильная база для разделения Swiss Knife Man по отдельным репозиториям. Контракты уже играют роль устойчивого API между частями системы.

## Детерминированный conductor

В текущей модели conductor не является LLM. Он запускает специализированные роли и принимает решения только по exit codes, закрытым результатам ролей и run options.

Это важное и правильное решение. Экономная модель не должна заменять state machine conductor и принимать решения о переходах, retry, commit или регистрации результата.

Рекомендуемая схема:

```text
User / Planner
      |
      v
Economy planner or context architect
      |
      v
Frozen execution graph
      |
      v
Deterministic conductor
      |
      +--> Context scout
      +--> Executor
      +--> Deterministic checks
      +--> Reviewer
      +--> Triager
      +--> Registrar
```

Экономная модель должна выполнять только одну из следующих функций:

- построить или уточнить execution graph;
- подобрать исполнителя;
- сформировать минимальный context bundle;
- классифицировать ошибку, если классификация не может быть выполнена детерминированно;
- подготовить recommendation для conductor.

Она не должна:

- быть источником истины о состоянии run;
- самостоятельно считать задачу завершённой;
- обходить acceptance checks;
- менять write scope;
- выполнять retry без записанного transition;
- подменять deterministic routing.

## Routing моделей

### Текущее положение

Model catalog уже разделяет модели на классы `economy`, `implementation` и `frontier`, но это статическое сопоставление provider → class → model.

На анализируемой ревизии:

| Provider | Economy | Implementation | Frontier |
|---|---|---|---|
| Claude Code | `haiku` | `sonnet` | `opus` |
| Codex | `gpt-5.6-luna` | `gpt-6-sol` | `gpt-6-astra` |
| Grok | `grok-4.5` | `grok-4.6` | `grok-4.7` |

Следовательно, указанные в постановке `Haiku 5.5`, `GPT-6 Luna` и `Grok 4.6` как универсальные economy conductors пока не соответствуют текущей конфигурации репозитория. В особенности `grok-4.6` сейчас относится к implementation, а не economy.

Сами названия моделей не должны становиться частью архитектурного контракта. Они быстро устаревают и могут различаться между CLI, аккаунтами и регионами.

### Необходимая модель

Следует заменить основной выбор по `model_class` на выбор по capabilities.

```json
{
  "$schema": "urn:swissknifeman:aicore:model-capability:v2",
  "provider": "codex",
  "model": "gpt-6-luna",
  "capabilities": {
    "planning": 0.82,
    "context_condensing": 0.91,
    "implementation": 0.54,
    "review": 0.61,
    "structured_output": 0.96,
    "tool_orchestration": 0.88
  },
  "constraints": {
    "context_tokens": 200000,
    "supports_json_schema": true,
    "supports_resume": false,
    "supports_read_only": true,
    "supports_workspace_write": true
  },
  "economics": {
    "cost_tier": "low",
    "latency_tier": "low"
  },
  "status": "verified",
  "verified_at": "2026-10-19"
}
```

Routing должен принимать решение на основании:

```text
required capabilities
+ minimum quality
+ context size
+ write authority
+ provider health
+ budget pressure
+ independence requirements
+ historical success rate
```

Пример route request:

```json
{
  "role": "context-architect",
  "requires": {
    "context_condensing": 0.8,
    "structured_output": 0.9,
    "tool_orchestration": 0.7
  },
  "constraints": {
    "write_authority": "none",
    "max_cost_tier": "low",
    "provider_exclude": ["provider-of-primary-executor"]
  }
}
```

Классы `economy`, `implementation` и `frontier` можно сохранить как удобные presets, но не как фундаментальный механизм.

## Пробелы provider coverage

Launch catalog несимметричен. Claude Code и Codex поддерживаются почти во всех ролях, тогда как Grok присутствует в `executor`, `bounded-implementer`, `reviewer` и `report-fixer`, но отсутствует в `scout`, `triager`, `registrar`, `researcher` и `advisor`.

Это противоречит цели «каждый provider может руководить». Даже если Grok способен выполнить роль, conductor не сможет выбрать его без launch definition.

Необходимо формализовать следующую матрицу:

| Role | Claude | Codex | Grok | Требование |
|---|---:|---:|---:|---|
| Context scout | Да | Да | Нет | P0 |
| Context architect | Нет отдельной роли | Нет | Нет | P0 |
| Executor | Да | Да | Да | Готово |
| Bounded implementer | Да | Да | Да | Готово |
| Reviewer | Да | Да | Да | Готово |
| Triager | Да | Да | Нет | P0 |
| Registrar | Да | Да | Нет | P1 |
| Researcher | Да | Нет | Нет | P1 |
| Advisor | Да | Нет | Нет | P1 |
| Report fixer | Да | Да | Да | Готово |

Для каждой комбинации следует проверять не только существование команды, но и:

- structured output;
- read-only enforcement;
- write sandbox;
- tool allowlist;
- idle detection;
- cancellation;
- resumability;
- context transport;
- maximum output;
- auth failure classification;
- rate-limit classification.

## Контекст и изоляция

### Что реализовано хорошо

Prompt builder уже работает с отдельными блоками: role text, execution input, repository rules, skills, context map, verification, run rules, correction package, review candidate и result contract.

Для каждого prompt формируется manifest, включающий:

- тип блока;
- происхождение;
- SHA-256;
- оценку токенов;
- исключённые элементы;
- provider, model и effort;
- digest всего prompt.

Исполнитель не получает исходную plan command line и полный внутренний контекст conductor. Это хорошая основа принципа need-to-know.

Scout context передаётся исполнителю как leads, а не как факты. Expected paths не расширяют write set. Research results также не считаются инструкциями и не расширяют scope.

### Чего не хватает

Текущий prompt builder в основном provider-neutral. Route сохраняется в manifest, но вид prompt не меняется систематически по provider или model family.

Необходим контракт `prompt-profile/v1`:

```yaml
profile_id: executor.codex.gpt-6-sol
matches:
  role: executor
  provider: codex
  model_family: gpt-6-sol
format:
  task_first: true
  repeat_result_contract_at_end: true
  prefer_xml_sections: false
  prefer_json_constraints: true
  max_instruction_depth: 3
context:
  repository_rules: summarized
  scout_map: full
  acceptance_checks: references
  previous_attempts: last_only
execution:
  require_explicit_plan: true
  require_checklist: false
  discourage_reexploration: true
```

Аналогично:

```yaml
profile_id: executor.claude.sonnet
matches:
  role: executor
  provider: claude-code
  model_family: sonnet
format:
  task_first: false
  repeat_result_contract_at_end: true
context:
  repository_rules: full
  scout_map: full
execution:
  prefer_native_file_tools: true
  forbid_file_edits_through_shell: true
```

При этом provider profile не должен иметь возможность:

- расширять tools;
- расширять write scope;
- удалять acceptance checks;
- менять result contract;
- понижать security requirements.

Он может только менять представление уже разрешённого контента.

## Context Bundle v2

Рекомендуемый context bundle:

```json
{
  "$schema": "urn:swissknifeman:orch:context-bundle:v2",
  "task": {
    "goal": "...",
    "acceptance": ["..."],
    "write_set": ["packages/orch/**"]
  },
  "blocks": [
    {
      "id": "repo-rules",
      "kind": "instruction",
      "source": "AGENTS.md",
      "source_revision": "sha256:...",
      "selection": "required",
      "tokens": 1450,
      "sensitivity": "internal",
      "content_ref": "artifact://..."
    },
    {
      "id": "related-api",
      "kind": "code",
      "source": "packages/orch/lib/orch/catalog.py",
      "selection": "semantic-match",
      "reason": "defines model class resolution",
      "tokens": 2200,
      "content_ref": "artifact://..."
    }
  ],
  "excluded": [
    {
      "source": "packages/gui/**",
      "reason": "outside task dependency closure"
    }
  ],
  "budget": {
    "soft_tokens": 32000,
    "hard_tokens": 48000
  }
}
```

Ключевые принципы:

- сначала dependency closure, затем semantic retrieval;
- полные файлы только при необходимости;
- summaries должны ссылаться на исходный digest;
- исполнитель может запросить дополнительный блок;
- каждый запрос расширения контекста записывается;
- неизменные большие блоки передаются через artifact references;
- context bundle замораживается на попытку исполнения;
- повторная попытка получает diff контекста, а не полную историю run.

## Конфигурация инструкций

### Что уже есть

Общая конфигурация накладывается в порядке:

```text
schema defaults
→ machine
→ project
→ environment
→ invocation config
→ flags
```

Опасные параметры, такие как `profiles.dirs` и команды ролей, нельзя задавать из управляемого проектом слоя.

Дополнительные role instructions поддерживают machine и project layers. Они разрешаются один раз при старте, сохраняются в `instructions.json` и повторно используются при resume, поэтому изменение файла во время run не меняет поведение уже начатого запуска.

Это сильное решение с точки зрения воспроизводимости.

### Необходимая иерархия

```text
canonical role contract              immutable
organization security policy         may only restrict
machine policy                       may only restrict
workspace policy                     common multi-repo rules
repository policy                    project conventions
package policy                       package-specific conventions
role profile                         executor/reviewer/scout
provider profile                     Claude/Codex/Grok formatting
model-family profile                 Sonnet/Sol/Astra/etc.
run policy                           frozen run settings
item override                        narrow task-specific addition
```

Правила merge:

1. Security, scope и tools объединяются по принципу наиболее строгого значения.
2. Acceptance checks не переопределяются инструкциями.
3. Package policy применяется только при попадании write set в package root.
4. Model profile влияет только на presentation.
5. Любой override должен иметь provenance и digest.
6. Неизвестный или конфликтующий override приводит к prepare-time отказу.
7. В GUI должен быть режим «effective instructions» с объяснением каждого значения.

Пример:

```toml
[orch.instructions.package."packages/orch"]
review = ["strict-contract-review", "provider-parity"]
executor = ["preserve-closed-schemas"]

[orch.instructions.model_family."codex/gpt-6-sol"]
executor = ["task-first", "explicit-output-contract"]

[orch.instructions.model_family."claude-code/sonnet"]
executor = ["native-file-tools", "no-shell-file-edit"]
```

## Бюджеты и большие задачи

Полная run policy устанавливает `brief_max_bytes = 65536`, `packer_input_max_bytes = 262144`, `stage_tokens_max = 0` и общий retry budget 2.

На уровне conductor `tokens_max` также фактически служит beacon, а wall-clock timeout может быть отключён; idle timeout применяется как защита от зависших процессов.

Нулевой hard token limit позволяет не обрывать большую задачу, но создаёт риск бесконтрольного роста стоимости и контекста.

### Рекомендуемая схема

Бюджет не должен быть единственным числом.

```yaml
budget:
  money:
    soft: 10
    hard: 50
  tokens:
    context_soft: 40000
    context_hard: 80000
    run_soft: 500000
    run_hard: 2000000
  time:
    stage_soft_s: 1800
    stage_hard_s: 7200
    idle_s: 900
  retries:
    transient_per_stage: 3
    correction_per_item: 2
    total: 12
```

Поведение на soft limit:

- остановить speculative review;
- использовать economy model для condense;
- не передавать полную историю;
- повысить reuse context artifacts;
- уменьшить review scope только до изменённых областей;
- предложить shard.

Поведение на hard limit:

- сохранить checkpoint;
- вернуть `needs_replan`, а не generic failure;
- разбить задачу на подзадачи;
- продолжить новым run с parent reference;
- не терять уже подтверждённые результаты.

Большая задача должна выходить за бюджет через управляемую декомпозицию, а не через бесконечное продолжение одного prompt.

## Durable-исполнение

Архитектурная документация `orch` по-прежнему называет durable timers, workflow replay, compensation и multi-day execution нецелевыми возможностями Engine Port. Одновременно conductor уже предоставляет run journal, resume и frozen state.

Следует явно развести:

```text
Orch Conductor:
  durable item execution
  checkpoints
  resume
  result reconciliation

External Workflow Runtime:
  multi-day scheduling
  timers
  compensation
  cross-machine execution
  business workflow semantics
```

Для каждой стадии нужен durable record:

```json
{
  "run_id": "RUN123",
  "item_id": "P4.2",
  "stage_id": "executor-1",
  "attempt": 2,
  "idempotency_key": "RUN123:P4.2:executor:2",
  "state": "running",
  "lease_owner": "host-a:pid-1234",
  "lease_expires_at": "...",
  "input_digest": "sha256:...",
  "prompt_digest": "sha256:...",
  "workspace_digest_before": "sha256:...",
  "provider_operation_id": "...",
  "last_heartbeat_at": "...",
  "checkpoint_ref": "artifact://...",
  "result_ref": null
}
```

State machine:

```text
prepared
→ queued
→ leased
→ starting
→ running
→ result_persisting
→ succeeded

running
→ retry_wait
→ queued

running
→ unknown_outcome
→ reconciling
→ succeeded | failed | owner_required
```

Критически важно: потеря HTTP/MCP-соединения не должна отменять работу исполнителя.

## Практики AWS CAO

AWS CLI Agent Orchestrator отделяет provider adapter от terminal backend: backend владеет жизненным циклом терминала, а provider adapter — запуском CLI, status detection, input handling и provider-specific exit behavior. [github](https://github.com/awslabs/cli-agent-orchestrator/blob/main/CODEBASE.md)

Эту границу следует перенести в SKM как отдельный `ProviderRuntime`:

```python
class ProviderRuntime(Protocol):
    def prepare_launch(...)
    def classify_error(...)
    def decode_progress(...)
    def decode_result(...)
    def probe_health(...)
    def cancel(...)
    def reconcile(...)
```

### Status не равен истине

CAO прямо предупреждает, что статус, выведенный из terminal screen, может не соответствовать действительности и должен подтверждаться чтением фактического output. [raw.githubusercontent](https://raw.githubusercontent.com/awslabs/cli-agent-orchestrator/main/skills/cao-session-management/SKILL.md)

Для SKM это означает:

- `PROCESSING` нельзя определять только по наличию процесса;
- `COMPLETED` требует валидного closed result;
- `IDLE` не означает успешное завершение;
- disappearance процесса без результата — `unknown_outcome`;
- provider status всегда является наблюдением, а не authoritative state.

### Reconciliation loop

CAO имеет несколько путей inbox delivery: immediate attempt, event/watchdog delivery и медленный reconciliation sweep для сообщений, которые могли остаться `PENDING` навсегда. [github](https://github.com/awslabs/cli-agent-orchestrator/blob/main/docs/inbox-delivery.md)

Этот паттерн следует распространить на:

- незавершённые stages;
- потерянные completion events;
- незафиксированные provider results;
- незакрытые worktree leases;
- pending registrar operations;
- GUI runs, оставшиеся `running` после рестарта.

### Durable async handoff

В CAO сформулирована правильная модель долгой операции:

1. сохранить queued record и idempotency key;
2. создать terminal и отдельно записать terminal ID;
3. сразу вернуть operation ID;
4. независимо наблюдать исполнение;
5. сохранить результат до удаления terminal;
6. отправить at-least-once completion hint;
7. отдельно получить и подтвердить authoritative result;
8. хранить неподтверждённый результат до TTL. [github](https://github.com/awslabs/cli-agent-orchestrator/issues/447)

Эта схема практически полностью подходит для stage execution в SKM.

### Frozen workflow

Актуальные релизы CAO включают durable journal, replay, frozen execution manifest и plan approval. [github](https://github.com/awslabs/cli-agent-orchestrator/releases)

Для SKM следует замораживать:

- execution input;
- policy;
- resolved models;
- prompt profiles;
- role stubs;
- capabilities;
- launch argv template;
- environment allowlist;
- context manifests;
- plugin digests.

### Shadow routing

CAO поддерживает режим shadow, при котором decider записывает предполагаемый выбор, но не меняет фактический launch. [github](https://github.com/awslabs/cli-agent-orchestrator/blob/main/docs/decisions.md)

Перед автоматическим model routing в SKM необходимо минимум 2–4 недели shadow-режима:

```text
actual route: claude-code/sonnet
shadow route: codex/gpt-6-sol
reason: lower expected cost, sufficient implementation score
actual outcome: success
shadow evaluated outcome: unavailable
```

Сначала должна накапливаться telemetry, затем включаться advisory mode, и только после этого automatic mode.

## GUI как hub

### Сильные стороны

GUI уже построен как local control plane с единственным Python authority, typed requests, bridges, plugin catalog, isolation, quarantine и audit trail.

Contribution является декларативным `gui.json`; произвольный JavaScript contribution не исполняется. Пакет может добавить routes, widgets, queries, commands, forms, configuration sections и documentation.

Внешние extensions подключаются через aicore plugin configuration. После conformance check и enable их routes и widgets появляются без пересборки frontend.

Таким образом, желаемая схема «новый пакет регистрируется и появляется в общем GUI» уже в основном реализована. Более того, обязательная пересборка GUI не требуется, если пакет укладывается в существующие host views.

### Multi-repository mode

Для работы с пакетами в разных репозиториях необходимо добавить distribution layer:

```yaml
catalog:
  id: skm-official
  protocol: gui-catalog/v1
  sources:
    - repository: git@example.com:skm/orch.git
      revision: v1.4.0
      contribution: gui/gui.json
      digest: sha256:...
    - repository: git@example.com:skm/mind.git
      revision: v0.3.0
      contribution: gui/gui.json
      digest: sha256:...
```

Требования:

- immutable revision;
- digest verification;
- compatibility check до включения;
- атомарная установка;
- rollback;
- quarantine;
- отдельные grants;
- запрет транзитивного trust;
- отображение owner repository и revision в GUI.

### Нужные экраны

В GUI следует добавить:

- **Run timeline:** все transitions и duration.
- **Routing inspector:** почему выбрана модель.
- **Prompt inspector:** блоки, токены, provenance, excluded context.
- **Budget dashboard:** burn rate по стадии и provider.
- **Provider health:** auth, quota, rate limit, latency, recent failures.
- **Retry graph:** причина каждой повторной попытки.
- **Reconciliation queue:** операции с unknown outcome.
- **Policy simulator:** dry-run route без запуска.
- **Instruction explorer:** effective configuration для package/role/model.
- **Artifact browser:** context bundles, results, review findings.
- **Replay view:** восстановление state из журнала.
- **Plugin compatibility:** protocol, contracts, digest, grants и quarantine.

## GUI limitations

Contribution contract сознательно ограничивает интерфейс заранее известными host views: `resource-list`, `resource-detail`, `schema-form`, `metric-group`, `status-table`, `timeline`, `log-stream`, `dependency-graph`, `board` и другими.

Это обеспечивает безопасность, но новый пакет не сможет предоставить принципиально новый интерактивный UI без обновления host frontend.

Рекомендуется сохранить два уровня:

```text
Level 1: declarative trusted views
Level 2: sandboxed application contribution
```

Level 2 следует вводить только при реальной необходимости, через изолированный iframe/webview, CSP, typed message protocol и явные grants. Для большинства control-plane функций Level 1 достаточен.

## Тестовая стратегия

### Provider conformance

Каждый provider должен проходить одинаковый suite:

```text
launch
structured result
read-only enforcement
write-scope enforcement
timeout
idle timeout
cancel
auth failure
quota failure
rate limit
transport disconnect
invalid JSON result
oversized output
resume/reconcile
secret redaction
```

### Fault injection

Обязательные сценарии:

- процесс умер до записи result;
- result записан, но completion event потерян;
- journal append выполнен, projection update не выполнен;
- provider вернул повторный event;
- conductor перезапущен в середине commit;
- worktree изменён внешним процессом;
- диск заполнен при записи checkpoint;
- SQLite/database lock;
- plugin завис;
- GUI отключился во время stream;
- provider CLI обновился и изменил JSONL;
- модель исчезла между prepare и launch;
- budget превышен в середине стадии.

### Property tests

Особенно полезны свойства:

- повторный resume не дублирует side effect;
- replay журнала даёт тот же terminal state;
- model profile не расширяет permissions;
- project config не ослабляет machine policy;
- package instructions применяются только к своему package;
- два одинаковых frozen run manifests имеют одинаковый digest;
- ни один secret не попадает в prompt manifest или GUI event;
- unknown outcome никогда автоматически не превращается в success;
- повторная регистрация результата идемпотентна.

## План внедрения

### Этап 0: контракты

Срок: 1–2 недели.

- Зафиксировать distinction между deterministic conductor и LLM planner.
- Добавить `model-capability/v2`.
- Добавить `prompt-profile/v1`.
- Добавить `context-bundle/v2`.
- Описать durable stage state machine.
- Устранить противоречия документации по resume и durable execution.

### Этап 1: provider parity

Срок: 2–3 недели.

- Добавить Grok scout, triager и registrar.
- Добавить Codex/Grok researcher и advisor либо явно задокументировать refusal.
- Реализовать provider conformance suite.
- Добавить health probes.
- Ввести verified/unverified capability status.

### Этап 2: prompt adaptation

Срок: 2–3 недели.

- Разделить canonical role semantics и presentation profile.
- Добавить профили Claude Sonnet, Claude Opus, Codex Sol/Astra и Grok.
- Поддержать package-specific instructions.
- Добавить prompt dry-run и diff.
- Показывать итоговый prompt manifest в GUI.

### Этап 3: durability

Срок: 3–5 недель.

- Ввести idempotency keys.
- Разделить task execution и synchronous waiter.
- Добавить leases и heartbeats.
- Ввести result acknowledgement.
- Реализовать startup reconciliation.
- Добавить deterministic replay tests.

### Этап 4: adaptive budgets

Срок: 2–3 недели.

- Ввести soft/hard budgets.
- Добавить автоматический condense.
- Реализовать shard/replan transition.
- Ввести отдельные лимиты launch, readiness, execution, result persistence.
- Добавить circuit breaker по provider.

### Этап 5: GUI hub

Срок: 3–4 недели.

- Routing inspector.
- Prompt inspector.
- Budget dashboard.
- Provider health.
- Reconciliation queue.
- Instruction explorer.
- Multi-repository contribution catalog.

### Этап 6: smart routing

Срок: не менее 4 недель наблюдения.

- Shadow mode.
- Сбор success/cost/latency telemetry.
- Advisory mode.
- Canary automatic routing.
- Автоматический rollback при деградации.
- Запрет learning-based routing для security-sensitive задач без human gate.

## Критерии готовности

Систему можно считать отточенной, когда выполняются следующие условия:

- любой поддерживаемый provider может выполнять все заявленные роли либо prepare честно отказывает;
- выбор модели объясним и воспроизводим;
- executor получает только минимальный frozen context;
- provider/model profile меняет форму, но не полномочия;
- потеря соединения не теряет работу;
- повторный запуск не дублирует side effects;
- неизвестный outcome обязательно проходит reconciliation;
- большая задача автоматически дробится вместо аварийного завершения;
- GUI показывает состояние run без чтения внутренних файлов вручную;
- новый пакет из отдельного репозитория подключается декларативно;
- несовместимый plugin не нарушает работу остальных;
- все budgets, retries и overrides имеют provenance;
- run можно воспроизвести из frozen manifest и журнала;
- provider update обнаруживается conformance suite до production rollout.

## Итоговая рекомендация

Не следует превращать economy-модель в настоящий runtime conductor. Правильная архитектура — экономная модель проектирует или уточняет план, а детерминированный conductor исполняет замороженный граф и запускает сильные модели только на стадиях, где они действительно необходимы.

Наиболее важные ближайшие изменения:

1. `model-capability/v2` вместо жёсткой зависимости от `economy/implementation/frontier`.
2. Полная provider-role matrix, особенно для Grok.
3. `prompt-profile/v1` для Claude, Codex и Grok.
4. Durable async stage execution с idempotency и reconciliation.
5. Soft/hard budgets с shard/replan.
6. GUI routing/prompt/budget observability.
7. Shadow routing до включения автоматического выбора моделей.