---
name: ecosystem-integration
description: Как подключить (онбордить) новый проект к экосистеме academici через хаб mAInd — общая память + граф + MCP-инструменты + скиллы. Используй, когда пользователь просит «подключи/онбордни проект X к экосистеме», «добавь проект в mAInd», «накати память и граф на репозиторий», или нужно починить/обновить уже подключённый проект.
---

# Подключение проекта к экосистеме academici

Хаб **mAInd** связывает проекты двумя механизмами (общая память + граф топологии) и раскатывает
в каждый проект MCP-серверы, скилл-ориентир и healthcheck. Всё это делается командами `maind`.
Запускай их из каталога хаба maind (или по абсолютному пути `bin/maind`).

## Подключить новый проект

```bash
maind onboard <path|id> [--with-code] [--with-brain] [--yes]
```

Цепочка (каждый шаг standalone-safe — отсутствие соседа не валит онбординг):

1. **register** — добавить проект в `.maind.json` (namespace по умолчанию пустой → задай вручную,
   см. ниже).
2. **skills** — `swissknifeman integrate` (скиллы + хуки), если не `--skip-skills`.
3. **deploy** — MCP-серверы хаба в `.mcp.json` проекта: `agentmemory` + `maind` [+ код-граф].
4. **graph** — `derive` графа топологии из composer/доков + пересборка индекса.
5. **memory** — seed-факт о связях в общей памяти.
6. **ecosystem-skill** — раскатать скилл `ecosystem-mcp` в проект (ориентир для его агента).

## Namespace (важно)

Связи и общая память изолируются по namespace. Свежесозданная запись попадает в `default` и
**не свяжется** с группой. Пропиши группу в `.maind.json` у проекта:

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
Linger` → `yes`). См. [systemd-гайд](../../docs/guide/systemd.md).

## Код-граф (граф кода в проекте) — универсальный

Отдельный per-project MCP графа КОДА (символы/ссылки/реализации). Движок по умолчанию —
**Serena** (language-agnostic, через `uvx`), работает для любого стека. Включается намерением:

```json
{ "id": "myproject", "code": true, ... }
```

`maind sync --project myproject --only mcp` допишет сервер `serena` в `.mcp.json` (нужен `uvx`
в PATH; нет — корректный пропуск `skipped-not-installed`, остальное работает). Движок
переопределяется на проект (`code_command` / `code_args` с `{root}` / `code_server_name`)
— например, стек-специфичный сервер. Подробнее — [граф кода](../../docs/guide/code-graph.md).

## Памятка

- Память **общая**: внутри namespace видна связанным проектам, между namespace изолирована.
- MCP пассивны: агент проекта сам вызывает `recall`/`store`/graph-инструменты — никакого
  автоматического «перехвата».
- Источник истины артефактов — шаблоны в maind (`templates/`), не правь копии в проектах.
