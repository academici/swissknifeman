# academici

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> Швейцарский нож для разработки с Claude Code. Монорепозиторий-зонтик экосистемы **academici**:
> плагины со скиллами, роли и workflow, набор токен-рычагов, управление задачами и общая
> память/граф — под единой консолью и единым marketplace.

**Что это даёт разработчику:** подключаешь проект одной командой — и Claude Code получает
кураторский набор навыков, интент-команды задач, роли-агенты, дисциплину расхода токенов и общую
память экосистемы. Не «ещё один список правил», а собранный процесс разработки.

👉 **Как этим пользоваться — [раннбук разработчика](docs/develop.md)** (фазы плана, `/compact` vs
новая сессия, задачи, память, граф, токен-рычаги, RAG).

## Возможности

<!-- BEGIN GENERATED PROVIDER CAPABILITIES -->
### Поддержка провайдеров (generated)

Единый manifest: contract `1.0.0`, catalog `1.0.0`, canonical SHA-256 `4c479c697c708cfea8d36589c435338094d894bcf428687709987975b13b6ce1`. Подробности и операции: [provider support](docs/provider-support.md).

| Capability | Claude Code | Codex |
|:--|:--:|:--:|
| `agent-packs.lifecycle` | adapted | unsupported |
| `agents.catalog` | adapted | adapted |
| `analytics.legacy-migration` | adapted | unsupported |
| `analytics.normalized-events` | adapted | adapted |
| `analytics.run-report` | adapted | adapted |
| `command.external-research` | adapted | adapted |
| `command.filesystem-read` | native | native |
| `command.filesystem-write` | native | native |
| `command.git-read` | native | native |
| `command.git-write` | native | native |
| `command.subagents` | native | native |
| `command.workflow-carrier` | native | adapted |
| `context.observer` | unsupported | native |
| `context.output-style` | native | unsupported |
| `context.plans-directory` | native | unsupported |
| `doctor.environment` | adapted | adapted |
| `doctor.provider` | adapted | adapted |
| `instructions.project` | native | native |
| `lifecycle.auto-approval` | adapted | native |
| `lifecycle.changelog-gate` | adapted | unsupported |
| `lifecycle.command-log` | adapted | unsupported |
| `lifecycle.daemon-safety` | unsupported | unsupported |
| `lifecycle.git-guardrails` | unsupported | unsupported |
| `lifecycle.memory` | adapted | unsupported |
| `lifecycle.notification` | adapted | unsupported |
| `lifecycle.pack-guard` | adapted | unsupported |
| `lifecycle.review-gate` | adapted | unsupported |
| `lifecycle.router` | adapted | unsupported |
| `lifecycle.run-report` | adapted | unsupported |
| `mcp.catalog` | adapted | adapted |
| `security.safe-dirs` | adapted | unsupported |
| `settings.audit` | adapted | unsupported |
| `settings.permissions` | adapted | adapted |
| `skills.repository` | native | native |
| `workflows.status` | adapted | unsupported |
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
| [`packages/task`](packages/task/) | плагин интент-команд задач (`/task:*`) | плагин Claude Code |

Общий фундамент — пакет [`core`](core/) (stdlib-only: `Env`, вывод, slug).

## Установка

```bash
./install.sh                  # ставит skiller, harness, maind, analyst + корневой роутер swissknifeman в PATH
```

`install.sh` делегирует пакетную пост-настройку их собственным установщикам
(`packages/*/install.sh`) и ставит симлинк `swissknifeman` → корневой роутер (router + setup-фасад).

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

- **[Раннбук разработчика](docs/develop.md)** — как вести процесс разработки с Claude Code.
- [Обзор экосистемы](docs/index.md) · [control-surface проектов](docs/control-surface.md) ·
  [роутинг источников/задач](docs/routing.md) · [референсы](docs/reference.md).
- Пакеты: [скиллы](packages/skiller/docs/) · [окружение](packages/harness/docs/) ·
  [память и граф](packages/maind/docs/) · [continuous learning](packages/analyst/README.md).
- Развитие: [`roadmap/`](roadmap/) (напр. [Continuous Learning / самообучение](roadmap/self-learning-memory.md)).

## Разработка

Тесты/валидация — по пакету:

```bash
bash packages/skiller/scripts/validate.sh
bash packages/harness/scripts/validate.sh
bash packages/maind/scripts/validate.sh
```

Подробности — в `CLAUDE.md` корня и каждого пакета (+ `CONTRIBUTING.md`). Коммиты — Conventional Commits на русском.
