# SKM GUI: архитектура, стек и план расширяемой desktop-платформы

## Краткий вывод

Оптимальная архитектура для первой версии — **локальное desktop-приложение на Tauri 2 с React/TypeScript UI и отдельным Python control plane**, который запускается как sidecar и остаётся единственным владельцем конфигурации, команд, планов, логов и плагинов. Тот же UI и тот же Python API следует изначально делать browser-capable, но удалённый multi-user режим не включать: это даёт гибридность без преждевременного усложнения аутентификацией, TLS, распределёнными блокировками и серверной эксплуатацией.

Главное архитектурное решение — **не превращать GUI в новый источник истины и не позволять frontend-плагинам напрямую выполнять Python или shell**. GUI должен быть проекцией существующих контрактов SKM: `unit.json`, JSON Schema, effective config с provenance, event journal, permission manifests и subprocess extension protocol. В репозитории уже существуют подходящие основания: пакетные `unit.json`, версионированные language-neutral схемы, `config-explain`, `permissions`, `extension`, plugin request/response, события и telemetry conventions.

Рекомендуемый стек:

| Слой | Выбор | Роль |
|---|---|---|
| Desktop shell | Tauri 2, Rust только для lifecycle/OS integration | Запуск и контроль Python sidecar, single-instance, tray, deep links, updater, системные диалоги |
| UI | React + TypeScript + Vite | Dashboard, проекты, конфиг, планы, плагины, команды, логи, документация |
| UI data | TanStack Query + typed API client | Server state, cache, отмена запросов, retry только для безопасных reads |
| Формы | Собственный schema renderer поверх JSON Schema 2020-12; готовая библиотека только как ускоритель MVP | Типизированное редактирование с provenance, layer selection и domain widgets |
| Backend | Python 3.11+; FastAPI/Starlette, Pydantic 2, asyncio/AnyIO | API, WebSocket events, schema validation, orchestration, adapters к текущим пакетам |
| Процессы | `asyncio.create_subprocess_exec`, отдельный supervisor, PTY как отдельная capability | Запуск CLI и плагинов без `shell=True`, cancellation, timeout, output streaming |
| Хранилище GUI | SQLite + миграции; JSONL/файлы для больших потоков логов | Индекс запусков, пользовательские layout/preferences, кэш; не планы и не основной config |
| Plugin transport | Текущий external extension protocol через stdio JSON messages | Изоляция Python-плагинов по процессам, timeouts, permissions, crash containment |
| Observability | Structured JSON logs + trace/run IDs; OpenTelemetry-compatible conventions | Корреляция UI action → command → plugin → result |
| Packaging | По одному подписанному bundle на OS/arch; Python как versioned sidecar | Предсказуемая установка без требования системного Python |

Tauri подходит лучше Electron именно для тонкой оболочки: его capability-модель ограничивает доступ конкретных window/webview к привилегированным функциям, а запуск sidecar требует явного разрешения `execute`/`spawn`. Но capability Tauri защищает мост frontend → Rust, а не произвольный Python-плагин; поэтому реальная граница доверия должна оставаться в Python command/plugin broker.[^1][^2]

## Что уже есть в SKM

SKM уже организован как umbrella-репозиторий с пакетами `aicore`, `analyst`, `brain`, `harness`, `maind`, `orch`, `planner`, `skiller`, а CLI маршрутизирует команды между пакетами. GUI не должен создавать параллельную систему модулей: новый пакет `packages/gui` должен потреблять существующий `unit.json` каждого пакета и расширить его декларативным GUI-контрактом.

Текущий control surface уже описывает четыре независимых проектных слоя — skills, roles/agents, MCP и memory/graph — и предоставляет machine-readable команды `--json`, точечные fixes и dry-run re-sync. Следовательно, первая версия dashboard может работать через стабильные JSON-выходы существующих CLI, а затем критичные операции постепенно переводить на прямые Python API без изменения frontend-контрактов.

Planner особенно хорошо готов к schema-driven GUI. Его manifest публикует CLI, config schema, версионированные plan/event/check contracts, extension point `check` и доменные события. План v1 уже разделён на схемы plan, phase, item, decision, evidence, events, snapshots и read models; item schema содержит status, dependencies, route, review mode, reviewer model/provider/effort, authority gates, RAG status, orchestration, validations и lifecycle-owned result. Это означает, что полноценный редактор планов можно построить без reverse engineering JSON.

Конфигурационная основа также уже совпадает с требованиями GUI. Planner публикует schema-driven TOML, допускает global и project config, имеет enums, numeric bounds и отдельные настройки defaults для новых планов/items. Aicore дополнительно определяет `x-skm-layers`, `x-skm-secret`, defaults и `config-explain` с winning layer, файлом, строкой и overridden values.

## Desktop, web или hybrid

