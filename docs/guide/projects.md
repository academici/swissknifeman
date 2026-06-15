# Проекты

Реестр проектов экосистемы — в `.maind.json` (надмножество brain `.projects.json`).

## Приоритет загрузки

```
.maind.json      (primary — если есть)
    ↓ fallback
.projects.json   (legacy brain — только чтение, с предупреждением о миграции)
    ↓
пустой конфиг
```

`load_config` возвращает `(config, source)`, где `source ∈ {".maind.json",
"brain-fallback", "empty"}` — чтобы было видно происхождение.

## CLI

```bash
maind projects list [--json]
maind projects sync --from brain [--path ~/Vaults/Brain]
```

`sync` идемпотентен: мерджит по `id`, обновляет brain-источные поля
(`name`/`local_path`/`vault_path`/`type`/`enabled`/`docs_folders`) и **сохраняет**
maind-only поля (`skills`/`tags`/`dependencies`/`agents`/`repo`).

## Маппинг из brain

Реальная схема brain — `{name, enabled, vault_path, repo, folders}` (поля `id`/`local_path`/
`type` из старого описания в brain отсутствуют — синтезируются):

| brain | maind | правило |
|:--|:--|:--|
| `name` | `name`, `id` | `id` = slug от `name` |
| `repo` | `local_path` | путь к коду |
| `vault_path` | `vault_path` | как есть |
| `folders` | `docs_folders` | как есть |
| — | `type` | по маркерам репозитория (composer.json→php, package.json→node, .obsidian→vault) |

Дальше: [Доверие (workspace) →](/guide/workspace)
