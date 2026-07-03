# Permissions для Claude Code

Готовые пресеты разрешений (пакет `harness`, `packages/harness/configs/claude-code/`)
решают главную боль нового проекта: десятки permission-промптов в первые полчаса
работы. Один запуск `harness permissions` — и агент может выполнять весь типовой
инструментарий стека, а опасные операции остаются под контролем.

> Полная настройка машины (глобальный baseline + лог всех команд агента) —
> в гайде [Настройка окружения Claude Code](../setup/claude).

## Пресеты

| Пресет | Файл | Что разрешает |
|---|---|---|
| `base` | `settings.base.json` | git (push — с подтверждением), gh, файловые операции, curl/wget, jq/rg/sed/awk, make, оркестрация (`Workflow`/`Agent`/`TodoWrite`); deny на секреты и `sudo` |
| `laravel` | `settings.laravel.json` | `php artisan`, composer, pest/phpunit/pint/phpstan/rector, sail, npm/vite |
| `php-package` | `settings.php-package.json` | composer, тесты и линтеры — без artisan |
| `node` | `settings.node.json` | node/npm/npx/pnpm/yarn, tsc, vitest, eslint, prettier |
| `python` | `settings.python.json` | python/pip/pytest, uv, poetry, ruff/black/mypy |
| `docker` | `settings.docker.json` | docker + docker compose; удаление и prune — с подтверждением |
| `product-boundary` | `settings.product-boundary.json` | deny на запись в зависимый пакет (`Write/Edit(vendor/**)`) — граница «проект ↔ пакет» |
| `yolo` | `settings.yolo.json` | `bypassPermissions` — только для изолированных окружений |

Пресет `product-boundary` **opt-in** (не входит в автодетект): применяй его в
проектах-потребителях, которые дорабатывают свои пакеты, чтобы агент не правил
код пакета «по ходу» продуктовой задачи. Подробнее — скилл
[`package-contribution-protocol`](https://github.com/academici/swissknifeman/blob/main/skills/architect/package-contribution-protocol/SKILL.md);
вариант для path-репо (`packages/**`) — в его сниппете `permissions-deny.md`.

Логика каждого пресета трёхуровневая:

- **allow** — повседневный инструментарий стека работает без промптов;
- **ask** — необратимое или внешнее (git push, `migrate:fresh`,
  `docker system prune`, `npm publish`) требует подтверждения;
- **deny** — секреты (`.env`, `*.pem`, `*.key`, `~/.ssh`, `~/.aws`) и `sudo`
  заблокированы всегда.

::: tip rm управляется хуком, не ask-правилами
`rm`/`rmdir` в пресетах **не стоят в ask**: их жёстко блокирует deny_hard
auto-approve-хука, а внутри доверенных директорий (machine-owned allowlist
`safe-dirs.json` в корне монорепо swissknifeman, команда `harness safe-dirs`) —
пропускает.
Статическое ask-правило здесь только мешало бы: hook-`allow` не пробивает ask
из settings (официальная семантика permissions), и rm в safe-dirs промптил бы
всегда. Если ask-правила rm остались в проекте от старых пресетов — сними их:
`harness safe-dirs prune-ask --global --all-projects`.
:::

## Оркестрация: `Workflow` / `Agent` / `TodoWrite`

В `allow` пресетов `base` **и** `global` добавлены три инструмента оркестрации —
`Workflow`, `Agent`, `TodoWrite`. Они не привязаны к стеку: доступны в любом
проекте, поэтому живут в универсальном слое (а не в `laravel`/`node`/`python`).

Зачем: при запуске `Workflow` каждый прогон спавнит субагентов (`Agent`),
ведёт план (`TodoWrite`) и сам по себе — вызов инструмента `Workflow`. Без этих
правил Claude Code просил подтверждение **после каждой фазы/стадии**, и длинный
многофазный воркфлоу превращался в череду промптов. Авто-allow снимает эту боль.

Безопасность не страдает: разрешён лишь сам факт вызова инструмента. Субагент,
порождённый `Agent`/`Workflow`, исполняет свои Bash/Read/Edit-вызовы **через тот
же permission-слой** — широкий allow тут ничего не открывает, а `TodoWrite`
правит только локальный список задач. Точечное правило на конкретного субагента
(`Agent(Explore)`) по-прежнему работает поверх (см. раздел «Синтаксис правил»).

Источник истины — пресеты; чтобы правило долетело до уже онбордженного проекта,
перекати его (`harness permissions --target .` или `--global`).

## CLI `harness permissions`

```bash
# base + автодетект стека по маркерам проекта
harness permissions --target ~/projects/my-laravel-app

# Явный набор пресетов
harness permissions --target . --preset base,laravel,docker

# Превью без записи
harness permissions --target . --dry-run

# Список доступных пресетов
harness permissions --list

# В шаримый settings.json вместо локального
harness permissions --target . --file settings.json
```

Автодетект использует те же маркеры, что и `skiller vendor`:

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
```json
{
  "$schema": "https://json.schemastore.org/claude-code-settings.json",
  "permissions": {
    "defaultMode": "acceptEdits",
    "allow": [
      "Bash(git *)",
      "Bash(gh pr *)", "Bash(gh issue *)", "Bash(gh run *)",
      "Bash(gh api *)", "Bash(gh repo view *)",
      "Bash(mkdir *)", "Bash(touch *)", "Bash(cp *)", "Bash(mv *)",
      "Bash(ln -s *)", "Bash(chmod +x *)",
      "Bash(tar *)", "Bash(zip *)", "Bash(unzip *)",
      "Bash(rg *)", "Bash(jq *)", "Bash(sed *)", "Bash(awk *)",
      "Bash(sort *)", "Bash(uniq *)", "Bash(xargs rg *)", "Bash(make *)",
      "Bash(curl *)", "Bash(wget *)",
      "Bash(* --version)", "Bash(* --help)",
      "WebFetch(domain:github.com)",
      "WebFetch(domain:raw.githubusercontent.com)",
      "WebFetch(domain:api.github.com)",
      "Workflow", "Agent", "TodoWrite"
    ],
    "ask": [
      "Bash(git push *)", "Bash(git reset --hard *)", "Bash(git clean *)",
      "Bash(chmod -R *)", "Bash(chown *)"
    ],
    "deny": [
      "Read(.env)", "Read(.env.local)", "Read(.env.production)",
      "Read(**/*.pem)", "Read(**/*.key)",
      "Read(~/.ssh/**)", "Read(~/.aws/**)", "Bash(sudo *)"
    ]
  }
}
```
:::

> Источник пресета — `packages/harness/configs/claude-code/settings.base.json`
> (фрагмент выше — копия для удобства). Остальные пресеты —
> [packages/harness/configs/claude-code/](https://github.com/academici/swissknifeman/tree/main/packages/harness/configs/claude-code).

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
