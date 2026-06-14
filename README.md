# mAInd

> Центральный узел экосистемы academici: **память агентов · граф связей · реестр агентов и проектов · MCP-сервер**.

**mAInd** — это «мозг» экосистемы. Один общий хаб хранит долгосрочную память агентов,
строит граф связей между сущностями (проекты, агенты, память, скиллы) и координирует
реестр запущенных агентов. Остальные проекты (`brain`, `swissknifeman`, …) подключаются
к нему как клиенты.

Ядро — **Python + bash** (как `swissknifeman` и `brain`): тонкий лаунчер `bin/maind`,
вся логика в `lib/maind/*.py` на stdlib, тесты на `unittest`. npm нужен только для
Node-демона памяти и сборки документации.

---

## Топология: единый хаб + scopes

```
                 ┌──────────────── maind hub ────────────────┐
                 │  agent-memory daemon (Node, 4111/4112)    │
   maind start ─▶│   ns: project:brain · project:skm · global │
                 │  graph.db  (ОДИН общий граф, stdlib)       │
                 │  ~/.maind/  agents.json · projects.json    │
                 │  maind mcp  (stdio JSON-RPC: 6 tools)      │
                 └───────▲────────────▲────────────▲──────────┘
            MCP/HTTP     │            │            │
                      brain     swissknifeman   erp-sdk …   (клиенты, изоляция по namespace)
```

- **Память** — один Node-демон `@agentmemory/agentmemory`; изоляция между проектами по
  `namespace` (scope), а не отдельными демонами. Общие факты — в scope `global`.
- **Граф** — один на всю экосистему: проект → `depends_on` → проект, память →
  `belongs_to` → проект, агент → `belongs_to` → проект, проект → `uses` → скилл. Это и
  есть «общая связь».
- **Порты не хардкодятся** — берутся из `.env` / `.maind.json` (дефолт 4111/4112), чтобы
  не конфликтовать с другим узлом.

---

## Установка

```bash
git clone <repo> maind && cd maind
./install.sh                       # симлинк ~/.local/bin/maind + каталог ~/.maind
maind doctor                       # проверка окружения

# Память (опционально, нужен Node):
npm install                        # ставит @agentmemory/agentmemory
cp .env.example .env               # порты узла
maind start --only memory
```

## Быстрый старт

```bash
maind migrate from-brain ~/Vaults/Brain/.projects.json   # импорт проектов + граф
maind start                         # поднять память + граф
maind status                        # сводка узла
maind graph query --from project:brain --depth 2
maind projects list
```

---

## CLI

| Команда | Назначение |
|:--|:--|
| `maind start [--only memory\|graph]` | поднять воркеры узла |
| `maind status [--json]` | сводка: память, граф, агенты, проекты |
| `maind memory <start\|stop\|status>` | жизненный цикл демона памяти |
| `maind graph <query\|stats\|neighbors>` | обход графа связей |
| `maind agents <list\|register\|heartbeat\|kill>` | реестр агентов |
| `maind projects <list\|sync --from brain>` | реестр проектов |
| `maind migrate <from-brain\|from-agentmemory>` | импорт из brain / agent-memory |
| `maind mcp` | запустить maind как MCP-сервер (stdio) |
| `maind doctor` | диагностика окружения |

---

## Конфиг `.maind.json`

Главный конфиг узла — надмножество `.projects.json` из `brain`. Если `.maind.json` нет,
maind читает legacy `.projects.json` в режиме read-only (с предупреждением о миграции).
Полная схема — в [.maind.example.json](.maind.example.json). Ключевые секции: `node`,
`memory`, `graph`, `agents`, `projects[]`, `integrations`, `mcp`, `observability`.

## Память (scopes)

HTTP-контракт демона (agentmemory 0.9.x, сверено вживую): `GET /agentmemory/health` ·
`POST /agentmemory/remember {namespace, content, type}` ·
`POST /agentmemory/search {query, namespace}`. maind оркестрирует демон
(`start/stop/status`) и говорит по HTTP, скоупя запросы по namespace проекта
(`project:<id>`) или `global`.

## Граф

Движок по умолчанию — чистый stdlib (BFS-соседи, кратчайший путь, подграф, статистика),
персист в node-link JSON (`data/graph.db`). `networkx`/`graphify` подключаются как
опциональные адаптеры через `graph.adapter`.

## MCP

`maind mcp` — stdio JSON-RPC сервер. Tools: `maind_memory_store`, `maind_memory_recall`,
`maind_graph_query`, `maind_graph_neighbors`, `maind_agents_list`, `maind_projects_list`.
Подключение клиента (`.mcp.json`):

```json
{ "mcpServers": { "maind": { "command": "<repo>/bin/maind", "args": ["mcp"] } } }
```

---

## Разработка

```bash
scripts/test.sh          # unittest (без сторонних зависимостей и без живого демона)
scripts/validate.sh      # py_compile + bash -n + JSON + тесты
npm run docs:dev         # документация (VitePress)
```

Конвенции: stdlib-only Python, контекст через `Env` (без модульных глобалей), атомарная
запись JSON, русскоязычные сообщения. Подробнее — [CONTRIBUTING.md](CONTRIBUTING.md).

## Лицензия

[MIT](LICENSE) © 2026 Dmitry Vostrikov
