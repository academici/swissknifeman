---
name: ecosystem-integration
bucket: repository-bootstrap
version: 0.1.0
description: "Как подключить (онбордить) новый проект к экосистеме academici через хаб mAInd — общая память + граф + MCP-инструменты + скиллы. Используй, когда пользователь просит «подключи/онбордни проект X к экосистеме», «добавь проект в mAInd», «накати память и граф на репозиторий», или нужно починить/обновить уже подключённый проект."
risk: draft
persona: oss-dev
tags: [ecosystem, maind, onboarding, root-bootstrap]
requires: []
produces_for: []
outputs: [chat]
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Подключение проекта к экосистеме academici

Хаб **mAInd** связывает проекты двумя механизмами (общая память + граф топологии) и раскатывает
в каждый проект MCP-серверы, скилл-ориентир и healthcheck. Всё это делается командами `maind`.
Запускай их из каталога хаба maind (или по абсолютному пути `bin/maind`).

## Дерево решений (до онбординга)

Полное дерево сценариев настройки (10 слоёв, с условными ветками) — канонический документ
[«Дерево решений: настройка проекта»](../../../../../packages/maind/docs/guide/onboarding-decision-tree.md). Кратко
перед запуском реши: **тип** (детект → профиль; не распознан → не «всё подряд», выбери явно) →
**память** (maind/native/off) → **namespaces** (общий + личный) → **канал скиллов** (connect/vendor —
СПРОСИ) → **бакеты** (оптимально под стек, не максимально) → **окружение/граф**. Главное правило:
подбирай оптимальный набор; неочевидно — спроси пользователя.

## Подключить новый проект

```bash
maind onboard <path|id> [--with-code] [--with-brain] [--yes]
```

Цепочка (каждый шаг standalone-safe — отсутствие соседа не валит онбординг):

1. **register** — добавить проект в `config.json` (namespace по умолчанию пустой → задай вручную,
   см. ниже).
2. **skills** — `skiller integrate` (скиллы + хуки), если не `--skip-skills`. ⚠️ swissknifeman
   ставит скиллы **двумя каналами** — `connect` (плагины-бакеты, не в репо) и `vendor` (физический
   перенос конкретных скиллов в репо через `.swissknifeman/config.json` + `skiller sync`).
   **Спроси у пользователя канал** перед установкой (визард `integrate` тоже спрашивает). Операционные
   детали и Boost-как-MCP — в [project-tooling-runbook].
3. **deploy** — MCP-серверы хаба в `.mcp.json` проекта: `agentmemory` + `maind` [+ код-граф].
   ⚠️ `.mcp.json` несёт **абсолютные локальные пути** (`bin/maind`, путь проекта Serena) → коммитить
   как есть нельзя. Гигиена (индирекция через `.env` либо gitignore + синхронный `.example`) —
   [project-tooling-runbook] §«Гигиена machine-specific конфигов».
4. **graph** — `derive` графа топологии из composer/доков + пересборка индекса.
5. **memory** — seed-факт о связях в общей памяти.
6. **ecosystem-skill** — раскатать скилл [ecosystem-mcp] в проект (ориентир для его агента).

[project-tooling-runbook]: ../project-tooling-runbook/SKILL.md
[ecosystem-mcp]: ../ecosystem-mcp/SKILL.md

## Namespace (важно)

Связи и общая память изолируются по namespace. Свежесозданная запись попадает в `default` и
**не свяжется** с группой. Пропиши группу в `config.json` у проекта:

```json
{ "id": "myproject", "namespaces": ["axioma"], ... }
```

`["*"]` — общая инфраструктура (видна всем группам). После правки — пересобери граф:
`maind sync --namespace axioma --only graph`.

## Обновить / починить уже подключённый

```bash
maind sync --project <id> --mode auto      # переката все артефакты (mcp/graph/memory/health*/skill)
maind sync --project <id> --only mcp       # только MCP-серверы
maind sync --all                            # все enabled-проекты
```

