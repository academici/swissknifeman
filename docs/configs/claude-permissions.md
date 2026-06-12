# Permissions для Claude Code

Готовые пресеты разрешений в `configs/claude-code/` решают главную боль нового
проекта: десятки permission-промптов в первые полчаса работы. Один запуск
`apply-permissions.sh` — и агент может выполнять весь типовой инструментарий
стека, а опасные операции остаются под контролем.

> Полная настройка машины (глобальный baseline + лог всех команд агента) —
> в гайде [Настройка окружения Claude Code](/setup/claude).

## Пресеты

| Пресет | Файл | Что разрешает |
|---|---|---|
| `base` | `settings.base.json` | git (push — с подтверждением), gh, файловые операции, curl/wget, jq/rg/sed/awk, make; deny на секреты и `sudo` |
| `laravel` | `settings.laravel.json` | `php artisan`, composer, pest/phpunit/pint/phpstan/rector, sail, npm/vite |
| `php-package` | `settings.php-package.json` | composer, тесты и линтеры — без artisan |
| `node` | `settings.node.json` | node/npm/npx/pnpm/yarn, tsc, vitest, eslint, prettier |
| `python` | `settings.python.json` | python/pip/pytest, uv, poetry, ruff/black/mypy |
| `docker` | `settings.docker.json` | docker + docker compose; удаление и prune — с подтверждением |
| `yolo` | `settings.yolo.json` | `bypassPermissions` — только для изолированных окружений |

Логика каждого пресета трёхуровневая:

- **allow** — повседневный инструментарий стека работает без промптов;
- **ask** — необратимое или внешнее (git push, `rm -rf`, `migrate:fresh`,
  `docker system prune`, `npm publish`) требует подтверждения;
- **deny** — секреты (`.env`, `*.pem`, `*.key`, `~/.ssh`, `~/.aws`) и `sudo`
  заблокированы всегда.

## Скрипт apply-permissions.sh

```bash
# base + автодетект стека по маркерам проекта
./scripts/apply-permissions.sh --target ~/projects/my-laravel-app

# Явный набор пресетов
./scripts/apply-permissions.sh --target . --preset base,laravel,docker

# Превью без записи
./scripts/apply-permissions.sh --target . --dry-run

# Список доступных пресетов
./scripts/apply-permissions.sh --target . --list

# В шаримый settings.json вместо локального
./scripts/apply-permissions.sh --target . --file settings.json
```

Автодетект использует те же маркеры, что и `install.sh`:

| Маркер | Пресет |
|---|---|
| `artisan` + `composer.json` | `laravel` |
| `composer.json` без `artisan` | `php-package` |
| `package.json` | `node` |
| `pyproject.toml` / `requirements.txt` | `python` |
| `Dockerfile` / `compose.yaml` | `docker` |

Merge-семантика безопасна: `allow`/`ask`/`deny` объединяются с уже существующими
правилами цели без дублей, ничего не затирается, `defaultMode` берётся из
пресета только если в цели он не задан. Перед записью создаётся бэкап
`settings.local.json.bak`.

## Куда применять: settings.json vs settings.local.json

| Файл | Кому виден | Когда использовать |
|---|---|---|
| `.claude/settings.local.json` | только вам (не коммитится) | **по умолчанию** — личные разрешения |
| `.claude/settings.json` | всей команде (в git) | согласованные командные правила |
| `~/.claude/settings.json` | все ваши проекты | глобальные предпочтения |

Приоритет (от высшего): managed-настройки → CLI-аргументы →
`settings.local.json` → `settings.json` → `~/.claude/settings.json`.
**Deny на любом уровне нельзя перебить allow-ом на другом.**

## Синтаксис правил — шпаргалка

Правила оцениваются в порядке **deny → ask → allow**, побеждает первое
совпадение. Поэтому в пресетах работает связка «широкий allow + точечный ask»:
`Bash(git *)` в allow и `Bash(git push *)` в ask — push спросит, остальной
git нет.