| Вариант | Сильные стороны | Слабые стороны | Вердикт |
|---|---|---|---|
| Только browser UI на localhost | Самый быстрый dev loop; один web build; легко открыть несколько окон | Жизненный цикл daemon, случайное закрытие вкладки, local auth, Host/Origin/CSRF, слабее OS integration | Хорош как dev mode и аварийный fallback |
| Electron | Один TS/JS runtime, зрелая desktop-экосистема, единый Chromium | Больший runtime; main/preload/renderer security; Node API повышает последствия XSS | Резервный вариант, если Rust/Tauri станет организационным блокером |
| PySide6/Qt | Один основной язык Python; зрелые native widgets | Слабее повторное использование в браузере; труднее runtime UI contributions; отдельная UI-экосистема | Не рекомендуется для extensible dashboard |
| Tauri + Python sidecar | Маленькая тонкая shell-граница; web UI переиспользуется; capabilities; natural sidecar lifecycle | Rust toolchain, сборка sidecar по target triple, различия системных WebView | **Рекомендуется** |
| Удалённый web service | Централизованное управление парком и совместная работа | Auth/RBAC/TLS, remote execution, secrets, tenancy, distributed state | Отложить до отдельного security design |

Electron безопасен только при строгом разделении процессов: renderer sandbox ограничивает прямой доступ к системе, а privileged operations должны идти через IPC; Node integration отключает sandbox, а context isolation само по себе не делает произвольный bridge безопасным. Tauri сокращает поверхность, но не отменяет необходимость CSP, валидации каждого сообщения, ограничения навигации и отказа от remote content.[^3][^4][^5]

Гибридность надо реализовать не двумя приложениями, а одной трёхчастной системой:

```text
React/TypeScript UI
        │ typed HTTP + WebSocket
        ▼
Python SKM GUI Agent (single authority)
        │ adapters / command broker / plugin supervisor
        ▼
SKM packages, project files, subprocess plugins, provider CLIs

Tauri shell = lifecycle + OS integration around the same UI/API
Browser mode = optional localhost client of the same UI/API
```

## Границы компонентов

### Tauri shell

Rust-часть должна оставаться намеренно тонкой. Она отвечает только за:

- Запуск одного экземпляра Python sidecar и handshake версии/protocol.
- Выделение случайного loopback-порта или локального transport endpoint.
- Передачу bootstrap secret через pipe/унаследованный descriptor, а не command line.
- Контроль жизненного цикла: health check, graceful shutdown, hard kill после deadline.
- Native file/folder picker, tray, notifications, deep links и updater.
- Запрет произвольного shell API из webview; frontend вызывает только небольшой allowlisted bridge.

Tauri позволяет ограничивать permissions по window/webview, а sidecar запускается только после явного allow-list правила. Обновления должны быть подписаны: Tauri updater требует signature verification, и её нельзя отключить; приватный ключ должен находиться только в CI/release infrastructure.[^2][^6][^1]

### Python control plane

Python backend — единственная авторитетная точка для операций с SKM. Он содержит:

- `ProjectRegistry`: обнаружение проектов, canonical path, trust state, recent projects.
- `ConfigService`: load/merge/explain/validate/diff/write/rollback.
- `SchemaRegistry`: версии схем, `$ref` resolution, UI annotations, migrations.
- `CommandCatalog`: декларативные действия пакетов и их input/output schemas.
- `ExecutionBroker`: subprocess, PTY, timeout, cancellation, permission check, audit.
- `PluginSupervisor`: discovery, compatibility, enable/disable, process lifecycle, quarantine.
- `PlanService`: read models и mutation commands Planner, без прямой записи JSON из UI.
- `DocsService`: безопасный markdown render/search с привязкой к package/version.
- `EventHub`: WebSocket subscriptions, replay cursor, backpressure.
- `RunStore`: metadata, state machine, log chunks, artifacts, retention.

FastAPI/Starlette подходит как local API, поскольку поддерживает двунаправленные WebSocket endpoints, dependency/security hooks и обработку disconnects. Pydantic 2 может генерировать JSON Schema 2020-12 и OpenAPI 3.1 из Python models, но для существующих SKM contracts источник истины должен идти в обратную сторону: backend валидирует по canonical JSON Schema, а Pydantic models используются только там, где это не создаёт второй расходящийся контракт.[^7][^8][^9][^10]

### React frontend

Frontend должен быть непривилегированным клиентом. Рекомендуемые модули:

- `app-shell`: navigation, command palette, global search, notifications.
- `core-dashboard`: fleet health, recent runs, drift, blocked plans, plugin failures.
- `projects`: список, trust, четыре control-surface слоя, fixes и sync preview.
- `configuration`: effective/layers/diff/raw, schema form, provenance badges.
- `executions`: command builder, confirmation, live output, cancellation, artifacts.
- `plugins`: catalog, permissions, compatibility, enable/disable, health, logs.
- `docs`: versioned docs, full-text search, deep links в settings/actions.
- `planner`: plans, phases, item editor, dependencies, progress, events and review settings.

