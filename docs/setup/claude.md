# Настройка окружения Claude Code

Как один раз настроить машину и проекты так, чтобы Claude Code работал
автономно: без бесконечных permission-промптов, но с полным аудитом того,
что агент реально выполняет.

## Проблема

При активной разработке Claude Code запрашивает подтверждение почти на каждую
терминальную команду. На практике это выглядит так:

- в 100% случаев нажимается «подтвердить», а результат проверяется постфактум —
  промпты не защищают, а только прерывают работу;
- приходится сидеть у компьютера и ждать очередного вопроса вместо того,
  чтобы дать агенту задачу и вернуться к готовому результату;
- точечные разрешения «на конкретную команду» не переиспользуются: та же
  команда с другим файлом или флагом снова требует подтверждения.

Анализ ~5000 Bash-команд из реальных транскриптов показал масштаб проблемы:

| Тип команд | Доля | Примеры |
|---|---|---|
| Чистый read-only | **72.7%** | grep, find, ls, cat, git diff/log/status |
| Повторяемые dev-операции | ~21% | pest, composer, docker compose exec, git add/commit |
| Остальное | ~6% | curl, rm, разовые команды |

То есть почти три четверти промптов приходится на команды, которые ничего
не меняют, — их можно безопасно разрешить раз и навсегда.

## Решение: три слоя

### 1. Глобальный baseline (`~/.claude/settings.json`)

Пресет [`settings.global.json`](https://github.com/academici/swissknifeman/tree/main/configs/claude-code)
ставится один раз на машину и действует во всех проектах:

- **allow** — весь read-only (grep/find/ls/cat/head/tail/jq/awk…),
  read-only git (diff/log/status/show/branch), безопасный git
  (add/commit/checkout/stash), файловые операции (mkdir/cp/mv/touch);
- **ask** — необратимое: `git push`, `git reset --hard`, `rm -rf`;
- **deny** — заблокировано всегда: `sudo`, force-push, `git config --global`,
  `chmod 777`, чтение секретов (`.env`, `*.pem`, `*.key`, `~/.ssh`, `~/.aws`).

### 2. Профиль проекта (`.claude/settings.local.json`)

Поверх baseline в каждый проект накатывается пресет стека —
[см. подробный разбор](/configs/claude-permissions). Автодетект по маркерам:
`artisan` → laravel, `composer.json` → php-package, `package.json` → node,
`Dockerfile` → docker. После этого тесты, линтеры, composer и artisan
работают без промптов, а деструктивное (`migrate:fresh`,
`docker system prune`) остаётся под подтверждением.

### 3. Лог команд — «прокси» для аудита

Раз агент работает автономно, нужен способ постфактум проверить, что он
делал. Вместо внешнего прокси-демона используется нативный механизм hooks:
PreToolUse-hook `log-bash-command.sh` пишет **каждую** Bash-команду в
`~/.claude/logs/bash-commands.jsonl` — время, проект, команда, описание.
Hook только логирует и никогда не блокирует выполнение.

```bash
# Последние 20 команд
tail -20 ~/.claude/logs/bash-commands.jsonl | jq -r '"\(.ts) [\(.cwd)] \(.command)"'

# Все команды конкретного проекта
jq -r 'select(.cwd | test("myproject")) | .command' ~/.claude/logs/bash-commands.jsonl

# Частотный анализ: какие команды агент выполняет чаще всего
jq -r '.command' ~/.claude/logs/bash-commands.jsonl | awk '{print $1}' | sort | uniq -c | sort -rn | head
```

Ключевой принцип: **deny сильнее allow** — даже широкие префиксы не пропустят
`sudo`, force-push или чтение секретов. Контроль смещается с «подтверждать
каждый шаг» на «запретить опасное + проверять лог».

## Установка

```bash
cd ~/projects/packages/swissknifeman

# 1. Один раз на машину: глобальный baseline + hook-логгер
./scripts/apply-permissions.sh --global

# 2. В каждый проект: пресет стека (автодетект)
./scripts/apply-permissions.sh --target ~/projects/my-app

# Превью без записи / явный набор
./scripts/apply-permissions.sh --target . --dry-run
./scripts/apply-permissions.sh --target . --preset base,laravel,docker
```

Скрипт идемпотентен: правила мержатся с существующими без дублей, ничего
не затирается, перед записью создаётся бэкап `*.bak`. Ваши `model`,
`mcpServers` и прочие настройки в `~/.claude/settings.json` не трогаются.

::: warning Перезапуск обязателен
Hooks и permissions подхватываются при старте сессии — после `--global`
перезапустите открытые сессии Claude Code (и окно VSCode с расширением).
:::

## Если промпты всё ещё появляются

1. **Повторяющаяся команда** — добавьте её префикс в пресет
   (`Bash(vendor/bin/pest *)` покрывает любые аргументы) и переустановите.
2. **Автоматический подбор** — скилл `/fewer-permission-prompts` в Claude Code
   сам анализирует транскрипты и предлагает allowlist.
3. **Вариативные команды** — оберните их в стабильные скрипты
   (`composer ai:test`, `npm run ai:lint`): одно правило на скрипт вместо
   десятков уникальных команд.
