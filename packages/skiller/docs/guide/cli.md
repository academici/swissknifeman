# CLI swissknifeman

`bin/skiller` — единая точка входа: подключение проектов, обновление,
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

### `skiller connect`

Подключает проект к нативному plugin marketplace Claude Code: пишет
`extraKnownMarketplaces.swissknifeman` и `enabledPlugins."<bucket>@swissknifeman"`
в `.claude/settings.local.json`. Merge-only: явный `false` не перетирается,
включённое сверх профиля не отключается, бэкап в `*.bak`.

Provider selection берётся из `.swissknife.json::providers`: при отсутствии
слоя сохраняется legacy-режим только для Claude Code. Self-host checkout
использует thin Codex marketplace, а внешний connect-проект получает
repo-contained marketplace и self-contained bundles только выбранных plugins,
включая runtime-файлы скиллов (`snippets/`, `references/`, scripts/assets).
Проектная публикация не меняет user-level plugin state: базовые `core` + `task`
устанавливает машинный `install.sh`, а профильные Codex plugins добавляются только
явно. Native manifest каждого bucket перечисляет skill-каталоги явно, поэтому Codex
раскрывает их после установки. Dual-selection проходит preflight всех provider-целей
до первой записи, поэтому конфликт не оставляет успешную половину подключения.

```
skiller connect [--profile P | --plugins a,b]
                      [--file settings.json|settings.local.json]
                      [--cleanup-vendored] [--list] [--dry-run] [--hub]
```

### `./install.sh [--no-codex-plugins]`

Машинная установка добавляет marketplace текущего checkout в Codex и по умолчанию
устанавливает базовые плагины из CORE-политики (`core` + `task`). Если Codex CLI
отсутствует, этот шаг явно пропускается без поломки установки остальных CLI;
`--no-codex-plugins` — явный opt-out. Дополнительный глобальный плагин ставится
повторяемым `./packages/skiller/install.sh --codex-plugin NAME`.

`connect`, `sync`, `update`, `doctor` и `--dry-run` user-global Codex state не
меняют. Профильные плагины не устанавливаются глобально автоматически.

### `skiller vendor`

Вендорит скиллы в проект (Cursor и другие агенты): профили, автодетект,
транзитивный резолв `requires`, манифест-переустановка — см.
[Установка](./installation) и [Вендоринг](./vendor-skills).

```
skiller vendor [--agent claude|cursor|generic]
                     [--profile P | --buckets a,b] [--exclude x,y]
                     [--skills-path P] [--list] [--dry-run] [--force] [--hub]
```

### `skiller integrate`

Интерактивный визард интеграции: проходит [чеклист](./integration-checklist) по
всему функционалу (скиллы, permissions, MCP, хуки auto-approve/память/output-style,
hub) и применяет выбранное. Скиллы/hub — сам skiller; окружение (permissions/MCP/
хуки, включая терсе output-style `lean` — включён во всех бандлах) делегируется
пакету [`harness`](/harness/) через subprocess. Безопасно —
`--dry-run`, merge-only, бэкапы.

```
skiller integrate [--target P]
                        [--bundle minimal|recommended|full|custom]
                        [--yes] [--dry-run] [--file settings.json|settings.local.json]
```

### `skiller update [--all] [--dry-run]`

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

### `skiller status`

Read-only отчёт: корень и маркер, каналы, дрейф плагинов относительно профиля,
переехавший путь marketplace, состояние вендоренных скиллов, SHA реестра.

### `skiller list [--prune]`

Таблица зарегистрированных проектов со статусом `ok|missing`. Записи никогда
не удаляются автоматически — только явный `--prune`.

### `skiller analyze-run [--last | --session ID] [--project DIR] [--json] [--store]`

Пост-ран разбор прогона по JSONL-логам Claude Code (детерминированно, без трат
токенов): факт-токены/тайминги/cache-hit по агентам + эффективные/мёртвые скиллы +
рантайм-отказы. Дополняет качественный скилл `system/session-observer`. Подробности,
формат и ограничения — [analyze-run](./analyze-run.md).

## Команды мейнтейнера

