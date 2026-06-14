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
| `graph` | `adapter` (`memory`/`graphify`/`disabled`), `persist`, `persist_path` |
| `agents` | `registry_enabled`, `heartbeat_interval_ms`, `max_idle_ms`, `definitions[]` |
| `projects[]` | проекты (см. ниже) |
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
  "graph_node": true, "memory_scope": "project:brain",
  "agents": ["vault-architect"], "skills": [], "tags": ["docs"],
  "status": "active",                  // active | archived | planning
  "dependencies": ["maind"]            // id других проектов → рёбра depends_on
}
```

Обязательные для совместимости с brain поля: `id`, `name`, `repo`, `local_path`, `type`.
Остальное — расширения maind (brain их игнорирует при чтении fallback).

## Дефолты

`merge_defaults` дописывает обязательные значения (`memory.http_port=4111`,
`graph.adapter=memory`, `agents.heartbeat_interval_ms=30000`,
`observability.service_name=maind` …), чтобы код никогда не ловил `KeyError`.

::: warning Порты
`memory.http_port`/`stream_port` — лишь дефолт; `.env` (`AGENTMEMORY_PORT`/
`AGENTMEMORY_STREAM_PORT`) их переопределяет. См. [Память](/guide/memory).
:::

Дальше: [Миграция →](/guide/migration)
