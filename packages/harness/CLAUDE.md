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
  bypass; порядок deny_hard→deny_block→allow). **safe-dirs**: rm/rmdir с целями строго
  внутри доверенных директорий пропускаются мимо deny_hard — allowlist MACHINE-OWNED
  `<монорепо>/safe-dirs.json` (корень репо, gitignored, шаблон `safe-dirs.example.json`;
  лестница хука: `$SKM_SAFE_DIRS_CONFIG` → корень монорепо через realpath PATH-лаунчера →
  legacy `~/.swissknifeman/`), управление — `harness safe-dirs`, вердикт `lib/safedirs.py`
  (fail-closed: shlex-argv, realpath, containment, защита .git/корня; project-override
  конфига хука на allowlist НЕ влияет).
- `hooks/memory/` — единая память (file/federation/agentmemory).
- `hooks/review-gate/` — гейт архитектуры на `SubagentStop`. Содержание — `checks/`
  (диспетчер `run-checks.sh` + по файлу на класс проверки, везёт harness);
  `config.json` (machine-owned) объявляет ТОЛЬКО набор и per-check режим
  (`strict`/`warn`), `check_command` — одна стабильная строка-вызов диспетчера.
  Глобальный `MODE` (`env.ini`) может ПОНИЗИТЬ strict-класс до warn, не наоборот;
  защита от петли — счётчик диспетчера по (сессия, агент, проверка). Три состояния
  в `harness doctor` вместо тихого no-op.
- `hooks/notify/`, `hooks/log-bash-command.sh` — ОС-уведомления и лог Bash-команд.
- **`configs/common/agent-packs/review-roles.json`** — реестр ролей ревью как данные (L2):
  extension-таблица по ключу `(pack_id, role_id)` рядом с каноном `configs/common/agent-packs/
  roles.json`; индексирует пять reviewer-ролей (projection/overrides/required_sections/
  sections/dimensions), НЕ копирует правила и НЕ трогает `role-bindings.json`/`agentpacks.py`
  (frozen provider-contract, D126). Валидатор `lib/harness/reviewroles.py`
  (stdlib, восемь проверок) — шаг `[8/8]` в `scripts/validate.sh`; единственная точка
  принуждения.
- `hooks/agent-router/` — **intent-router** (первый Python-хук репо): пара `session-policy.py`
  (SessionStart — статическая политика) + `router.py` (UserPromptSubmit — keyword-подсказка) роутит
  свободный текст к оптимальной `/task:*`/агенту/скиллу. Каталог генерит `harness router --generate`.
- `hooks/run-report/` — **архивный захват прогона** (SessionEnd, `run-report.py` + `_lib.py`):
  строчно парсит транскрипт → пишет `<project>/.claude/runs/<sid>.json` (тесты/линт/файлы/
  tool-провалы/dev-loop-сигнал). Generic (любая задача, не только dev-loop). Читает `maind analyze`.
- `output-styles/<name>.md` — **терсе-«голос» вывода** (токен-экономия: output-токены ~4-5× input).
  `lean` — телеграфный (только выжимка+код), `keep-coding-instructions:true` (инж-правила живут).
  Включается per-project: `harness hooks --output-style lean` (пишет `outputStyle` в settings.local.json).
- **`plansDirectory` (per-project plan-система)** — `harness hooks --plans-dir plans|off` ставит
  top-level ключ `plansDirectory` в **`.claude/settings.json`** (шаримый, коммитится — командная
  конвенция, не машинно-локальная преференция; отличие от `outputStyle`). Merge-only и НЕ
  перезаписывает чужой выбор: ключ уже занят ДРУГИМ значением → skip + warn «уважаю локальный
  выбор»; `off` снимает ключ только если он равен нашему дефолту `plans`.

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
| `safedirs.py` | `cmd_safedirs` — allowlist `<монорепо>/safe-dirs.json` (init/add/list/prune-ask, init мигрирует legacy из home); вердикт-ядро живёт в хуке `configs/.../auto-approve/lib/safedirs.py` |
| `settings_audit.py` | **settings-doctor** (read-only): слои настроек CC (`user→project→local→managed`) + эффективная конфигурация с провенансом + таксономия проверок (`CHECKS`) + рендер отчёта/`--json`/exit-code. Профили — `configs/claude-code/policy/*.json`, декларация — `.swissknife.json:policy_profile` |
| `doctor.py` | диагностика окружения (без флага) + ветка `--settings` → аудит настроек CC (`settings_audit`, отчёт/`--json`/exit-code 0-1-2) |

## Команды CLI

```bash
harness permissions --target . [--preset a,b] [--file F] [--dry-run] [--list] [--global]
harness mcp         --target . --mcp context7,playwright [--list] [--dry-run]
harness hooks       --global            # файлы хуков в ~/.claude/hooks (один раз на машину)
harness hooks       --target . --auto-approve strict --memory core:federation --router propose --run-report on --output-style lean --plans-dir plans
harness router      --generate --target .   # каталог intent-router (.claude/agent-router.config.json)
harness agent-packs <list|render|upgrade|remove|doctor> [--pack P] [--target .] [--auto]
        [--dry-run] [--install-only] [--allow-shell M] [KEY=VALUE …]   # см. agentpacks.py
harness safe-dirs   <init|list|add|remove|prune-ask|delete> [PATH…] [--exclude] [--global]
        [--target P] [--all-projects] [--dry-run]   # allowlist rm/rmdir; delete — прямое
        удаление в обход shell rm/rmdir (для/xargs/sudo-заблокированных форм, см. safedirs.py)
harness doctor       # диагностика окружения harness
harness doctor      --settings [--target .] [--json] [--profile NAME]  # аудит настроек CC (read-only)
```

`agent-packs` — подсистема персона/стек-паков (шаблоны `.claude/agents|hooks|settings` под проект):
`render` ставит пак (интервью → подстановка `{{TOKEN}}`), `upgrade` накатывает новую версию пака
бережно (категории new/safe-apply/conflict/user-owned — `conflict` пишет `*.pack-new`, локальные
правки не затирает), `remove` сносит установленный пак безопасно (только неправленные файлы;
merge/user-owned оставляет с warn'ом), `list`/`doctor` — каталог и диагностика. Lock —
`.claude/agent-pack.lock.json`. `files[]`-запись пака может нести `src_pack: <другой-пак>` —
контент берётся из каталога того пака (шаринг без копий), владелец (header) — текущий пак.

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
