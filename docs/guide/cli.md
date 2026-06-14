# CLI swissknifeman

`bin/swissknifeman` — единая точка входа: подключение проектов, обновление,
диагностика и мейнтенанс реестра. Устанавливается симлинком в `~/.local/bin`
(см. [Установка](./installation)); путь к реестру определяет сам через
`readlink` собственного файла — никакой конфигурации пути нет.

## Команды для проектов

Все команды находят корень проекта автоматически — подъёмом вверх от текущей
директории до ближайшего маркера: `.swissknife.json` → `.claude/` → `.git`
(каталог или файл — worktree и submodule считаются). Ближайший маркер
побеждает: submodule — это свой проект; чтобы сместить корень, положите
`.swissknife.json` в нужный каталог. Внутри самого реестра project-команды
отказываются работать.

### `swissknifeman connect`

Подключает проект к нативному plugin marketplace Claude Code: пишет
`extraKnownMarketplaces.swissknifeman` и `enabledPlugins."<bucket>@swissknifeman"`
в `.claude/settings.local.json`. Merge-only: явный `false` не перетирается,
включённое сверх профиля не отключается, бэкап в `*.bak`.

```
swissknifeman connect [--profile P | --plugins a,b]
                      [--file settings.json|settings.local.json]
                      [--cleanup-vendored] [--list] [--dry-run] [--hub]
```

### `swissknifeman vendor`

Вендорит скиллы в проект (Cursor и другие агенты): профили, автодетект,
транзитивный резолв `requires`, манифест-переустановка — см.
[Установка](./installation) и [Вендоринг](./vendor-skills).

```
swissknifeman vendor [--agent claude|cursor|generic]
                     [--profile P | --buckets a,b] [--exclude x,y]
                     [--skills-path P] [--list] [--dry-run] [--force] [--hub]
```

### `swissknifeman update [--all] [--dry-run]`

Обновляет подключение проекта. Диск — источник истины: каналы определяются
по маркерам (`extraKnownMarketplaces.swissknifeman` в `.claude/settings*.json`;
`.swissknifeman-manifest.json` в `skills_path` / `.claude/skills` /
`.cursor/skills` / `.ai/skills`), проект может быть на обоих каналах сразу.

- **marketplace**: чинит путь к реестру, если репозиторий переехал
  (с бэкапом), доливает плагины, появившиеся в профиле, регенерирует хаб,
  показывает HEAD SHA реестра и предупреждает о незакоммиченных скиллах
  (marketplace видит только коммиты).
- **vendor**: чистая переустановка по манифесту — удалённые/переименованные
  в реестре скиллы убираются из проекта.

::: warning Чистая переустановка удаляет ранее вендоренные скиллы
`vendor` (и `update`) читает `.swissknifeman-manifest.json` и **удаляет** скиллы,
которые были вендорены ранее, но больше не входят в текущий набор реестра
(скилл убрали/переименовали в реестре, либо он выпал из выбора `--buckets`/
`--exclude`). Это касается и **незакоммиченных** локальных копий с тем же путём.
Проектные скиллы, которые нужно сохранить, **держите в git** (или вне
`skills_path`/манифеста); при Boost их копии остаются в `.cursor/skills`,
`.claude/skills` и восстанавливаются оттуда. Превью удаляемого — `--dry-run`.
:::

Проект с маркерами, но без записи в `projects.json`, регистрируется
автоматически (adopt) — карта проектов самовосстанавливается.
`--all` обходит все зарегистрированные проекты, пропуская отсутствующие
каталоги, и печатает сводку.

### `swissknifeman status`

Read-only отчёт: корень и маркер, каналы, дрейф плагинов относительно профиля,
переехавший путь marketplace, состояние вендоренных скиллов, SHA реестра.

### `swissknifeman list [--prune]`

Таблица зарегистрированных проектов со статусом `ok|missing`. Записи никогда
не удаляются автоматически — только явный `--prune`.

## Команды мейнтейнера

| Команда | Что делает |
|---|---|
| `swissknifeman registry` | регенерирует `skills.json`, плагин-манифесты `.claude-plugin/*` и `docs/guide/graph.md` (бывший `./sync.sh --update-registry`) |
| `swissknifeman validate` | `scripts/validate.sh` (то же, что CI) |
| `swissknifeman doctor` | python3, симлинк, PATH, projects.json, чистота реестра, профили |
| `swissknifeman version` | git SHA + путь к реестру |

## Карта проектов: `~/.swissknifeman/projects.json`

Пополняется автоматически при `connect`/`vendor`/`update`. Записи с ключом
(path, channel):

```json
{
  "version": 1,
  "projects": [
    {
      "path": "/home/user/projects/my-app",
      "channel": "marketplace",
      "profile": "laravel-project",
      "profile_source": "autodetect",
      "plugins": ["architect", "php", "quality"],
      "settings_file": "settings.local.json",
      "hub": true,
      "first_connected_at": "2026-06-12T10:00:00Z",
      "updated_at": "2026-06-12T10:00:00Z"
    }
  ]
}
```

`profile_source` управляет поведением `update`: `autodetect`/`config`
пере-резолвятся с диска, явные `flag`/`plugins`/`buckets` воспроизводятся.
Запись атомарная; повреждённый файл переименовывается в
`projects.json.corrupt.<дата>` и пересоздаётся — записи восстанавливаются
adopt-ом при следующем `update` в проекте.

## Troubleshooting

- **`bash: swissknifeman: No such file or directory`** — симлинк повис
  (репозиторий реестра переехал или удалён). Перезапустите `./install.sh`
  из нового расположения репозитория.
- **`~/.local/bin` не в PATH** — `install.sh` печатает команду для вашего
  шелла; после добавления перезапустите терминал.
- **`python3 is required`** — установите python3 (`apt install python3` /
  `brew install python3`).
- **Проект не находится** — нет ни `.swissknife.json`, ни `.claude/`, ни
  `.git` вверх по дереву; создайте `.swissknife.json` в корне проекта.
- Общая диагностика: `swissknifeman doctor`.

## Deprecated

`scripts/connect-claude.sh` и `./sync.sh --update-registry` — тонкие
wrapper'ы на один релиз, переадресуют в CLI. Brain-sync (`BRAIN_PATH`)
удалён: brain подключается как обычный проект (`cd <brain> && swissknifeman
vendor`, дальше `swissknifeman update`).