## Проверить результат

```bash
maind health --project <id>     # connected | partial | standalone (+ подсказки)
maind health --cwd --fix        # из каталога проекта: поднять память + дописать MCP
maind graph --project <id>      # граф проекта и соседи
```

`partial` обычно значит «демон памяти не запущен» → `maind start --only memory` (или
зарегистрируй сервис: `maind service install`).

Демон под systemd стартует при логине; чтобы поднимался **при загрузке ОС** (сервер по SSH) —
разово включи linger: `loginctl enable-linger $USER` (проверка: `loginctl show-user $USER -p
Linger` → `yes`). См. [systemd-гайд](../../../../../packages/maind/docs/guide/systemd.md).

## Drift-gate — обязательно перед тем, как считать онбординг/интеграцию завершённой

Managed-скиллы (vendor-канал skiller + `ecosystem-mcp`/`ecosystem-setup` от maind) со временем
улучшаются в реестре/шаблонах, но уже онбордженным проектам это НЕ прилетает само — раскатка
одноразовая. Без финальной проверки частичные `--only`-синки незаметно копят дрейф (инцидент:
у agelto `ecosystem-mcp` не знал про Serena 2 недели — агент читал файлы напрямую вместо графа).

```bash
skiller doctor --vendor-drift     # какие vendor-проекты отстали от реестра skiller (add/update/remove)
maind doctor --skill-drift        # какие проекты отстали от шаблонов ecosystem-mcp/ecosystem-setup
```

Оба read-only и по умолчанию (без флагов) дают одну summary-строку в обычном `doctor`. Проект
из отчёта → `skiller sync` (из его каталога) и/или `maind sync --project <id> --only
ecosystem-skill,setup-skill`. Гоняй это после любого точечного (`--only`) онбординга/интеграции,
не только после полного `maind onboard`.

## Код-граф (граф кода в проекте) — универсальный

Отдельный per-project MCP графа КОДА (символы/ссылки/реализации). Движок по умолчанию —
**Serena** (language-agnostic, через `uvx`), работает для любого стека. Включается намерением:

```json
{ "id": "myproject", "code": true, ... }
```

`maind sync --project myproject --only mcp` допишет сервер `serena` в `.mcp.json` (нужен `uvx`
в PATH; нет — корректный пропуск `skipped-not-installed`, остальное работает). Движок
переопределяется на проект (`code_command` / `code_args` с `{root}` / `code_server_name`)
— например, стек-специфичный сервер. Подробнее — [граф кода](../../../../../packages/maind/docs/guide/code-graph.md).

## Памятка

- Память **общая**: внутри namespace видна связанным проектам, между namespace изолирована. Но
  **дайджест на старте сессии этим общим контекстом не делится по умолчанию** (`shared_max=0`,
  D10) — только `project:<id>`; общий контекст группы поднимается ЯВНО `recall --scope ns:<имя>`,
  когда задача реально межпроектная (гайдлайн — скилл [ecosystem-mcp] → «Межпроектная задача»,
  доктрина — [docs/guide/memory.md](../../../../../packages/maind/docs/guide/memory.md)).
- MCP пассивны: агент проекта сам вызывает `recall`/`store`/graph-инструменты — никакого
  автоматического «перехвата».
- Источник истины артефактов — шаблоны в maind (`templates/`), не правь копии в проектах.

## Провенанс (root-bootstrap, P1.2)

Класс A private/source-only root-bootstrap identity (D31/D38, `plans/2026.07.24-AGENT-RELIABILITY`):
канонический источник — этот файл; тонкие проекции — `.claude/skills/ecosystem-integration/SKILL.md`
и `.agents/skills/ecosystem-integration/SKILL.md` (генерируются `skiller registry`, не редактируются
руками). Бакет `repository-bootstrap` — приватный, не публикуется как обычный unit/core/marketplace,
не вендорится/коннектится в проекты-потребители.
