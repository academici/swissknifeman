# Чеклист интеграции в проект

При интеграции swissknifeman в проект ты выбираешь, **что хочешь из максимального
функционала**. Есть два пути: интерактивный **визард** (`swissknifeman integrate`),
который проходит чеклист и применяет выбранное, и **ручной** — те же действия
отдельными командами.

```bash
cd ~/projects/my-app
swissknifeman integrate            # интерактивно (меню по каждому блоку)
swissknifeman integrate --dry-run  # показать план, ничего не записывая
swissknifeman integrate --yes --bundle recommended   # без вопросов, готовый набор
```

## Уровни (бандлы)

Быстрый старт без перебора каждого пункта — `--bundle`:

| Бандл | Скиллы | Permissions | auto-approve | Память | Hub |
|---|---|---|---|---|---|
| `minimal` | connect | — | — | — | — |
| `recommended` (дефолт для `--yes`) | connect | autodetect | strict | — | да |
| `full` | connect | autodetect | strict | brain `core`, federation | да |
| `custom` (дефолт интерактивно) | спрашивает каждый блок | | | | |

## Чеклист (что можно включить)

Каждый пункт — что даёт, как включает визард, ручной эквивалент.

### 1. Скиллы (обязательный минимум)
Раздача скиллов реестра в проект.
- **connect** — Claude Code через plugin marketplace (правит `.claude/settings.local.json`:
  `extraKnownMarketplaces` + `enabledPlugins`). Версия = git SHA реестра.
- **vendor** — Cursor и другие агенты (копирует скиллы в `.cursor/skills` / `.ai/skills`).
- Профиль/бакеты — autodetect (`.obsidian/` → vault, `artisan`+`composer.json` → laravel,
  `composer.json` → php-package, иначе standalone), переопределяется флагами.
- Ручками: `swissknifeman connect` / `swissknifeman vendor --agent cursor`.

### 2. Permissions-пресеты
Готовые `allow/ask/deny` под стек — меньше permission-промптов.
- Autodetect по маркерам (base + laravel/php-package/node/python/docker).
- Ручками: `./scripts/apply-permissions.sh --target <проект>`.
- Подробнее: [Permissions](/configs/claude-permissions).

### 3. auto-approve (per-project)
PreToolUse-хук, разбирающий **всю** командную строку (компаунд-команды), режимы
`strict|permissive|bypass|off`.
- Визард пишет `.claude/auto-approve.env.ini` (MODE) + регистрирует хук на
  `PreToolUse` (Bash + ExitPlanMode) в `.claude/settings.json`.
- Файлы хука ставятся один раз на машину: `apply-permissions.sh --global`.
- Подробнее: [конфиги Claude Code](https://github.com/academici/swissknifeman/tree/main/configs/claude-code#авто-апрув-команд-hooks).

### 4. Память (членство в общем «мозге»)
Проект делит факты с другими участниками своей группы (brain); режимы
`file|federation|agentmemory|off`.
- Визард пишет `.swissknife.json:memory_brain` + `.claude/memory.env.ini` (MODE).
- Состав участников группы — `~/.claude/hooks/memory/config.json` (`brains.<имя>.members`).
- Файлы хука — `apply-permissions.sh --global`. Скилл-обвязка: `system/shared-memory`.

### 5. Hub (индекс скиллов)
Managed-блок в `CLAUDE.md` (или `.ai/guidelines/swissknifeman-hub.md` при Boost) —
агент видит, какие скиллы подключены.
- Визард включает `--hub` у connect/vendor.
- Ручками: `./scripts/generate-hub.sh --target <проект>`.

### 6. Brain docs-sync (со стороны волта)
Двусторонний синк `docs/`/`docs-public` между проектом и Obsidian-волтом Brain.
- **Не автоматизируется из проекта** — настраивается во волте: во frontmatter
  заметки проекта добавь `repo: <путь к проекту>`, затем `brain status/sync`.
- Визард печатает нужный сниппет.

## Пререквизиты (один раз на машину)

Визард их проверяет и предлагает выполнить:
- **Топология** — `swissknifeman topology init` (`~/.swissknifeman/topology.json`);
  от неё зависят память и координатор (резолв узлов/участников).
- **Файлы хуков** — `./scripts/apply-permissions.sh --global` ставит
  `~/.claude/hooks/{notify,auto-approve,memory}` (notify/лог активны сразу,
  auto-approve/memory включаются по проекту).

## Безопасность визарда

- `--dry-run` — показывает весь план, **ничего не пишет**.
- Все правки **merge-only**: чужие ключи в `.claude/settings*.json` и `.swissknife.json`
  не затираются, перед записью — бэкап `*.bak`.
- Машинные пререквизиты (`--global`, `topology init`) — только с подтверждением.
- Идемпотентно: повторный прогон не плодит дубли хуков/правил.

## См. также
- [Установка скиллов](/guide/installation) — детали connect/vendor.
- [CLI swissknifeman](/guide/cli) — все команды.
- [Профили и автодетект](/guide/profiles).
