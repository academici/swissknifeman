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
maind onboard <path|id> [--with-graphify] [--with-brain] [--yes]
```

Цепочка (каждый шаг standalone-safe — отсутствие соседа не валит онбординг):

1. **register** — добавить проект в `.maind.json` (namespace по умолчанию пустой → задай вручную,
   см. ниже).
2. **skills** — `swissknifeman integrate` (скиллы + хуки), если не `--skip-skills`.
3. **deploy** — MCP-серверы хаба в `.mcp.json` проекта: `agentmemory` + `maind` [+ `graphify`].
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

## Код-граф (graphify) — опционально

graphify — отдельный per-project MCP-сервер графа КОДА. На текущий момент бинаря `graphify-mcp`
в системе нет, поэтому слой **опционален**. Включается намерением в `.maind.json`:

```json
{ "id": "myproject", "graphify": true, ... }
```

При следующем `maind sync --project myproject --only mcp` graphify добавится в `.mcp.json`,
**если** бинарь установлен; иначе — корректный пропуск (`skipped-not-installed`), остальное
работает. Можно указать свой code-intelligence MCP полем `"graphify_command": "<команда>"`.

## Памятка

- Память **общая**: внутри namespace видна связанным проектам, между namespace изолирована.
- MCP пассивны: агент проекта сам вызывает `recall`/`store`/graph-инструменты — никакого
  автоматического «перехвата».
- Источник истины артефактов — шаблоны в maind (`templates/`), не правь копии в проектах.