TanStack Query следует использовать только для server state. Локальное UI-состояние должно оставаться минимальным: selected project, panel layout, draft form и filters; canonical entities не дублируются в глобальном store.

## Plugin-модель

### Базовый принцип

Пакет не должен поставлять произвольный React-код как основной способ интеграции. В v1 каждый пакет публикует **декларативные contributions**, которые host визуализирует своими доверенными компонентами. Это сохраняет единый UX, работает в desktop и browser mode, упрощает совместимость и резко уменьшает supply-chain/XSS риск.

Существующий SKM extension contract уже предусматривает executable entrypoint, protocol range, required contracts, provided extension points/events, capabilities, permissions и timeout. Его надо расширить совместимым GUI-контрактом, а не вводить отдельный loader на базе импортов Python. Для установленных Python distributions допустим discovery через standardized package entry points, однако entry point должен возвращать descriptor/manifest, а фактическое выполнение всё равно идти в subprocess; PyPA описывает entry points как portable metadata для обнаружения плагинов через `importlib.metadata`.[^11][^12]

### Предлагаемый manifest

В `unit.json` для встроенного пакета или `extension.json` для внешнего расширения добавляется ссылка на отдельный `gui.json`:

```json
{
  "$schema": "urn:swissknifeman:gui:contribution:v1",
  "plugin": "planner",
  "gui_protocol": { "min": "1", "max": "1" },
  "assets_digest": "sha256:...",
  "contributes": {
    "routes": [
      {
        "id": "planner.plans",
        "path": "/projects/:projectId/plans",
        "title": "Plans",
        "view": "resource-list",
        "resource": "planner.plan"
      }
    ],
    "dashboard_widgets": [
      {
        "id": "planner.progress",
        "view": "metric-group",
        "query": "planner.dashboard.progress",
        "default_size": "medium"
      }
    ],
    "actions": [
      {
        "id": "planner.run-item",
        "title": "Run item",
        "command": "planner.item.run",
        "confirmation": "risk-based"
      }
    ],
    "config_sections": [
      {
        "id": "planner.settings",
        "schema": "urn:swissknifeman:planner:config:v1#/properties/planner"
      }
    ],
    "docs": [{ "id": "planner", "root": "docs", "index": "README.md" }]
  }
}
```

`view` — идентификатор host-компонента, а не путь к JS module. Начальный каталог views: `resource-list`, `resource-detail`, `schema-form`, `metric`, `metric-group`, `status-table`, `timeline`, `log-stream`, `markdown`, `dependency-graph`, `command-form`.

### Когда нужен custom UI

Escape hatch допустим позже как отдельный trust tier:

1. Custom frontend bundle подписан и связан digest с manifest.
2. Он запускается в отдельном webview/iframe origin с жёсткой CSP.
3. Он не получает Tauri API, filesystem, shell или секреты.
4. Доступен только versioned message API с capability tokens.
5. Все payload валидируются host-схемами в обе стороны.
6. Plugin можно отключить и перевести в quarantine без перезапуска всего приложения.

Module Federation или runtime `import()` из plugin directories не следует использовать в v1: они смешивают dependency resolution, CSP, подписи, React singleton compatibility и privilege boundary. Декларативный renderer покрывает Planner, config, docs, logs и dashboard widgets без этого риска.

### Enable и disable

Состояния плагина должны быть явной машиной состояний:

```text
discovered → compatible → enabled → starting → healthy
                         ↘ disabled
starting/healthy → degraded → quarantined
incompatible / invalid / permission-denied
```

Отключение состоит из двух независимых флагов:

- `runtime_enabled`: backend actions/subscriptions/process.
- `ui_enabled`: routes/widgets/docs contributions.

Host сначала снимает UI routes, запрещает новые invokes, отменяет или дожидается активных jobs по policy, завершает subprocess и только затем фиксирует состояние. Нельзя выгружать импортированный Python module из главного процесса; поэтому subprocess isolation является обязательной, а не косметической.

## Конфигурация и наследование

### Слои

Рекомендуемый порядок эффективного значения:

```text
schema default
  < global user
  < workspace/ecosystem
  < project
  < plan
  < item
  < invocation (ephemeral)
```

Не каждый ключ обязан быть разрешён на каждом уровне. `x-skm-layers` уже предназначен для этого, а GUI должен скрывать или блокировать запрещённые targets с объяснением. Planner сегодня явно использует global и project files, а часть ключей допускает invocation override.

### Экран редактора

Для каждого поля интерфейс показывает:

- Effective value.
- Winning layer и точный source file.
- Все overridden values по слоям.
- Default из schema.
- Разрешённые edit layers.
- Validation constraints и description.
- Состояние: inherited, overridden, invalid, secret reference, read-only.

Верхняя панель содержит target layer selector и режимы `Form`, `Diff`, `Raw`, `Explain`. Изменение выполняется только в выбранном слое; «изменить effective value» без выбора слоя запрещено, иначе пользователь не понимает, какой файл изменился.

### Транзакция записи

