# Конфиг `.maind.json`

Главный конфиг узла — надмножество `.projects.json` из brain. Полный пример с
комментариями — [`.maind.example.json`](https://github.com/academici/maind/blob/main/.maind.example.json).
Валидация — на stdlib (без jsonschema): неизвестный топ-ключ фатален (с подсказкой через
difflib), неизвестный вложенный — предупреждение.

## Секции

| Секция | Назначение |
|:--|:--|
| `node` | идентификация узла: `id`, `name`, `role` (`primary`/`secondary`/`mirror`) |
| `memory` | `http_port`, `stream_port`, `data_dir`, `url`, `config_path` |
| `graph` | `adapter` (`federation` по умолчанию / `disabled`) — federation единственная раскладка |
| `agents` | `registry_enabled`, `heartbeat_interval_ms`, `max_idle_ms`, `definitions[]` |
| `projects[]` | проекты (см. ниже) |
| `namespaces` | необязательный реестр namespace-групп: `{ id: { name, description } }` |
| `integrations` | `swissknifeman`, `brain` (синк) |
| `mcp` | `servers[]` — внешние MCP-серверы узла |
| `observability` | `service_name`, `log_level`, `metrics_enabled`, `traces_enabled` |

## Проект

```jsonc
{
  // совместимо с brain (.projects.json)
  "id": "brain", "name": "Brain", "repo": "academici/brain",
  "local_path": "~/Vaults/Brain", "type": "obsidian-vault",
  // расширения maind
  "memory_scope": "project:brain",     // приватный бакет памяти проекта
  "agents": ["vault-architect"], "skills": [], "tags": ["docs"],
  "namespaces": ["axioma"],            // группы изоляции связей графа+памяти; ["*"] = общая инфраструктура
  "graph_store": "hub",                // hub (data/graphs/<id>.db) | local (<repo>/.maind/graph.db)
  "graphify": false,                   // включить код-MCP (граф кода); дефолт-движок Serena (uvx)
  "graphify_command": "uvx",           // опц. бинарь code-intelligence MCP (дефолт uvx → Serena)
  "graphify_args": ["..."],            // опц. аргументы; {root} → путь проекта
  "graphify_server_name": "serena",    // опц. имя сервера в .mcp.json (дефолт serena)
  "graphify_workspace": false,         // опц. единый граф: индексировать локальные пакеты (packages/*)
  "status": "active"                   // active | archived | planning
}
```

Обязательные для совместимости с brain поля: `id`, `name`, `repo`, `local_path`, `type`.
Остальное — расширения maind (brain их игнорирует при чтении fallback).

## Namespaces

`namespaces` у проекта изолируют межпроектные связи **и графа, и памяти**: ребро A↔B строится,
только если A и B делят хотя бы одну группу; факты памяти проекта видны внутри его namespace
(`ns:<имя>`) и изолированы между группами. Нет поля / `[]` → неявный `default`; `["*"]` →
общая инфраструктура, связывается со всеми группами. Подробнее — [Namespaces](/guide/namespaces).

## Дефолты

`merge_defaults` дописывает обязательные значения (`memory.http_port=4111`,
`graph.adapter=federation`, `agents.heartbeat_interval_ms=30000`,
`observability.service_name=maind` …), чтобы код никогда не ловил `KeyError`. Устаревший
`graph.adapter` (`memory`/`graphify`/`networkx`) принимается с предупреждением и нормализуется
в `federation`.

::: warning Порты
`memory.http_port`/`stream_port` — лишь дефолт; `.env` (`AGENTMEMORY_PORT`/
`AGENTMEMORY_STREAM_PORT`) их переопределяет. См. [Память](/guide/memory).
:::

Дальше: [Память →](/guide/memory)
