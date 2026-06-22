# Проекты

Реестр проектов экосистемы — в `config.json` (в корне монорепо, надмножество brain
`.projects.json`).

## Приоритет загрузки

```
config.json      (primary — в корне монорепо, если есть)
    ↓ fallback
.maind.json      (legacy-имя того же конфига — обратная совместимость)
    ↓ fallback
.projects.json   (legacy brain — только чтение, с предупреждением о миграции)
    ↓
пустой конфиг
```

`load_config` возвращает `(config, source)`, где `source ∈ {"config.json", ".maind.json",
"brain-fallback", "empty"}` — чтобы было видно происхождение.

## CLI

```bash
maind projects list [--namespace NS] [--json]
maind projects sync --from brain [--path ~/Vaults/Brain]
maind namespaces [--json]            # namespace-группы и их проекты-члены
```

`sync` идемпотентен: мерджит по `id`, обновляет brain-источные поля
(`name`/`local_path`/`vault_path`/`type`/`enabled`/`docs_folders`) и **сохраняет**
maind-only поля (`skills`/`tags`/`namespaces`/`dependencies`/`agents`/`repo`).

## Namespaces

Поле `projects[].namespaces` группирует проекты и **изолирует** межпроектные связи: ребро
строится только между проектами одной группы (`["*"]` — общая инфраструктура, связывается со
всеми). `--namespace NS` фильтрует `projects list`/`status` и `sync`. Подробнее —
[Архитектура → Namespaces](../architecture#namespaces-изоляция-связей).

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

Дальше: [Миграция →](./migration)