Каждая mutation проходит одинаковый pipeline:

1. Клиент получает document и `revision` — digest содержимого и зависимых layers.
2. Отправляет JSON Patch/typed patch, target layer и expected revision.
3. Backend применяет patch в памяти.
4. Выполняет schema validation и package semantic checks.
5. Строит before/effective-after diff и impact summary.
6. Для опасных изменений требует подтверждение.
7. Берёт file lock, повторно сверяет revision.
8. Пишет во временный файл, `fsync`, atomic replace.
9. Перечитывает и повторно валидирует.
10. Публикует config-changed event и audit record.

TOML следует обновлять библиотекой, сохраняющей комментарии и порядок, но бизнес-логика не должна зависеть от конкретной библиотеки. При конфликте revision UI показывает three-way diff и предлагает reload/copy draft; silent last-write-wins недопустим.

### Secret fields

`x-skm-secret: true` означает редактор **secret reference**, а не секретного значения. UI может сохранять `env://NAME`, `keyring://service/key` или другой разрешённый reference, но read API никогда не возвращает resolved secret. Даже privileged command получает секрет через краткоживущий environment injection, а log redactor знает fingerprints переданных значений.

### Модели

Model selector строится из `aicore` model catalog и provider capability observations, а не из свободного текстового списка; model catalog уже является отдельным versioned contract. Для review item UI показывает mode, class, provider, model и effort, потому что эти поля уже определены в item schema. Невалидная или недоступная модель отображается как drift с repair action, а не автоматически заменяется без ведома пользователя.

## Planner UX

### Список и прогресс

Страница проекта показывает планы с состоянием, фазами, completed/total items, blocked count, pending gates, stale schema/version и последней активностью. Расчёт прогресса должен выполняться в `PlanService`, а не в React, чтобы CLI, browser и desktop видели одинаковую семантику.

### Страница плана

Рекомендуемые представления:

- Overview: brief, settings, health, progress, next ready items.
- Board: items по lifecycle status.
- Phases: ordered phase/item hierarchy.
- Graph: blocking `depends_on` и non-blocking `related` отдельно.
- Decisions: accepted/superseded/conflicting decisions.
- Evidence: checks, artifacts, commits, captures.
- Timeline: planner events and runs.
- Raw: read-only canonical JSON с source paths; edit только через typed forms/actions.

### Редактор item

Поля группируются по смыслу, а не по порядку JSON:

- Intent: title, summary, why, scope.
- Inputs: reads, decisions, skills, examples, artifacts.
- Execution: route class/effort, orchestration, rules, guidance, task files.
- Review: mode, model class, provider, model, effort.
- Gates: authority kind/gate/scope.
- Research: need/status/captures.
- Validation: exact checks and deliverables.
- Result: lifecycle-owned, преимущественно read-only.

Schema `readOnly`/`writeOnly`, defaults и examples имеют стандартную семантику в JSON Schema 2020-12 и могут напрямую влиять на renderer. Для SKM-specific UX следует добавить только namespaced annotations, например `x-skm-widget`, `x-skm-order`, `x-skm-group`, `x-skm-confirm`, `x-skm-resource-ref`; unknown annotations должны игнорироваться renderer, но валидироваться schema lint в репозитории.[^13]

### Mutation safety

GUI не должен непосредственно менять lifecycle-owned `status`, `result` или `updated_at`, даже если поле физически находится в JSON. Для них используются доменные команды `start`, `finish`, `block`, `skip`, `review`, `accept-decision`, которые поддерживают invariants, idempotency и event journal. Item schema прямо отмечает lifecycle ownership status/result и содержит attempt id для идемпотентной регистрации результата.

## Выполнение команд

### Два режима

1. **Catalog actions** — рекомендуемый режим. Пакет объявляет command id, input schema, required context, permissions, risk, timeout, streaming mode и idempotency.
2. **Arbitrary terminal** — отдельная privileged feature. Она выключена по умолчанию, требует доверенного проекта и явного подтверждения точной команды.

Нельзя строить основной API как `POST /run {"command": "..."}`. Правильный запрос — `POST /commands/{commandId}/runs` с типизированным input; backend сам строит argv по зарегистрированному adapter.

### Execution descriptor

Каждая команда объявляет:

```json
{
  "id": "planner.item.run",
  "input_schema": "urn:swissknifeman:gui:command:planner-item-run:v1",
  "context": ["project", "plan", "item"],
  "effects": ["project.write", "process.spawn"],
  "risk": "high",
  "supports": ["dry-run", "cancel", "stream"],
  "timeout_seconds": 3600,
  "concurrency_key": "project:{project_id}:plan:{plan_id}"
}
```

`risk` определяет confirmation UX, а permissions остаются отдельной enforceable policy. Нельзя смешивать «опасно» и «разрешено»: команда может быть high-risk, но разрешённой, или low-risk, но запрещённой политикой.

### Process safety

Execution broker обязан:

