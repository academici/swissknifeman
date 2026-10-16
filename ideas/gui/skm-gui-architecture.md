# SKM GUI — рекомендуемая архитектура

## Решение

Основной production-стек: **Tauri 2 + React/TypeScript + Python sidecar**. Один и тот же frontend должен работать внутри desktop shell и в опциональном локальном browser mode. Python backend остаётся единственным владельцем SKM domain logic, конфигурации, планов, команд, плагинов и логов.

## Слои

| Слой | Технология | Ответственность |
|---|---|---|
| Desktop shell | Tauri 2 | Lifecycle sidecar, single instance, tray, native dialogs, updater |
| Frontend | React, TypeScript, Vite | Dashboard, projects, config, plans, plugins, docs, logs |
| API | FastAPI/Starlette, Pydantic 2 | HTTP/WebSocket contracts, validation, orchestration |
| Execution | asyncio subprocess supervisor | Commands, cancellation, timeouts, process trees, redaction |
| Plugin runtime | Existing SKM stdio JSON protocol | Process isolation, permissions, health, quarantine |
| Local state | SQLite | GUI preferences, run index, cache; never canonical config/plans |

## Главные правила

1. React не получает filesystem или shell access.
2. Rust shell не дублирует SKM domain logic.
3. GUI не пишет plan/config JSON напрямую: только typed domain mutations.
4. Canonical SKM files and schemas остаются source of truth.
5. Plugin UI в v1 — декларативные routes, widgets, forms, commands и docs.
6. Произвольный JavaScript plugin UI — только будущий изолированный trust tier.
7. Catalog commands запускаются argv-массивом без `shell=True`; arbitrary terminal — отдельная привилегия.
8. Permission UI различает declared, advisory и реально enforced ограничения.
9. Local API требует случайный session secret, Origin/Host checks и loopback-only binding.
10. Remote multi-user mode проектируется отдельно, а не включается скрытым флагом.

## Plugin contract

Каждый встроенный пакет расширяет `unit.json`, внешний — `extension.json`, ссылкой на `gui.json`. Contribution manifest объявляет:

- routes;
- dashboard widgets;
- typed actions;
- config sections;
- resources and queries;
- documentation roots;
- required contracts and protocol range;
- permissions and assets digest.

Host рендерит доверенные виды: `resource-list`, `resource-detail`, `schema-form`, `metric-group`, `status-table`, `timeline`, `log-stream`, `markdown`, `dependency-graph`, `command-form`.

## Config editor

Effective config строится по слоям:

`schema default < global < workspace < project < plan < item < invocation`.

Для каждого поля UI показывает effective value, winning layer, source file, overridden values, default, разрешённые edit layers и validation constraints. Запись проходит preview, schema/semantic validation, diff, permission confirmation, revision CAS, file lock, atomic replace и повторную валидацию.

## Planner

Planner contribution предоставляет:

- список планов и progress summaries;
- phases, board и dependency graph;
- decisions, evidence и timeline;
- typed item editor;
- route/orchestration controls;
- review mode, provider, model and effort;
- authority gates и RAG status;
- lifecycle actions `start`, `finish`, `block`, `skip`, `review`.

Lifecycle-owned `status`, `result` и timestamps нельзя менять generic form editor.

## Выполнение команд

Основной API использует `commandId` и input schema, а не произвольную строку shell. Descriptor содержит context, effects, risk, timeout, support for dry-run/cancel/stream и concurrency key.

Execution broker обязан ограничивать cwd, environment, output size, runtime и concurrency; отменять всё process tree; отделять stdout/stderr/events/artifacts; редактировать секреты до записи; сохранять executable version/digest, redacted argv, cwd, permission decision и exit state.

## Надёжность

- Plugin всегда исполняется отдельным процессом.
- Enable/disable — явная state machine с drain и quarantine.
- WebSocket имеет cursor replay и backpressure.
- File watchers только инвалидируют cache; backend всегда перечитывает и валидирует файл.
- Незавершённые runs после crash становятся `lost`.
- Handshake проверяет desktop, UI, backend, GUI protocol и contract versions.
- SQLite можно полностью перестроить из canonical files/events.

## Этапы

1. Заморозить GUI contribution, command, event и compatibility contracts.
2. Реализовать Python control plane и local browser dev mode.
3. Добавить Tauri shell, sidecar packaging и signed updater.
4. Реализовать contribution resolver, plugin supervisor и conformance tests.
5. Сделать полный Planner vertical slice.
6. Добавить typed command runner, затем privileged PTY terminal.
7. Провести OS sandboxing, supply-chain, installer E2E и security hardening.

## MVP DoD

- Fleet dashboard показывает четыре control-surface слоя, drift и fixes.
- Global/project config редактируется с provenance, preview и conflict detection.
- Plugin можно включить, отключить и изолировать после сбоя.
- Команда имеет dry-run, confirmation, streaming logs, cancel и audit.
- Planner показывает планы в человеческом виде и меняет route/review model через domain API.
- Crash backend/plugin не повреждает canonical files.
- Один frontend build работает в Tauri и local browser mode.
