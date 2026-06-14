# Архитектура

**mAInd** — вершина иерархии экосистемы. Один общий хаб композирует три слоя под одним
конфигом `.maind.json` и одним CLI. Остальные проекты подключаются к нему как клиенты.

## Топология: единый хаб + scopes

```mermaid
graph TD
  subgraph hub["maind hub (этот пакет)"]
    M["agent-memory daemon<br/>Node · 4111/4112<br/>ns: project:* · global"]
    G["graph.db<br/>ОДИН общий граф (stdlib)"]
    R["~/.maind<br/>agents.json · projects.json"]
    MCP["maind mcp<br/>stdio JSON-RPC · 6 tools"]
  end
  brain -->|MCP/HTTP, ns project:brain| hub
  swissknifeman -->|MCP/HTTP, ns project:swissknifeman| hub
  erp["erp-sdk · …"] -->|MCP/HTTP| hub
```

Изоляция между проектами — **логическая** (по `namespace`/scope), а не отдельными
демонами. Демон памяти **не** запускается на каждый проект — один на хаб.

## Три слоя

```mermaid
flowchart LR
  CLI["bin/maind (bash) → python3 -m maind"] --> cli["cli.py · COMMANDS"]
  cli --> mem["memory.py"] & gr["graph.py"] & ag["agents.py"] & pr["projects.py"] & mcp["mcp.py"]
  mem -->|HTTP| daemon["agent-memory (Node)"]
  gr -->|node-link JSON| db[("data/graph.db")]
  ag -->|atomic JSON| aj[("~/.maind/agents.json")]
  pr -->|читает/пишет| cfg[(".maind.json")]
  mcp --> mem & gr & ag & pr
```

- **Память** (`memory.py`) — оркестрирует внешний Node-демон `@agentmemory/agentmemory`
  (start/stop/status, health-poll, pidfile) и говорит по HTTP со scope'ами. Демон —
  зависимость, не переписывается на Python.
- **Граф** (`graph.py`) — stdlib property-граф (BFS-соседи, кратчайший путь, подграф,
  статистика), персист в node-link JSON. `networkx`/`graphify` — опциональные адаптеры.
- **Агенты** (`agents.py`) — реестр в `~/.maind/agents.json`; состояние выводится из
  возраста heartbeat и живости pid.
- **Проекты** (`projects.py`) — `.maind.json` (надмножество brain `.projects.json`),
  fallback на legacy, синк из brain.
- **MCP** (`mcp.py`) — публикует всё это как stdio JSON-RPC сервер для внешних агентов.

## Как строится «общая связь»

На `maind start` / `maind migrate from-brain` проекты из конфига регистрируются как узлы
графа, а поля `dependencies` / `skills` / `agents` материализуются в рёбра
`depends_on` / `uses` / `belongs_to`. Обход графа (`maind graph query --from project:brain
--depth 2`) показывает межпроектные связи — это и есть единый источник истины о топологии.

## Почему Python + bash

Ровно как `swissknifeman` и `brain`: тонкий лаунчер `bin/maind` проверяет окружение и
вызывает `python3 -m maind <root> <cmd>`; логика — в `lib/maind/*.py` на stdlib (тестируемо,
без сторонних зависимостей). Это держит узел переносимым и предсказуемым.