- Использовать argv array и `create_subprocess_exec`, никогда `shell=True` для catalog actions.
- Нормализовать и проверять `cwd` против trusted project roots.
- Передавать allowlisted environment; удалять token/secrets по умолчанию.
- Ограничивать output chunk size, total bytes, runtime и idle timeout.
- Поддерживать cancel всей process group/tree.
- Отделять stdout, stderr, structured events и artifacts.
- Выполнять redaction до записи на диск и до отправки в WebSocket.
- Сохранять exact executable digest/version, argv с redaction, cwd, actor, permission decision и exit state.
- Ограничивать число одновременных jobs globally, per project и per plugin.

Для interactive commands нужен PTY через отдельный adapter и xterm.js. PTY нельзя автоматически выдавать каждому plugin: он практически эквивалентен интерактивному shell и должен иметь отдельную capability и audit trail.

### Реальность sandbox

«Отдельный процесс» обеспечивает crash isolation, но сам по себе не ограничивает filesystem/network. Строгая enforceable изоляция требует OS-specific sandbox или container: bubblewrap на Linux, отдельной стратегии sandbox/profile на macOS и Windows. Поэтому permissions manifest должен показывать два статуса — `declared` и `enforced`; если платформа не умеет enforce конкретный effect, UI обязан показать `advisory`, а политика может запретить запуск. Это лучше ложного зелёного индикатора.

## API-контракты

### Core HTTP

| Method | Endpoint | Назначение |
|---|---|---|
| GET | `/v1/bootstrap` | Версии UI/API/protocol, features, session, platform |
| GET | `/v1/projects` | Fleet/project list and health summary |
| GET | `/v1/projects/{id}` | Project details and four-layer status |
| POST | `/v1/projects/{id}/actions/{action}` | Typed fix/sync/doctor actions |
| GET | `/v1/config/{module}/effective` | Effective config + provenance + revisions |
| POST | `/v1/config/{module}/preview` | Validate patch and return diff/impact |
| PATCH | `/v1/config/{module}/layers/{layer}` | CAS mutation after preview |
| GET | `/v1/plugins` | Catalog, state, compatibility, permissions |
| POST | `/v1/plugins/{id}:enable` | Enable runtime/UI under policy |
| POST | `/v1/plugins/{id}:disable` | Drain and disable |
| GET | `/v1/commands` | Context-filtered action catalog |
| POST | `/v1/commands/{id}/runs` | Start typed run |
| POST | `/v1/runs/{id}:cancel` | Cancel run/process tree |
| GET | `/v1/runs/{id}` | Run state, result, artifacts |
| GET | `/v1/ui/contributions` | Resolved routes/widgets/docs/actions |
| GET | `/v1/schemas/{contract}/{version}` | Canonical schema registry |

Plugin-specific APIs не должны добавлять произвольные FastAPI routes в общий process. Они регистрируют resources, queries и commands через contracts; host exposes generic endpoints and dispatches protocol messages to subprocesses.

### Event stream

Один WebSocket `/v1/events` поддерживает subscriptions по project/run/plugin/type и cursor replay. Событие имеет monotonic local sequence, event id, timestamp, type, source, project id, correlation id и schema-versioned data. Это естественно продолжает существующий aicore event contract — subset CloudEvents с типом `<module>.<subject>.<verb>`.

Backpressure обязателен: progress events можно coalesce, log chunks — ограничивать ring buffer, terminal bytes — подтверждать window/credits. При reconnect клиент передаёт last sequence; если replay уже удалён retention policy, server возвращает snapshot-required.

### Ошибки

Все ошибки приводятся к одному envelope:

```json
{
  "error": {
    "code": "CONFIG_REVISION_CONFLICT",
    "class": "conflict",
    "message": "Configuration changed on disk",
    "retryable": false,
    "details": {},
    "correlation_id": "..."
  }
}
```

Safe message отделяется от internal traceback. Существующий aicore contract `error` уже моделирует class, code, retryable и safe message.

## Логи и наблюдаемость

Лог — structured event, а не строка терминала. Минимальные поля: timestamp, severity, component, event, message, project, plugin, command, run id, trace id, span id, stream, redaction status. Raw ANSI output хранится отдельно и связывается с run.

OpenTelemetry Python предоставляет интерфейсы для traces, metrics и logs, а logging integration умеет добавлять trace/span context в стандартные Python log records. Для первой версии не нужен обязательный collector: достаточно писать OTel-compatible JSON локально, оставив OTLP exporter opt-in. В самом SKM уже есть telemetry conventions contract, поэтому имена spans/attributes нужно брать из него, а не придумывать в GUI.[^14][^15]

Retention policy задаётся по типу данных:

- Run metadata — долго, малый объём.
- Structured logs — ограничение по возрасту и суммарному размеру.
- Terminal chunks — более короткое хранение.
- Artifacts/evidence — по policy владельца проекта.
- Secrets — никогда.

