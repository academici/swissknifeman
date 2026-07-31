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
| `providers` | необязательные fleet defaults provider selection; точный контракт ниже |
| `namespaces` | необязательный реестр namespace-групп: `{ id: { name, description } }` |
| `integrations` | `swissknifeman`, `brain` (синк) |
| `mcp` | `servers[]` — внешние MCP-серверы узла; `emit_example` (default-on `.mcp.json.example`, opt-out `false`); `perplexity_web` — hub-managed раскатка keyless-моста perplexity-web (см. ниже) |
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

### Дополнительные provider-managed MCP-серверы

Проект может объявить дополнительные серверы, которыми владеет другой package, в
`projects[].mcp.extra_servers`. `maind deploy` добавляет их в единый semantic inventory
вместе со своими `maind`/memory/code серверами, проверяет дубликаты ID до записи и затем
передаёт их provider-managed renderer. Значения — native MCP-объекты (`command`, `args`,
`env` и т. п.); их owner отвечает за содержимое и lifecycle.

```jsonc
"mcp": {
  "extra_servers": {
    "analytics-capture": {
      "command": "python3",
      "args": [".codex/hooks/analytics-capture.py"]
    }
  }
}
```

`extra_servers` не может переопределять IDs, уже принадлежащие `maind`, memory, code graph
или включённым интеграциям: такой конфликт останавливает deploy до изменения target-файлов.

Старые имена `graphify` / `graphify_command` / `graphify_args` / `graphify_server_name` /
`graphify_workspace` принимаются как **legacy-alias** (обратная совместимость).

## Provider selection

Необязательный `providers.defaults` задаёт fleet-слой выбора провайдера, а
`projects[].providers` — более сильный слой для точного project ID. Каждый слой следует
одному provider-config v1 contract (`contract_version` и непустой `selection`), совместимому
с project-owned `.swissknife.json#/providers`. При отсутствии всех provider-слоёв результат
остается legacy Claude Code-only и ничего не записывается на диск.

Точный порядок precedence: operation override → project `.swissknife.json` →
`projects[].providers` → `providers.defaults` → synthetic legacy. Provider selection
валидируется и возвращает provenance/diagnostics; он не включает provider, не генерирует
артефакты и не меняет существующий `config.json` сам по себе.

Обязательные для совместимости с brain поля: `id`, `name`, `repo`, `local_path`, `type`.
Остальное — расширения maind (brain их игнорирует при чтении fallback).

### Три слоя каталога и владелец факта

Каталог проектов существует в **трёх представлениях** с одним направлением синка
(`integrations.brain.sync_direction:"import"`):

| Слой | Файл | Владеет фактом |
|:--|:--|:--|
| **Источник** | frontmatter control-нот Brain (`<Name>.md`) | какие проекты есть, `repo:` (путь к коду), doc-папки, **`visibility`** (`docs_public`) |
| **Кэш** | `<vault>/.projects.json` (генерируется brain, gitignored) | машинная проекция frontmatter — руками не править |
| **Реестр тулинга** | этот `config.json` | импортирует каталог + добавляет maind-поля (`namespaces`/`type`/`graph`/`mcp`) |

Каталожные поля (`name`, `local_path`, `vault_path`, `type`, `enabled`, `docs_folders`) приходят
в `config.json` **импортом** (`maind projects sync --from brain`) — меняй их во frontmatter Brain,
не здесь (синк перетрёт; смена `visibility` существующего проекта сопровождается warn).
maind-only проекты (которых нет в Brain) владеют этими полями сами.

**`repo` ≠ `local_path`** (намеренный мост между схемами, не путать): в `config.json` `repo` —
GitHub-slug `owner/name`, путь к коду — `local_path`. В brain-схеме `.projects.json` `repo` = **путь
к коду** (slug'а там нет); при импорте maind кладёт его в `local_path`, а `repo` оставляет под slug.
`visibility` в `docs_folders` — **кэш** из frontmatter Brain (maind его для поведения не читает).

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

Игноры `vendor`/`packages` и пр. — **здесь**, а не захардкожены. См. [Граф кода](./code-graph).

## Секция `mcp.perplexity_web` (раскатка keyless-моста)

Keyless-мост **perplexity-web** (отдельный Node-пакет, поиск Perplexity через браузерный профиль)
раздаётся в проекты тем же `deploy`/`sync`, что `maind` и Serena — единым источником истины, а не
ручной хардкод-записью в каждом `.mcp.json`. **opt-in, disabled-by-default**: без секции сервер не
раскатывается.

```jsonc
"mcp": {
  "perplexity_web": {
    "enabled": true,                     // глобальный фан-аут на все проекты
    "pool": "default",                   // модель пулов браузера (см. ниже)
    "bin": "/abs/path/to/perplexity-web-mcp/start.sh"  // fallback-путь к start.sh
  }
}
```

**Пул** = демон + профиль + окно браузера. Только `default` переиспользует текущий логин; любой
другой пул получает свой профиль и требует **отдельного логина** в Perplexity. Демон уже гонит до
`maxConcurrency` поисков параллельно (вкладки), поэтому изоляция нужна лишь под раздельные аккаунты:

| `pool` | Пул проекта | Логины |
|:--|:--|:--|
| `"default"` (или любой литерал) | общий пул для всех | один (текущий) |
| `"per-namespace"` | `ns-<первый namespace>` | по логину на группу |
| `"per-project"` | `<id проекта>` | по логину на проект |

Per-project override: `projects[].perplexity_web` (`true`/`false` — форс вкл/выкл) и
`projects[].perplexity_web_pool` (литеральное имя пула). Команда пишется через индирекцию
`${PERPLEXITY_WEB_MCP_BIN:-<bin>}` (как `${MAIND_BIN:-maind}`) — переносимо между машинами/CI,
без захардкоженного `/home/...` в `.mcp.json`.

## Namespaces

`namespaces` у проекта изолируют межпроектные связи **и графа, и памяти**: ребро A↔B строится,
только если A и B делят хотя бы одну группу; факты памяти проекта видны внутри его namespace
(`ns:<имя>`) и изолированы между группами. Нет поля / `[]` → неявный `default`; `["*"]` →
общая инфраструктура, связывается со всеми группами. Подробнее — [Namespaces](./namespaces).

## Дефолты

`merge_defaults` дописывает обязательные значения (`memory.http_port=4111`,
`graph.adapter=federation`, `agents.heartbeat_interval_ms=30000`,
`observability.service_name=maind` …), чтобы код никогда не ловил `KeyError`. Устаревший
`graph.adapter` (`memory`/`graphify`/`networkx`) принимается с предупреждением и нормализуется
в `federation`.

::: warning Порты
`memory.http_port`/`stream_port` — лишь дефолт; `.env` (`AGENTMEMORY_PORT`/
`AGENTMEMORY_STREAM_PORT`) их переопределяет. См. [Память](./memory).
:::

Дальше: [Память →](./memory)
