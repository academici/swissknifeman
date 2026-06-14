# Пресеты permissions для Claude Code

Готовые наборы разрешений для `.claude/settings.local.json` — чтобы новый проект
сразу работал без бесконечных permission-промптов.

| Пресет | Что разрешает |
|---|---|
| `base` | git (push — с подтверждением), gh, файловые операции, curl/wget, jq/rg/sed; deny на секреты (`.env`, ключи, `~/.ssh`) и `sudo` |
| `laravel` | `php artisan`, composer, pest/phpunit/pint/phpstan/rector, sail, npm/vite; деструктивные миграции — с подтверждением; deny на токен-шум (`storage/logs`, `node_modules`, `*.lock`, кэши) — `vendor/` **не** блокируется: там Boost-гайдлайны (`vendor/laravel/boost/.ai/`) |
| `php-package` | composer, pest/phpunit/pint/phpstan/rector/infection — без artisan |
| `node` | node/npm/npx/pnpm/yarn, tsc, vitest, eslint, prettier; publish — с подтверждением; deny на токен-шум (`node_modules`, `dist`, `build`, `coverage`, `*.lock`, минифицированные бандлы) |
| `python` | python/pip/pytest, uv, poetry, ruff/black/mypy |
| `docker` | docker + docker compose; удаление контейнеров/volumes/prune — с подтверждением |
| `yolo` | `bypassPermissions` — только для контейнеров и VM, см. предупреждение в доке |
| `global` | baseline для `~/.claude/settings.json`: read-only команды (grep/find/ls/cat, git diff/log/status), безопасный git (add/commit/checkout/stash), deny на sudo/force-push/секреты + **hook-логгер команд** (активен) + **notify** — ОС-уведомления на запрос подтверждения/утверждения (активен) + установка файлов **auto-approve** (включается по проекту, см. ниже) (через `--global`) |

## Быстрый старт

```bash
# base + автодетект стека по маркерам проекта (artisan, package.json, pyproject.toml, ...)
./scripts/apply-permissions.sh --target ~/projects/my-laravel-app

# явный набор
./scripts/apply-permissions.sh --target . --preset base,laravel,docker

# превью без записи
./scripts/apply-permissions.sh --target . --dry-run

# глобальный baseline + hook-логгер в ~/.claude (один раз на машину)
./scripts/apply-permissions.sh --global
```

Скрипт объединяет `allow`/`ask`/`deny` с уже существующими правилами цели
(ничего не затирает, дубликаты убирает) и делает бэкап `settings.local.json.bak`.

## Лог команд («прокси»)

Пресет `global` регистрирует PreToolUse-hook ([hooks/log-bash-command.sh](hooks/log-bash-command.sh)):
каждая Bash-команда Claude Code пишется в `~/.claude/logs/bash-commands.jsonl` —
в любой момент можно проверить, что агент реально выполнял. Hook только логирует,
никогда не блокирует. Подхватывается при старте сессии — после установки
перезапустите Claude Code.

```bash
# последние 20 команд
tail -20 ~/.claude/logs/bash-commands.jsonl | jq -r '"\(.ts) [\(.cwd)] \(.command)"'

# команды конкретного проекта
jq -r 'select(.cwd | test("myproject")) | .command' ~/.claude/logs/bash-commands.jsonl
```

## ОС-уведомления (notify)

Пресет `global` регистрирует Notification-hook
([hooks/notify/notify.sh](hooks/notify/notify.sh)): как только Claude Code
ждёт человека — **запрос разрешения на инструмент**, **утверждение плана**
(ExitPlanMode) или простой промпта дольше ~60 сек — всплывает ОС-уведомление
с текстом запроса и именем проекта. Удобно, когда агент работает в фоне и
не нужно держать терминал в фокусе. Hook только уведомляет, никогда не блокирует.

Кросс-платформенно, бэкенд выбирается по ОС (если ни одного нет — тихо выходит):

| ОС | Бэкенд |
|---|---|
| Linux | `notify-send` (libnotify) |
| macOS | `terminal-notifier` → `osascript` |
| WSL / Windows | PowerShell toast → `MessageBox` → `msg.exe` |

Подхватывается при старте сессии — после `--global` перезапустите Claude Code.

## Авто-апрув команд (hooks)

Префиксные allow-правила (`Bash(grep *)`) не матчат **компаунд-команды** —
с `cd ... &&`, циклами `for`, пайпами, подстановками `$(...)`. Такие команды
каждый раз уникальны и упираются в permission-промпт, сколько паттернов ни добавь.
Решение — PreToolUse-хуки, которые разбирают **всю** строку и принимают решение.

### Один переключатель, режим в `env.ini`