Dashboard строится из materialized summaries в SQLite, но любой показатель должен ссылаться на underlying runs/events. SQLite — кэш и индекс GUI; canonical plans/configs и package manifests остаются в репозитории/пользовательских config files.

## Local security

### Session и transport

Даже localhost API требует аутентификации. При старте shell создаёт 256-bit random session secret, передаёт его sidecar через защищённый pipe и frontend через Tauri bootstrap command. Backend слушает только `127.0.0.1`/`::1`, проверяет `Host`, `Origin`, protocol version и bearer/session token; CORS не разрешает wildcard.

Browser mode запускается отдельной явной командой и выдаёт одноразовый URL, который меняется на secure session cookie (`HttpOnly`, `SameSite=Strict`) после первого запроса. Desktop mode не должен автоматически принимать browser clients. Remote binding `0.0.0.0` отсутствует в production binary.

### Trust model

Объекты доверия различаются:

- Application release.
- Core package.
- Built-in plugin.
- External signed plugin.
- Unsigned local development plugin.
- Project/repository.
- Arbitrary command invocation.

Trust не транзитивен: доверенный plugin не делает доверенным открытый проект; доверенный проект не разрешает любой shell. Permission grants scoped по plugin + capability + project + optional duration и сохраняются с manifest digest, чтобы обновление permission set требовало повторного approval.

### Web content

Docs renderer запрещает raw HTML по умолчанию, sanitizes links и не исполняет scripts. External links открываются только после scheme allowlist (`https`, возможно `mailto`) и user action. Electron отдельно предупреждает, что `openExternal` с untrusted input может привести к выполнению команд; тот же принцип применим к Tauri opener.[^4]

### Supply chain

- Подписывать desktop bundle и update artifacts.
- Pin Python and npm lockfiles, Rust `Cargo.lock`.
- Формировать SBOM на release.
- Проверять digest sidecar при старте.
- Связывать plugin asset digest с manifest.
- Не скачивать/активировать plugin автоматически без preview permissions.
- Разделять stable/beta/dev channels.

## Надёжность

### Состояние run

```text
queued → authorizing → starting → running
                         ↘ failed_to_start
running → succeeded | failed | cancelling → cancelled | timed_out | lost
```

Переходы сохраняются до публикации UI event. После crash backend помечает незавершённые локальные процессы `lost`, проверяет pid identity/creation time и не пытается слепо «усыновить» произвольный PID.

### Блокировки

- Один writer на конкретный config document.
- CAS revision поверх file lock.
- Planner mutations используют существующий planner lock timeout, а не второй GUI lock.
- Long-running command lock не держит database transaction.
- Per-project mutation queue предотвращает конкурирующие `sync`/`setup`, но read-only health может выполняться параллельно.

### Работа с файлами

File watcher служит сигналом invalidate, но не источником истины. После события backend перечитывает и валидирует документ. Rename/temp-write patterns debounce; изменения самого GUI не должны порождать бесконечный цикл refresh.

### Совместимость

Handshake включает:

- Desktop app version.
- UI build id.
- Backend version.
- GUI protocol min/max.
- SKM contracts supported.
- Package/plugin versions.

При несовместимости shell показывает диагностическую страницу и путь восстановления; он не пытается открыть основной dashboard. Breaking contract создаёт `v2` рядом с `v1`, что уже является правилом aicore.

## Тестовая стратегия

### Contract tests

Каждая schema имеет valid/invalid fixtures; GUI renderer дополнительно использует golden fixtures для widgets, conditionals, refs и layered config. Такой layout уже принят в aicore: `schemas/tract>/vN`, valid/invalid examples, сохранение старой major version рядом с новой.

### Backend

- Unit: merge/explain, permissions, argv construction, redaction, state machines.
- Property-based: config patch round-trip, arbitrary nested schema values, path normalization.
- Integration: реальные CLI с temp projects; command cancel/timeout; plugin crash/malformed output.
- Security: traversal, symlink escape, hostile ANSI, oversized frames, origin/host spoofing, secret leakage.
- Migration: SQLite upgrade/downgrade policy и schema-version fixtures.

### Frontend

- Component tests для schema widgets и provenance.
- Contract-generated tests для каждого field type.
- Accessibility: keyboard-only, focus after dynamic form change, screen-reader labels.
- E2E через Tauri driver/browser mode: onboarding, config conflict, plugin disable during run, reconnect logs.

### Plugin conformance

Команда `swissknifeman gui plugin check <path>` должна проверять manifest, protocol overlap, schemas, assets digest, permissions, describe handshake, sample invocation, timeout/cancel и отсутствие undeclared contributions. Plugin SDK предоставляет fixture host и recorder; публикация plugin без conformance gate запрещена.

## Риски и меры