### Bash

```json
"Bash(npm run build)"   // точное совпадение
"Bash(npm run *)"       // префикс: npm run lint, npm run test:unit, ...
"Bash(git * main)"      // wildcard в любой позиции
"Bash(* --version)"     // и в начале тоже
```

Нюансы, проверенные по официальной документации:

- пробел перед `*` важен: `Bash(ls *)` матчит `ls -la`, но не `lsof`;
  `Bash(ls*)` матчит оба. Суффикс `:*` эквивалентен ` *`;
- один `*` покрывает любую последовательность символов, включая пробелы:
  `Bash(git *)` матчит `git log --oneline --all`;
- **составные команды** разбираются по операторам `&&`, `||`, `;`, `|` —
  правило должно матчить каждую подкоманду отдельно. `Bash(safe-cmd *)`
  не разрешит `safe-cmd && rm -rf .`;
- обёртки `timeout`, `time`, `nice`, `nohup`, `stdbuf` и голый `xargs`
  срезаются перед матчингом; а вот `npx`, `docker exec`, `devbox run` — нет:
  `Bash(devbox run *)` разрешит всё, что идёт после `run`;
- read-only команды (`ls`, `cat`, `grep`, `pwd`, читающие формы `git` и т.д.)
  встроенно разрешены во всех режимах и в allow не нуждаются.

### Read / Edit

Пути — в gitignore-семантике, **четыре якоря**:

```json
"Read(//etc/hosts)"      // абсолютный путь (двойной слэш!)
"Read(~/.zshrc)"         // от home
"Edit(/src/**/*.ts)"     // от корня проекта (одинарный слэш)
"Read(*.env)"            // от текущего каталога
```

::: warning Частая ошибка
`/Users/alice/file` — это **не** абсолютный путь, а путь от корня проекта.
Для абсолютных путей нужен двойной слэш: `//Users/alice/file`.
:::

Голое имя файла матчится на любой глубине: `Read(.env)` ≡ `Read(**/.env)`.

### Остальные инструменты

```json
"WebFetch(domain:github.com)"        // fetch только на домен
"mcp__github"                        // все инструменты MCP-сервера github
"mcp__github__get_*"                 // его get-инструменты
"Agent(Explore)"                     // правило на субагента
```

## Режимы: defaultMode

| Режим | Поведение |
|---|---|
| `default` | промпт при первом использовании каждого инструмента |
| `acceptEdits` | автопринятие правок файлов и fs-команд в рабочем каталоге — **используется в пресете base** |
| `plan` | только чтение и анализ |
| `dontAsk` | автоотказ всему, что не разрешено явно |
| `bypassPermissions` | без промптов вообще — **только пресет yolo** |

::: danger Пресет yolo
`settings.yolo.json` включает `bypassPermissions`: Claude Code не спрашивает
ничего, кроме явных ask-правил и встроенного предохранителя на `rm -rf /` и
`rm -rf ~`. Используйте **только в изолированных окружениях** — контейнерах,
VM, devcontainer-ах, где агент не может навредить основной системе. Пресет
сохраняет deny на `~/.ssh`, `~/.aws`, `*.pem` и `sudo` и ask на `git push --force`.
:::

## Пример: содержимое base

::: details settings.base.json целиком
<<< ../../configs/claude-code/settings.base.json
:::

Остальные пресеты — в
[configs/claude-code/](https://github.com/academici/swissknifeman/tree/main/configs/claude-code).

## Тонкая настройка под проект

Пресет — отправная точка. После применения правьте
`.claude/settings.local.json` под проект или используйте `/permissions` прямо
в Claude Code — интерфейс показывает все правила и файлы-источники.

Типовые доработки:

```json
{
  "permissions": {
    "allow": [
      "Bash(./bin/console *)",
      "WebFetch(domain:laravel.com)"
    ],
    "deny": [
      "Read(storage/oauth-*.key)"
    ],
    "additionalDirectories": ["../shared-lib"]
  }
}
```