Всё в самодостаточной папке [`hooks/auto-approve/`](hooks/auto-approve/) — её целиком
публикует swissknifeman, а ты выбираешь режим в файле. Корневой
[`auto-approve.sh`](hooks/auto-approve/auto-approve.sh) — **переключатель**: читает
режим из [`env.ini`](hooks/auto-approve/env.ini) и вызывает один из
[`modes/`](hooks/auto-approve/modes/). Источники — [`CREDITS.md`](hooks/auto-approve/CREDITS.md).

```
hooks/auto-approve/
  auto-approve.sh   # переключатель (регистрируется на Bash + ExitPlanMode)
  env.ini           # MODE=strict|permissive|bypass|off  ← выбор режима
  config.json       # конструкции (allow/deny/субкоманды)
  lib/{common,analyze}.sh
  modes/{strict,permissive,bypass}.sh
```

Зарегистрирован один файл на оба матчера; смена `MODE` в `env.ini` → **перезапусти
Claude Code**. Режимы — спектр автономности:

| `MODE` | Команды (Bash) | План (ExitPlanMode) |
|---|---|---|
| `strict` | allowlist-first: read-only → allow, мутации → промпт, катастрофа → deny | промпт |
| `permissive` | denylist-first: всё кроме денилиста → allow, мутации → промпт, катастрофа → deny | промпт |
| `bypass` | всё, кроме катастрофичного (`deny_hard`) → allow | **авто-подтверждение** |
| `off` | обычный permission-флоу | обычный |

**Денилисты (общие, из `config.json`):**
- `deny_hard` (катастрофично: `sudo`/`rm`/`mkfs`/fork-bomb/`\| sh`/запись на диск) →
  **активный `deny`** во всех режимах.
- `deny_block_approve` (мутация: `mv`/`cp`/запись в файл/`git push`·`commit`/`docker run`/
  `npm install`/`sed -i`) → **промпт** (в `strict`/`permissive`).
- `strict` дополнительно требует, чтобы голова каждого сегмента была из `allow`
  (read-only coreutils, read-субкоманды `git`/`gh`/`docker`, `jq`/`awk`/`sed`,
  инлайн `python3 -c`/`node -e`).

Конфиг и режим имеют per-project override:
`<project>/.claude/auto-approve.config.json` и `auto-approve.env.ini`.

Парсинг: если установлен `shfmt` — AST-разбор как доп. проверка (union: может только
ужесточить); иначе встроенный regex-разбор. Содержимое кавычек вырезается до анализа
⇒ тела `python3 -c`/`node -e` доверяются (флаг `trust_inline_interpreters`).

### Лог решений

Каждый проход хука пишется в `~/.claude/logs/auto-approve-decisions.jsonl`
(`ts`, `hook`, `cwd`, `decision`, `command`, `reason`) — видно, какие команды вызывает
агент, и можно докрутить конфиг:
```bash
# что упёрлось в промпт (decision=ask) — кандидаты в allow/deny
jq -r 'select(.decision=="ask") | .command' ~/.claude/logs/auto-approve-decisions.jsonl | sort | uniq -c | sort -rn | head
# распределение решений
jq -r .decision ~/.claude/logs/auto-approve-decisions.jsonl | sort | uniq -c
```

### Включение по проекту

Глобально (`global`) **только устанавливаются файлы** `~/.claude/hooks/auto-approve/`
и активируется лог-логгер — сам auto-approve **глобально НЕ зарегистрирован** (никакого
авто-одобрения в случайных каталогах). Включаешь хук точечно в нужном проекте,
`<project>/.claude/settings.json`:
```jsonc
{ "hooks": { "PreToolUse": [
  { "matcher": "Bash",        "hooks": [{ "type": "command", "command": "~/.claude/hooks/auto-approve/auto-approve.sh" }] },
  { "matcher": "ExitPlanMode","hooks": [{ "type": "command", "command": "~/.claude/hooks/auto-approve/auto-approve.sh" }] }
] } }
```
Режим для проекта — `<project>/.claude/auto-approve.env.ini` (иначе берётся дефолт из
`~/.claude/hooks/auto-approve/env.ini`):
```ini
MODE=strict
```
После подключения/смены режима — перезапусти Claude Code.

> ⚠️ **Риск-компромиссы.** `permissive` одобрит незнакомую команду вне денилиста;
> `bypass` одобрит любую команду кроме катастрофичной и сам подтвердит план — только
> доверенные проекты/контейнеры. `python3 -c`/`node -e` доверяются (тело не
> анализируется). Для полного «bypass всех команд после плана» в `bypass`-режиме
> добавь в настройки проекта `"permissions": { "defaultMode": "bypassPermissions" }`.

Подробный разбор синтаксиса правил и логики пресетов — в
[документации](../../docs/configs/claude-permissions.md).