| Риск | Вероятность/влияние | Мера |
|---|---|---|
| GUI начинает дублировать domain logic CLI | Высокое/высокое | Backend adapters и canonical service API; UI не пишет domain files напрямую |
| Произвольный plugin UI компрометирует host | Среднее/критическое | Declarative contributions by default; isolated custom UI only later |
| «Permissions» остаются только декларацией | Высокое/высокое | Показывать declared/enforced; deny при требовании strict enforcement |
| Sidecar packaging ломается на OS/arch | Среднее/высокое | Release matrix, smoke-test установленного bundle, protocol handshake, rollback channel |
| localhost API доступен посторонней странице | Среднее/критическое | Random secret, Host/Origin checks, strict CORS/CSP, desktop/browser mode separation |
| Config editor теряет комментарии или чужие изменения | Среднее/высокое | Comment-preserving writer, revision CAS, file locks, atomic replace, three-way conflict |
| Логи раскрывают API keys/prompts | Среднее/критическое | Secret references, pre-storage redaction, size limits, export preview |
| Команда оставляет дочерние процессы после cancel | Среднее/высокое | Process groups/job objects, tree kill, deadline escalation, tests per OS |
| System WebView ведёт себя по-разному | Среднее/среднее | Ограниченный browser feature baseline, CI on all supported OS, Electron fallback ADR |
| Plugin обновился с новыми permissions | Среднее/высокое | Grants tied to manifest digest; re-approval on permission delta |
| Runtime routes конфликтуют | Среднее/среднее | Namespaced IDs/paths, deterministic resolver, conflict as invalid plugin state |
| UI schema annotations расходятся с validator | Среднее/среднее | Canonical schema lint + renderer contract tests; annotations never alter validation |
| SQLite становится вторым source of truth | Среднее/высокое | Только cache/index/UI state; rebuild command from canonical files/events |
| Remote mode случайно появляется без security design | Низкое/критическое | Production bind loopback-only, no remote flag; отдельный future product/ADR |

## Структура кода

```text
packages/gui/
  unit.json
  configs/config.schema.json
  schemas/
    gui-contribution/v1/
    command-descriptor/v1/
    api-error/v1/
    run-event/v1/
  backend/
    skm_gui/
      api/
      projects/
      config/
      commands/
      plugins/
      plans/
      docs/
      events/
      storage/
      security/
  frontend/
    src/
      app/
      core/
      features/
      plugin-views/
      generated-api/
  desktop/
    src-tauri/
  tests/
    contracts/
    integration/
    e2e/
```

Domain-specific frontend contributions могут жить в своём пакете как data/templates:

```text
packages/planner/
  gui/
    contribution.json
    queries.json
    docs-index.json
    ui-schema/
      plan.json
      phase.json
      item.json
```

При сборке `packages/gui` собирает validated contribution catalog, аналогично тому как существующий aicore собирает plugin catalogs. External packages обнаруживаются runtime, но проходят тот же resolver и conformance checks.

## Этапы реализации

### Этап 0 — контракты

Критерий завершения: ни один UI экран ещё не нужен, но frozen v1 contracts готовы.

- ADR: Tauri vs Electron, local transport, source-of-truth boundaries.
- `gui-contribution/v1`, `command-descriptor/v1`, `run-event/v1`.
- Расширение `unit`/`extension` ссылкой на GUI contribution без breaking change либо новая major schema.
- Permission semantics `declared/advisory/enforced`.
- Compatibility and handshake matrix.

### Этап 1 — browser-capable control plane

Критерий завершения: один проект можно безопасно открыть, диагностировать и изменить config.

- Python service, session bootstrap, project registry.
- Dashboard поверх `swissknifeman status --json`.
- Effective config/explain, preview/diff/CAS save.
- Run store, structured logs, basic WebSocket.
- Browser dev mode только на loopback.

### Этап 2 — desktop shell

Критерий завершения: подписываемый installable app управляет sidecar и восстанавливается после crash.

- Tauri lifecycle, single instance, file picker, tray.
- Sidecar bundling per target.
- Health/restart/diagnostic screen.
- Release signing and updater.

### Этап 3 — plugin platform

Критерий завершения: Planner и ещё один пакет подключаются без изменений core frontend routing.

- Contribution resolver and host view catalog.
- Plugin catalog, permissions, enable/disable/quarantine.
- Subprocess supervisor over existing extension protocol.
- Conformance CLI and fixture host.

### Этап 4 — Planner

Критерий завершения: планы полностью читаются в человеческом виде, а разрешённые изменения выполняются typed domain mutations.

- Plan list, phase/item views, progress.
- Typed item editor including route/review/provider/model/effort.
- Dependency graph, decisions, evidence, timeline.
- Lifecycle actions and conflict handling.

### Этап 5 — команды и терминал

Критерий завершения: catalog actions имеют dry-run/confirm/cancel/logs, arbitrary terminal отделён policy.

- Command forms from schema.
- Risk-based confirmation.
- Cross-platform process-tree cancellation.
- PTY/xterm as explicit privileged capability.
- Output limits, redaction, artifact download.

### Этап 6 — hardening

Критерий завершения: threat model и failure matrix закрыты automated gates.

