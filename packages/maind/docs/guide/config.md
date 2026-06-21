# Конфиг `config.json`

Главный конфиг узла — `config.json` **в корне монорепо** (не в пакете maind);
резолвер поднимается вверх до каталога с `packages/`. Legacy-имя `.maind.json`
по-прежнему подхватывается для обратной совместимости. Надмножество `.projects.json`
из brain. Полный пример с комментариями —
[`config.example.json`](https://github.com/academici/maind/blob/main/config.example.json).
Валидация — на stdlib (без jsonschema): неизвестный топ-ключ фатален (с подсказкой через
difflib), неизвестный вложенный — предупреждение.

## Секции

| Секция | Назначение |
|:--|:--|
| `node` | идентификация узла: `id`, `name`, `role` (`primary`/`secondary`/`mirror`) |
| `memory` | `http_port`, `stream_port`, `data_dir`, `url`, `config_path` |
| `graph` | `adapter` (`federation` по умолчанию / `disabled`) — federation единственная раскладка |
| `code_graph` | политика графа кода: `command`/`args`/`server_name`, `ignores`/`workspace_ignores`, `language_by_type`, `initial_prompt`/`workspace_prompt`, `pre_index`, `feature_log_hook` (см. ниже) |
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
  "code": false,                       // включить граф кода (legacy-alias graphify); движок из секции code_graph
  "code_command": "uvx",               // опц. бинарь code-MCP (override дефолта из code_graph)
  "code_args": ["..."],                // опц. аргументы; {root} → путь проекта
  "code_server_name": "serena",        // опц. имя сервера в .mcp.json
  "code_workspace": false,             // опц. override авто-режима «единый граф с packages/*» (авто, если есть packages/)
  "code_ignores": ["vendor"],          // опц. per-project список игноров (иначе из code_graph)
  "status": "active"                   // active | archived | planning
}
```

Старые имена `graphify` / `graphify_command` / `graphify_args` / `graphify_server_name` /
`graphify_workspace` принимаются как **legacy-alias** (обратная совместимость).

Обязательные для совместимости с brain поля: `id`, `name`, `repo`, `local_path`, `type`.
Остальное — расширения maind (brain их игнорирует при чтении fallback).

## Секция `code_graph` (политика графа кода)

Вся политика графа кода — **в конфиге, не в коде** (правишь здесь, а не в исходниках maind).
`merge_defaults` накладывает дефолты, так что блок необязателен; задавай только то, что меняешь.

```jsonc
"code_graph": {
  "command": "uvx",                    // движок (по умолчанию Serena через uvx)
  "args": ["...","--project","{root}"],// {root} → путь проекта
  "server_name": "serena",             // имя сервера в .mcp.json проекта
  "language_by_type": { "php-package": "php", "node-package": "typescript" },
  "ignores": ["vendor","node_modules","packages","..."],          // дефолтный режим
  "workspace_ignores": ["vendor","**/vendor","..."],              // режим единого графа (packages не игнорим)
  "pre_index": true,                   // фоновая прогрев-индексация при включении
  "feature_log_hook": true             // SessionEnd-хук фиксации коммитов в общую память
}
```

Игноры `vendor`/`packages` и пр. — **здесь**, а не захардкожены. См. [Граф кода](/guide/code-graph).

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
