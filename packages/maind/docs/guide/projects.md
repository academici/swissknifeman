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
maind projects health [--project ID | --namespace NS | --all] --evidence-set FILE --json
maind projects sync --from brain [--path ~/Vaults/Brain]
maind namespaces [--json]            # namespace-группы и их проекты-члены
```

`sync` идемпотентен: мерджит по `id`, обновляет brain-источные поля
(`name`/`local_path`/`vault_path`/`type`/`enabled`/`docs_folders`) и **сохраняет**
maind-only поля (`skills`/`tags`/`namespaces`/`dependencies`/`agents`/`repo`).

## Provider health

`projects health` — read-only exact-set проверка по frozen `provider-health-v1`. Файл
`--evidence-set` фиксирует sealed project/provider/axis requirements и redacted evidence
identities; mAInd дополняет package-owned наблюдения только через публичные worktree-local CLI с
ограниченным timeout. Команда не читает provider targets как intent и ничего не исправляет.

`aggregate=green` возможен только при точном совпадении project set и полном свежем покрытии всех
required provider/axis rows. Missing/extra/duplicate project или provider, timeout, malformed JSON,
stale/unknown evidence, required unsupported capability и успешный только один provider остаются
явным `non-green`. Корректно построенный `non-green` отчёт означает, что проверка выполнена, но не
является разрешением на rollout или repair.

Durable JSON содержит только стабильные project/provider/axis/source/evidence identities и
диагностики; absolute roots, secrets и raw subprocess output отклоняются.

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