- OS sandbox adapters and enforcement indicators.
- Supply-chain checks, SBOM, digest verification.
- Accessibility/performance budgets.
- Restore/rebuild SQLite cache.
- Full installer E2E on supported OS/arch.

## Решения, которые стоит зафиксировать сразу

1. **Tauri 2 + React/TypeScript + Python sidecar** — основной production stack.
2. **Browser mode поддерживается архитектурно**, но остаётся local development/fallback, не remote product.
3. **Python backend — единственный authority**; Rust не дублирует SKM domain logic, React не трогает filesystem.
4. **Плагины выполняются в subprocess** через существующий extension protocol; package imports допустимы только для trusted descriptors/build-time tooling.
5. **Plugin UI декларативен по умолчанию**; произвольный JS не входит в v1.
6. **Все config/plan editors schema-driven**, но mutations учитывают domain ownership и не сводятся к generic JSON save.
7. **Файлы SKM остаются source of truth**; SQLite — индекс, cache и GUI-local state.
8. **Catalog actions первичны**, arbitrary shell — отдельная привилегия.
9. **Permissions показывают enforceability**, а не создают иллюзию sandbox.
10. **Remote multi-user mode — отдельная будущая архитектура**, а не скрытый checkbox.

## Definition of Done для MVP

MVP можно считать архитектурно полноценным, когда он выполняет следующий vertical slice:

- Находит проекты и показывает четыре control-surface слоя, drift и exact fixes.
- Открывает global/project config, показывает effective value и provenance каждого ключа.
- Валидирует и атомарно сохраняет override с preview diff и conflict detection.
- Показывает package/plugin catalog, compatibility и permissions; включает/отключает один subprocess plugin.
- Запускает allowlisted command с dry-run/confirmation, live logs, cancel и audit.
- Показывает список Planner plans, phases/items и позволяет изменить route/review model через domain mutation.
- Переживает crash plugin и backend без повреждения canonical files.
- Работает из одного frontend build в Tauri и local browser dev mode.

Этот slice проверяет все рискованные основания — desktop lifecycle, Python orchestration, contracts, plugins, layered config, Planner, execution и logs — до инвестиций в многочисленные специализированные widgets.

---

## References

1. [Capabilities | Tauri](https://v2.tauri.app/security/capabilities/) - Capabilities define which permissions are granted or denied for which windows or webviews.

2. [Embedding External Binaries - Tauri](https://v2.tauri.app/develop/sidecar/) - When running the sidecar, Tauri requires you to give the sidecar permission to run the `execute` or ...

3. [Process Sandboxing | Electron](https://www.electronjs.org/docs/latest/tutorial/sandbox) - more privileged than that of a sandboxed renderer, it is still possible to leak
privileged APIs to u...

4. [Security | Electron](https://www.electronjs.org/docs/latest/tutorial/security) - Context isolation is an Electron feature that allows developers to run code
in preload scripts and i...

5. [Context Isolation - Electron](https://www.electronjs.org/docs/latest/tutorial/context-isolation) - Context Isolation is a feature that ensures that both your `preload` scripts and Electron's internal...

6. [Updater - Tauri](https://v2.tauri.app/plugin/updater/) - 2. The private key, which is used to sign your installer files.

7. [WebSockets](https://fastapi.tiangolo.com/advanced/websockets/) - In WebSocket endpoints you can import from `fastapi` and use:
- `Depends`

8. [WebSockets - FastAPI](https://fastapi.tiangolo.com/reference/websockets/) - When defining WebSockets, you normally declare a parameter of type `WebSocket` and with it you can r...

9. [pydantic.dev › validation › 2Json schema | Pydantic Docs](https://pydantic.dev/docs/validation/2.8/concepts/json_schema/) - `model_json_schema` and `TypeAdapter.json_schema` methods.

10. [pydantic.dev › docs › validationJSON Schema | Pydantic Docs](https://pydantic.dev/docs/validation/latest/concepts/json_schema/) - Pydantic allows automatic creation and customization of JSON schemas from models.

11. [Creating and discovering plugins](https://packaging.python.org/en/latest/guides/creating-and-discovering-plugins/) - Then you can discover and load all of the registered entry points by using

12. [Entry points specification](https://packaging.python.org/en/latest/specifications/entry-points/?i6gfh5g0n) - *Entry points* are a mechanism for an installed distribution to advertise components it provides to ...

13. [A Vocabulary for Structural Validation of JSON](https://json-schema.org/draft/2020-12/json-schema-validation) - of the instance is managed exclusively by the owning authority, and
...
is never present when the in...

14. [opentelemetry-python.readthedocs.io › en › latestOpenTelemetry Python API — OpenTelemetry Python documentation](https://opentelemetry-python.readthedocs.io/en/latest/api/index.html) - implementations for instrumenting applications with traces, metrics, and logs.

15. [OpenTelemetry Logging Instrumentation](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/logging/logging.html) - The OpenTelemetry `logging` integration can also be configured to inject tracing context into log st...
