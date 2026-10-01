# academici

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> Локальный набор инструментов для разработки с Claude Code, Codex и Cursor.
> Монорепозиторий-зонтик экосистемы **academici**: скиллы, проекции под клиентов,
> инструменты задач и общая память/граф — с явными границами поддержки провайдеров.

**Что это даёт разработчику:** можно подключить к проекту нужные скиллы и проекции клиента;
Task и длинные workflow вызываются только для задач, которым они полезны. Матрица ниже
показывает, где возможности клиента нативны, адаптированы или недоступны.

👉 **[Начать работу](docs/getting-started.md)** — короткий путь к первой задаче и выбор масштаба
процесса. Подробности Claude Code — в [раннбуке разработчика](docs/develop.md).

## Возможности

<!-- BEGIN GENERATED PROVIDER CAPABILITIES -->
### Поддержка провайдеров (generated)

Единый manifest: contract `1.0.0`, catalog `1.0.0`, canonical SHA-256 `cec032979b131fda6314a5e4ae0803ee75508f1c1f31dcf26c36a727c2206315`. Manifest (`configs/provider-capabilities.json`) — source of truth, hand-edited, no generator: `root.generated-artifacts` does not apply to it. Подробности и операции: [provider support](docs/provider-support.md).

| Capability | Claude Code | Codex | Cursor |
|:--|:--:|:--:|:--:|
| `agent-packs.lifecycle` | adapted | adapted | adapted |
| `agents.catalog` | adapted | adapted | adapted |
| `analytics.legacy-migration` | adapted | unsupported | unsupported |
| `analytics.normalized-events` | adapted | adapted | adapted |
| `analytics.run-report` | adapted | adapted | adapted |
| `command.external-research` | adapted | adapted | adapted |
| `command.filesystem-read` | native | native | native |
| `command.filesystem-write` | native | native | native |
| `command.git-read` | native | native | native |
| `command.git-write` | native | native | native |
| `command.subagents` | native | native | native |
| `command.workflow-carrier` | native | adapted | adapted |
| `context.observer` | unsupported | native | adapted |
| `context.output-style` | native | unsupported | unsupported |
| `context.plans-directory` | native | unsupported | unsupported |
| `doctor.environment` | adapted | adapted | adapted |
| `doctor.provider` | adapted | adapted | adapted |
| `instructions.project` | native | native | native |
| `lifecycle.auto-approval` | adapted | native | adapted |
| `lifecycle.changelog-gate` | adapted | adapted | adapted |
| `lifecycle.command-log` | adapted | adapted | adapted |
| `lifecycle.daemon-safety` | adapted | adapted | adapted |
| `lifecycle.git-guardrails` | unsupported | adapted | adapted |
| `lifecycle.memory` | adapted | adapted | adapted |
| `lifecycle.notification` | adapted | unsupported | unsupported |
| `lifecycle.pack-guard` | adapted | adapted | adapted |
| `lifecycle.review-gate` | adapted | adapted | adapted |
| `lifecycle.router` | adapted | adapted | adapted |
| `lifecycle.run-report` | adapted | adapted | adapted |
| `lifecycle.terminal-admission` | adapted | adapted | adapted |
| `lifecycle.tool-telemetry` | unsupported | adapted | adapted |
| `mcp.catalog` | adapted | adapted | native |
| `security.safe-dirs` | adapted | adapted | adapted |
| `settings.audit` | adapted | adapted | adapted |
| `settings.permissions` | adapted | adapted | adapted |
| `skills.repository` | native | native | native |
| `workflows.status` | adapted | unsupported | unsupported |

Unsupported reasons legend: `not implemented` (adapter/binding not shipped), `API-capped` (provider has no suitable project-scoped API), `not applicable` (intent has no provider object to migrate/read).
<!-- END GENERATED PROVIDER CAPABILITIES -->

