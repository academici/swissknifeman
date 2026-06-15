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

## Топология: единый хаб + namespace'ы

```
                 ┌──────────────────── maind hub ─────────────────────┐
                 │  agent-memory daemon (Node, 4111/4112)             │
   maind start ─▶│   бакеты: project:<id> · ns:<имя> · global          │
                 │  data/graphs/*  (граф на проект + _index.db, stdlib)│
                 │  ~/.maind/  agents.json · projects.json             │
                 │  maind mcp  (stdio JSON-RPC: 11 tools)              │
                 └───────▲────────────▲────────────▲──────────────────┘
            MCP/HTTP     │            │            │
                      brain     swissknifeman   erp-sdk …   (клиенты, изоляция по namespace)
```

Через хаб идут **два независимых механизма связывания**, оба работают по namespace'ам:

- **agent-memory** (память/контекст) — один Node-демон; изоляция логическая, по бакетам:
  `project:<id>` (приватно) · `ns:<имя>` (группа) · `global` (вся экосистема). Внутри группы
  память общая, между группами изолирована.
- **maind-граф** (топология между проектами) — федерация: граф на проект (`data/graphs/<id>.db`)
  + тонкий `_index.db`. Строится из источников истины (`derive`: composer/Brain/override/skills),
  не из ручного дубля. Межпроектное ребро — только внутри общего namespace.
- **graphify** (граф кода внутри проекта) — со-равный механизм, раскатывается отдельным
  MCP-сервером (`deploy --with-graphify`).
- **Порты не хардкодятся** — из `.env` / `.maind.json` (дефолт 4111/4112), чтобы не
  конфликтовать с другим узлом.

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
(`start/stop/status`) и говорит по HTTP, скоупя запросы по бакетам проекта
(`project:<id>` · `ns:<имя>` · `global`).

## Граф

Движок — чистый stdlib (BFS-соседи, кратчайший путь, подграф, статистика), персист в
node-link JSON. Раскладка — **федерация**: граф на проект (`data/graphs/<id>.db`) + тонкий
регенерируемый `_index.db`; строится из источников истины (`derive`), читается через единый
фасад `federation.graph_reader`. `graph.adapter`: `federation` (по умолчанию) | `disabled`.

## MCP

`maind mcp` — stdio JSON-RPC сервер (11 tools): память (`store`/`recall`/`forget`), граф
(`query`/`neighbors`/`path`/`project`), `memory_links`, `agents_list`, `projects_list`,
`projects_status`. Подключение клиента (`.mcp.json`):

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