| Команда | Что делает |
|---|---|
| `skiller registry` | регенерирует `skills.json`, плагин-манифесты `.claude-plugin/*` и `docs/guide/graph.md` (бывший `./sync.sh --update-registry`) |
| `swissknifeman validate` | `scripts/validate.sh` (то же, что CI) |
| `skiller doctor` | python3, симлинк, PATH, projects.json, чистота реестра, профили |
| `skiller budget --first-turn [--target DIR] [--json] [--strict]` | always-on футпринт первого хода проекта (skills+agents+CLAUDE.md/rules+живой прогон SessionStart-хуков+MCP); вердикт OK ≤16K / ELEVATED ≤23K / WARN >23K ток; `--strict` — exit 1 при WARN (CI). Флот — `maind doctor --context`. Строка MCP — режим-зависимая (P2.3): `deferred` (дефолт, tool search включён — имена инструментов + инструкции сервера, нижняя граница) / `auto` (верхняя граница, допущение «в пределах 10% окна» не проверено) / `off` (`ENABLE_TOOL_SEARCH=false` — полные схемы); режим печатается вместе с источником (env → `settings.local.json` → `settings.json` → дефолт) и классом оценки, в JSON — аддитивные ключи `mcp.mode`/`mcp.mode_source`/`mcp.estimate_class` (`total`/`verdict` не меняются, D16) |
| `skiller budget --first-turn --with-plugins [--target DIR] [--json]` | добавляет always-on цену установленных marketplace-плагинов проекта (`claude plugin list/details`, вызов `details` — под `cwd` проекта, local-scope плагины чужого CWD не резолвятся) аддитивными ключами `plugins`/`session_total`/`session_verdict`; без флага вывод не меняется. Требует `--first-turn`; сбой листинга → `n/a`; невзятая цена плагина — `broken` (сам листинг объявил плагин сломанным полем `errors`) отдельно от `unparsed` (нераспознанный формат апстрима), никогда молчаливый 0. **Пороги вердикта откалиброваны именно на этой, плагин-инклюзивной величине** (`session_total`): baseline флота n=22, медиана плагинной суммы 8 741 ток → `16K`/`23K` вместо прежних `7K`/`10K`, посчитанных до того, как плагины вообще стали считаться (2026.07.31-SKM-LEAN D83) |
| `skiller budget --provider claude-code\|codex [--profile P\|--config F\|--target DIR]` | добавляет к отчёту provider-aware бюджет обнаружения (листинга) и режим деградации; дефолт без флага — `claude-code`. `--profiles` — тот же замер по КАЖДОМУ поставляемому профилю против обоих провайдеров разом (WARN-гейт в `validate.sh` при переборе фолбэк-бюджета Codex, D26) |

**Строка «исключено записей: N (по полю …)»** в отчётах `--first-turn` и `--provider`
(2026.07.31-SKM-LEAN P3.2, D95/D96). Запись скилла, несущего `disable-model-invocation: true`
или `paths:`, в резидентный листинг Claude Code **не входит** — измеритель её не считает и
печатает число исключений с полем-причиной, а рядом — цену, ушедшую из листинга. Основание —
НАБЛЮДЕНИЕ стенда на живой 2.1.220, не документация: оба поля дали одну и ту же дельту оси A
(−88 на запись, воспроизведено байт-в-байт в двух прогонах), причём для `paths:` это
противоречит доковой строке «The listing always contains every skill name»
(`plans/archive/2026.07.31-SKM-LEAN/findings/P3-native-fields-smoke.md` §3.1–3.2). Условие механизма
`paths:` — «сессия ПРОЧЛА совпавший файл», а не «файл лежит в дереве»
(`findings/P3-paths-mechanism.md` §2), и на ПЕРВОМ ходу прочитанных файлов нет по построению,
поэтому исключение безусловно. В JSON сведения приезжают аддитивно:
`sources.skills.excluded`/`excluded_by`/`excluded_raw` (`--first-turn`) и
`listing.excluded`/`excluded_by`/`excluded_raw` (`--provider`) — ключи `total`/`verdict` и
смысл прежних ключей не меняются (D16). Для `--provider codex` исключение **не применяется**:
поля измерены только на Claude Code, и codex-ветка сознательно продолжает завышать, вместо
недоказанного занижения.
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

Provider-aware vendor lock хранит legacy Claude entries в `skills`, а Codex — в
`providers.codex`; ключ карты проекта — `(path, channel, provider)`. Два
provider-а не могут владеть одним physical skills path: операция fail-closed до
копирования или prune.

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
- Общая диагностика: `skiller doctor`.

## Deprecated

`scripts/connect-claude.sh` и `./sync.sh --update-registry` — тонкие
wrapper'ы на один релиз, переадресуют в CLI. Brain-sync (`BRAIN_PATH`)
удалён: brain подключается как обычный проект (`cd <brain> && swissknifeman
vendor`, дальше `skiller update`).
# Проверяемая поставка релиза

`skiller version --json` показывает umbrella tag/commit и независимые unit versions/digests.
`skiller attest --release vX.Y.Z --previous vA.B.C` генерирует `releases/vX.Y.Z.json`;
`--check` проверяет свежесть и immutable version tuple. После проверки generator locks
и commit запустите `python3 scripts/verify-tag.py vX.Y.Z` до создания annotated tag.

`skiller deliver --release vX.Y.Z --all --dry-run` классифицирует lost ownership без записи.
Без `--dry-run` команда обновляет registered projects и установленные native plugins,
восстанавливая только exact-current/exact-known-old или закрытую generated marketplace форму.
Modified/unknown файлы сохраняются и оставляют PARTIAL. До изменения сохраняются preimages.
`--target PATH` ограничивает project delivery; `--no-native` явно исключает cache stage.

Receipt хранится в `~/.swissknifeman/receipts/delivery/<release>/`; GREEN требует readback
всех выбранных targets. Existing sessions отмечаются `restart-required`: начните новую сессию.
Source-managed bytes, native cache, project projection и loaded session — разные поверхности.
Commit SHA добавляется к runtime receipt через annotated tag: committed attestation хранит tag,
date и tree digests, чтобы не создавать самоссылочный SHA release commit.
# Native cache and legacy Codex copies

`connect --cleanup-codex-vendored` explicitly retires only directories declared by a known v1 `.agents/skills` vendor manifest. It keeps unlisted local skills, refuses foreign lock ownership, and moves the old copies into `.swissknifeman/backups/` so they can be restored. It does not change the project's configured plugin selection.

Release attestation distinguishes contained `codex` skill bundles from full `codex-native` source caches. Ignored local telemetry is not a release surface. Added evidence coverage is checked against the previous Git source tag; changing already recorded bytes still requires a new unit version.
