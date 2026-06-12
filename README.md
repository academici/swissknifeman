# academici/swissknifeman

> Универсальный личный реестр AI-скиллов и сниппетов: один источник истины,
> установка в любой проект и любую IDE, отслеживание внешних источников.

**Документация:** [academici.github.io/swissknifeman](https://academici.github.io/swissknifeman/)
(локально: `npm install && npm run docs:dev`)

## Для чего этот пакет

Единая библиотека скиллов (provider-neutral `SKILL.md` + `snippets/`) под мои
сценарии работы:

1. **Документация** — написание и сопровождение технической документации
2. **Obsidian vault** — управление знаниями, заметки, базы знаний
3. **Технические задания** — составление ТЗ (BRD → PRD → архитектура)
4. **PHP-пакеты** — разработка open-source пакетов, в первую очередь Laravel
5. **Крупные Laravel-проекты** — архитектура, паттерны, DevOps, качество

Скиллы накапливаются постепенно: свои — из опыта реальных проектов (AzGuard,
botkit и др.), внешние — выборочно из лучших открытых источников с отслеживанием
обновлений. Каркас универсален: один реестр → установка в Claude Code, Cursor
или любой другой агент.

## Скиллы vs. воркфлоу

Два слоя, которые не надо смешивать:

- **Скиллы** (`skills/`) — утилитарны. Один скилл = один навык, работающий
  **внутри конкретной IDE/агента** (Claude Code, Cursor). Скилл содержит чисто
  навык и не описывает совместное поведение разных систем.
- **Воркфлоу** ([docs/workflows/](docs/workflows/index.md)) — **межсистемный
  слой**: как Perplexity → Claude → Cursor → ревью передают работу друг другу.
  Это методология, а не исполняемый навык; она не привязана к одной IDE.

ТЗ из воркфлоу описывает *что* строить; скиллы — *как* это делать в той IDE,
где запущен агент.

## Структура

```
skills/                    # скилл = папка + SKILL.md + snippets/ (+ upstream.json у внешних)
├── architect/  (9)        # архитектура, API, данные, безопасность
├── devops/     (6)        # Docker, CI/CD, GitOps
├── founder/    (5)        # идеи, анализ конкурентов, питчи
├── imported/   (12)       # внешние super-skills (отслеживаются через upstream.json)
├── operator/   (5)        # инциденты, runbook, postmortem
├── oss-dev/    (6+refs)   # open-source разработка + языковые references/
├── php/        (7)        # Laravel, пакеты, тесты, паттерны
├── pm/         (8)        # BRD, PRD, roadmap, монетизация
├── quality/    (4)        # code review, тесты, техдолг
└── roles/      (4)        # персоны: tech-lead, startup-cto, ...

profiles/                  # тип проекта → набор bucket-ов
configs/                   # готовые конфиги: пресеты permissions для Claude Code
references/                # каталог внешних источников (что брать, статус)
adapters/                  # доки по интеграции: claude-code, cursor, perplexity
docs/workflows/            # межсистемные методологии (Perplexity→Claude→Cursor→ревью)
bin/                       # CLI swissknifeman (connect/vendor/update/status/list/registry/doctor)
scripts/                   # validate, update-upstreams, scanner, apply-permissions
generate-skill/            # мета-скилл создания новых скиллов
skills.json                # реестр (генерируется swissknifeman registry, с provenance)
buckets.json               # метаданные bucket-ов (description/category/tags)
.claude-plugin/            # marketplace.json — нативный marketplace Claude Code (генерируется)
docs/                      # документация (VitePress)
```

> `references/` в корне — каталог внешних источников для отбора;
> `skills/oss-dev/references/` — языковые reference-файлы внутри bucket-а. Это разные вещи.

## Установка

### Шаг 1: CLI (один раз на машину)

```bash
cd ~/projects/packages/swissknifeman
./install.sh        # симлинк ~/.local/bin/swissknifeman → bin/swissknifeman
swissknifeman doctor
```

Дальше всё делается **из каталога проекта** — корень ищется автоматически,
реестру не нужно знать о ваших проектах (карта подключений копится в
`~/.swissknifeman/projects.json`). Справочник команд: [docs/guide/cli.md](docs/guide/cli.md).

### Claude Code: plugin marketplace (рекомендуется)

Репозиторий — нативный marketplace плагинов Claude Code: каждый bucket = плагин,
скиллы получают неймспейс `<bucket>:<skill>` (например `php:laravel-packages`).
Скиллы **не копируются** в проект — живут в кэше Claude Code и обновляются отсюда.

```bash
cd ~/projects/my-app
swissknifeman connect                      # автодетект профиля → settings.local.json

# Превью / явный набор / миграция со старого вендоринга
swissknifeman connect --dry-run
swissknifeman connect --plugins php,quality
swissknifeman connect --cleanup-vendored
```

Версия плагина = git SHA: правки скиллов подтягиваются в проекты после
локального **коммита** (пуш не нужен) — `/plugin marketplace update swissknifeman`
или перезапуск сессии. Манифесты плагинов (`.claude-plugin/`) генерируются
`swissknifeman registry`.

### Cursor / другие агенты: вендоринг

`swissknifeman vendor` сам определяет тип проекта и копирует подходящий набор скиллов:

```bash
# Laravel-проект (artisan+composer.json) → architect, php, devops, quality, operator
cd ~/projects/my-laravel-app
swissknifeman vendor --agent cursor

# Obsidian vault (.obsidian/) → architect, pm, founder, operator, roles, imported
cd ~/vaults/brain && swissknifeman vendor

# Превью без установки
swissknifeman vendor --list

# Явный профиль / bucket-ы / исключения
swissknifeman vendor --profile php-package
swissknifeman vendor --buckets php,quality --exclude botkit
```

### Обновление подключённых проектов

```bash
cd ~/projects/my-app && swissknifeman update   # текущий проект (канал детектится сам)
swissknifeman update --all                     # все зарегистрированные
swissknifeman status                           # отчёт по текущему проекту
swissknifeman list                             # карта проектов
```

Переустановка чистит только то, что ставила сама (манифест
`.swissknifeman-manifest.json` в обоих режимах раскладки); существующие чужие
папки скиллов — ошибка-коллизия, перезапись только с `--force`.
Режим `--agent claude` (плоский вендоринг) оставлен для совместимости,
для Claude Code предпочтителен marketplace.

Проект может зафиксировать свою конфигурацию в `.swissknife.json`
(см. [.swissknife.example.json](.swissknife.example.json)) — приоритет:
флаги → `.swissknife.json` → автодетект. Файл проходит схема-валидацию
(опечатка в ключе → ошибка с подсказкой).

### Корневой хаб скиллов (generate-hub.sh)

После подключения скиллов сгенерируйте в проекте «разветвитель» — приоритеты
чтения источников + индекс установленных скиллов с правилами поиска:

```bash
swissknifeman update          # регенерирует хаб, если он уже есть в проекте
./scripts/generate-hub.sh --target ~/projects/my-app   # или флаг --hub у connect/vendor
```

- проект **с Laravel Boost** (есть `boost.json`) → пишется фрагмент
  `.ai/guidelines/swissknifeman-hub.md`; в CLAUDE.md/AGENTS.md его вставит сам
  Boost при `php artisan boost:update`;
- проект **без Boost** → managed-блок в `CLAUDE.md` между маркерами
  `<!-- swissknifeman:hub:start/end -->`; пользовательский контент вне маркеров
  не затрагивается, повторный запуск идемпотентен.

Установленное определяется по `enabledPlugins` в `.claude/settings*.json`
(канал marketplace) и/или манифестам `.swissknifeman-manifest.json`
(канал вендоринга). Приоритеты и таблица роутинга «тип задачи → скилл» —
[docs/routing.md](docs/routing.md); политика совместимости с Laravel Boost —
[docs/boost-compatibility.md](docs/boost-compatibility.md); устройство единого
источника истины скиллов в проекте — скилл `general/skills-ssot`.

## Пресеты permissions для Claude Code

Готовые наборы разрешений ([configs/claude-code/](configs/claude-code/README.md)),
чтобы агент в новом проекте работал без permission-промптов:

```bash
# base + автодетект стека (artisan → laravel, package.json → node, ...)
./scripts/apply-permissions.sh --target ~/projects/my-laravel-app

# Явный набор / превью
./scripts/apply-permissions.sh --target . --preset base,laravel,docker
./scripts/apply-permissions.sh --target . --dry-run

# Глобальный baseline (read-only команды) + hook-логгер всех Bash-команд в ~/.claude
./scripts/apply-permissions.sh --global
```

Пресеты: `base`, `laravel`, `php-package`, `node`, `python`, `docker`, `yolo`, `global`.
Merge в `.claude/settings.local.json` без затирания существующих правил, с бэкапом.
Опасные операции (`git push`, `rm -rf`, `migrate:fresh`) — через ask, секреты
(`.env`, ключи, `~/.ssh`) — deny.

## Профили

| Профиль | Автодетект | Bucket-ы |
|---|---|---|
| `obsidian-vault` | `.obsidian/` | architect, pm, founder, operator, roles, imported |
| `laravel-project` | `artisan` + `composer.json` | architect, php, devops, quality, operator |
| `php-package` | `composer.json` без `artisan` | oss-dev, php, quality, devops |
| `standalone` | нет маркеров | все + generate-skill |

## Upstream-sync: отслеживание внешних скиллов

Скилл, взятый из внешнего источника, содержит `upstream.json` рядом со `SKILL.md`:

```json
{
  "schema_version": 1,
  "source": "github",
  "repo": "get-zeked/research-knowledge-super-skill",
  "strategy": "notify",
  "files": [
    { "path": "SKILL.md",
      "url": "https://raw.githubusercontent.com/.../SKILL.md",
      "sha256": "…", "fetched_at": "2026-06-11" }
  ]
}
```

- **Нет `upstream.json`** → скилл самописный, sync-тулинг его не трогает
- **`strategy: replace`** → файл зеркалируется как есть, обновления применяются автоматически
- **`strategy: notify`** → локальная копия адаптирована; об обновлениях апстрима
  только сообщается, файл не перезаписывается

```bash
./scripts/update-upstreams.sh --check        # отчёт: что устарело (exit 10 = есть изменения)
./scripts/update-upstreams.sh --apply        # применить replace-обновления, записать sha
./scripts/update-upstreams.sh --apply --force --skill imported/research   # перезаписать конфликт
```

GitHub Action `upstream-sync.yml` еженедельно проверяет все апстримы и открывает
PR с диффом — изменения чужих репозиториев попадают в main только после ревью.

## Реестр

`skills.json` генерируется `swissknifeman registry`: путь, версия, sha256
и provenance каждого скилла (`source: local|github|http`, `upstream` URL,
`fetched_at`).

```bash
swissknifeman registry                         # пересобрать реестр + манифесты + граф
```

Отдельного зеркалирования в brain больше нет: brain — обычный потребляющий
проект (`cd <brain> && swissknifeman vendor`, дальше `swissknifeman update`).

## Добавление скиллов

- **Свой скилл:** папка + `SKILL.md` по `SKILL_TEMPLATE.md` (см. [CONTRIBUTING.md](CONTRIBUTING.md))
- **Внешний скилл:** папка + `upstream.json` → `./scripts/update-upstreams.sh --apply --skill ...`
- **Источники-кандидаты:** каталог [references/](references/README.md) — что брать выборочно и откуда

## Scanner

Извлечение сниппетов из локальных проектов (пути в `.skills-scanner.json`):

```bash
./scripts/scan-skills.sh              # найти кандидатов
./scripts/scan-skills.sh --extract    # анонимизировать в .scanner-output/
./scripts/scan-and-pr.sh              # commit + PR
```

## CI/CD

| Workflow | Назначение |
|----------|------------|
| `validate.yml` | `scripts/validate.sh`: frontmatter, upstream.json, profiles, манифесты |
| `upstream-sync.yml` | Еженедельная проверка апстримов → PR с диффом |
| `sha256-update.yml` | Пересчёт хешей реестра при пуше |
| `scanner-pr.yml` | Еженедельный PR от сканера |