| Что | Коротко |
|:--|:--|
| **🔌 Плагины со скиллами** | Единый marketplace Claude Code (бакеты навыков). Кураторский **CORE** (8 скиллов ≈ 480 резидентных токенов) раздаётся в каждый проект; остальное — по типу проекта. Два канала: `connect` (marketplace, автообновление) и `vendor` (физ. копии для отдачи вовне) |
| **🎭 Роли и workflow** | `agent-packs` — версионируемые бандлы субагентов + workflow + хуков: стек-паки (Laravel/Node/Python/Flutter) и роль-паки (tech-lead/CTO/founder/maintainer). **dev-loop** гонит вертикальные срезы через risk-адаптивный **review-gate** (Haiku→Sonnet→Opus по риску) |
| **📋 Управление задачами** | Плагин `task` (default-on): `/task:design\|dev\|review\|research\|fix` — каждая **пинит модель + effort + профиль** под интент, без ручного переключения |
| **🪙 Токен-рычаги** | Дисциплина расхода: лестница `context-economy` (трим CLAUDE.md до ~92%, роутинг моделей до ~75%, аудит MCP, selective-input 5–50×), лаконичный вывод (`compact-responses`, output-style `lean`), **PAO** для PHP (вывод тестов → ~20 токенов JSON) |
| **🧠 Память и граф** | Хаб **mAInd**: общая память экосистемы (agentmemory-демон, изоляция по namespace) + код-граф (Serena, навигация по символам вместо чтения файлов) + топология между проектами. Наблюдаемость — `maind analyze`/`verify`/`health` |
| **📈 Аналитика и обучение** | Захват прогона хуком `run-report` → пост-ран разбор `maind analyze` (вердикт GREEN/ATTENTION/RED + метрики использования памяти/графа). Пакет **`analyst`** (P1 MVP): `analyst digest` детерминированно извлекает кандидат-уроки из прогона → `review`/`promote` с **человеком в гейте** (авто-запись запрещена) → curated всплывает в память mAInd. Есть кросс-проектный агрегатор (`scan`) и confidence-жизненный цикл (`recompute`, Beta/decay + числовая state-machine) |
| **⚙️ Окружение** | `harness` настраивает Claude Code: пресеты permissions по стекам, MCP-серверы, хуки (auto-approve/memory/notify/run-report) |
| **🔎 RAG-дисциплина** | Верификация внешних фактов до фиксации: лестница context7 → perplexity-web → WebSearch (скиллы `verify-claims`, `query-craft`, `mcp-advisor`) |

## Пакеты

| Пакет | Роль | CLI |
|:--|:--|:--|
| [`packages/skiller`](packages/skiller/) | реестр AI-скиллов — раздаёт навыки в проекты (connect/vendor) | `skiller` (алиас `swissknifeman`) |
| [`packages/harness`](packages/harness/) | настройка окружения Claude Code (permissions, MCP, хуки, agent-packs) | `harness` |
| [`packages/maind`](packages/maind/) | хаб памяти, графа и координации экосистемы (MCP-шина) | `maind` |
| [`packages/analyst`](packages/analyst/) | continuous learning: захват уроков из прогонов, человеко-гейт, провенанс | `analyst` |
| [`packages/task`](packages/task/) | плагин интент-команд задач (`/task:*`, `$ task:*`) | плагины Claude Code и Codex |

Общий фундамент — пакет [`core`](core/) (stdlib-only: `Env`, вывод, slug).

## Установка

```bash
./install.sh                  # CLI + роутер + базовые Codex-плагины core/task (если Codex установлен)
```

`install.sh` делегирует пакетную пост-настройку их собственным установщикам,
ставит симлинк `swissknifeman` → корневой роутер и подключает в Codex локальный
marketplace с базовыми `core`/`task`. Opt-out: `--no-codex-plugins`.

> `.mcp.json` этого репо машинно-специфичен (абсолютные пути к `maind`) и не коммитится —
> шаблон [`.mcp.json.example`](.mcp.json.example), реальный файл генерит/обновляет `maind` (sync/deploy).

## CLI

```bash
swissknifeman <group> …       # корневой роутер: skills→skiller, env→harness, maind→maind, analyst→analyst; + setup, doctor
swissknifeman setup <project> # кросс-пакетный онбординг (скиллы+окружение+память+граф) → maind onboard
skiller <cmd>                 # реестр скиллов (connect, vendor, integrate, registry, …) — алиас swissknifeman
harness <cmd>                 # окружение Claude Code (permissions, mcp, hooks, agent-packs, doctor)
maind <cmd>                   # хаб (memory, graph, onboard, deploy, sync, health, analyze, verify, …)
analyst <cmd>                 # continuous learning (digest, scan, review, promote, deprecate, doctor)
```

## Плагины Claude Code

Один marketplace (`.claude-plugin/marketplace.json`, имя `swissknifeman` = зонтик) объявляет все
плагины репо: бакеты скиллов, кураторский `core`, `task`, `skm`, `generate-skill`, `maind` и `analyst`.
Генерируется `skiller registry`. Плагин `maind` — только команды `/maind:*` (MCP-инструменты хаба
приходят per-project сервером `maind` из `.mcp.json` проекта, не из плагина).

## Документация

- **[Начать работу](docs/getting-started.md)** — установка, первая задача и выбор пути.
- **[Раннбук разработчика](docs/develop.md)** — как вести процесс разработки с Claude Code.
- [Обзор экосистемы](docs/index.md) · [control-surface проектов](docs/control-surface.md) ·
  [роутинг источников/задач](docs/routing.md) · [референсы](docs/reference.md).
- Пакеты: [скиллы](packages/skiller/docs/) · [окружение](packages/harness/docs/) ·
  [память и граф](packages/maind/docs/) · [continuous learning](packages/analyst/README.md).

## Разработка

Тесты/валидация — по пакету:

```bash
bash packages/skiller/scripts/validate.sh
bash packages/harness/scripts/validate.sh
bash packages/maind/scripts/validate.sh
```

Подробности — в `CLAUDE.md` корня и каждого пакета (+ `CONTRIBUTING.md`). Коммиты — Conventional Commits на русском.
