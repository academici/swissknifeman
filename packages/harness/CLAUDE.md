# CLAUDE.md — harness

Гид по кодовой базе для агентов. Это пакет **настройки окружения Claude Code**
экосистемы academici: раздаёт в проекты харнес-конфигурацию — пресеты permissions,
режимы auto-approve/bypass, MCP-серверы и хуки (memory/notify/log). Выделен из
`skiller` (там оставались только скиллы). CLI — `harness`.

## Что это

Источник истины харнес-пресетов — `configs/claude-code/`:

- `settings.*.json` — пресеты permissions по стекам (base/laravel/php-package/node/
  python/docker) + `global`/`yolo`/`product-boundary`. Вливаются merge-only в
  `.claude/settings*.json` цели.
- `mcp/<name>.json` — голые объекты конфига MCP-серверов (context7/playwright/
  filesystem/fetch/memory/github/sequential-thinking). Вливаются в `.mcp.json`.
- `hooks/auto-approve/` — PreToolUse-хук авто-одобрения (режимы strict/permissive/
  bypass; порядок deny_hard→deny_block→allow).
- `hooks/memory/` — единая память (file/federation/agentmemory).
- `hooks/notify/`, `hooks/log-bash-command.sh` — ОС-уведомления и лог Bash-команд.

## Раскладка

- `bin/harness` — тонкий bash-лаунчер → `python3 -m harness <root> <cmd> [args]`.
- `lib/harness/*.py` — вся логика, **stdlib-only**.
- `configs/claude-code/` — пресеты settings/mcp + хуки (источник истины).
- `scripts/apply-permissions.sh` — bash+python merge пресетов в `.claude/`.
- `.claude-plugin/` + `commands/*.md` — плагин Claude Code (slash `/harness:*` → CLI).
- `tests/` — `unittest`, изоляция в tmpdir (синтетические пресеты).

### Ключевые модули

| Модуль | Ответственность |
|:--|:--|
| `cli.py` | диспетчер команд (`COMMANDS` → `cmd_*(env, argv)`) |
| `common.py` | `Env(BaseEnv)` (path-property пакета), `parse_flags`, реэкспорт из `core` |
| `settings.py` | merge-only writer'ы в `.claude`/`.mcp.json`/`.swissknife.json` (бэкап *.bak) |
| `permissions.py` | `apply_permissions` + `cmd_permissions` (обвязка `apply-permissions.sh`) |
| `mcp.py` | `block_mcp`/`available_mcp` + `cmd_mcp` (пресеты MCP → `.mcp.json`) |
| `hooks.py` | `block_autoapprove`/`block_memory`/`install_global` + `cmd_hooks` |
| `doctor.py` | диагностика окружения |

## Команды CLI

```bash
harness permissions --target . [--preset a,b] [--file F] [--dry-run] [--list] [--global]
harness mcp         --target . --mcp context7,playwright [--list] [--dry-run]
harness hooks       --global            # файлы хуков в ~/.claude/hooks (один раз на машину)
harness hooks       --target . --auto-approve strict --memory core:federation
harness doctor
```

## Конвенции (соблюдай при правках)

- **stdlib-only** в `lib/harness/`. Никаких pip-зависимостей в рантайме.
- **`Env` передаётся явно** (frozen dataclass), без модульных глобалей — тестируемо в tmpdir.
- **Запись в проекты — merge-only**, существующее не затирается, бэкап `*.bak`.
- **Сообщения — на русском** (`die(...)`, `warn(...)`), как в skiller/maind.
- **После правок плагина/команд** — `skiller registry` (регенерит общий
  `.claude-plugin/marketplace.json`; harness подхватывается как соседний пакет).

## Кросс-зависимости (важно)

- **Память делит state со skiller.** Установленные хуки `~/.claude/hooks/memory/`
  читают `~/.swissknifeman/topology.json`/`projects.json` — это state, которым
  владеет `skiller` (его `install.sh` создаёт каталог). harness лишь раздаёт файлы
  хуков; пути в них НЕ менять (back-compat для уже установленных хуков). Нейтральный
  общий state (`~/.academici/`) — будущая миграция, вне scope.
- **`.swissknife.json:memory_brain`** пишет harness (`hooks --memory`), валидирует
  `skiller` (`CONFIG_KEYS`). Ключ не переименовывать.
- **skiller делегирует сюда** через subprocess: `skiller`/`integrate` зовут
  `harness permissions|mcp|hooks` (резолв лаунчера: `SKM_HARNESS_BIN` →
  `<монорепо>/packages/harness/bin/harness`). При отсутствии harness — graceful skip.

## Разработка

```bash
bash scripts/test.sh          # unittest (без сети)
bash scripts/validate.sh      # py_compile + bash -n + JSON + frontmatter + тесты
npm run docs:build            # standalone-сайт доков (своя docs/.vitepress, base /harness/)
```

Доки пакета (`docs/`) собираются и **standalone** (своя `docs/.vitepress/config.mts`),
и в зонтичном агрегате (`scripts/docs-sync.sh` отбрасывает per-package `.vitepress`).
Поэтому внутренние ссылки доков — **относительные** (`./`, `../`), без `/harness/`-префикса.

Коммиты — Conventional Commits, на русском. Перед PR: `scripts/validate.sh` зелёный.
