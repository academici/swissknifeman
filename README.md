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

## Структура

```
skills/                    # скилл = папка + SKILL.md + snippets/ (+ upstream.json у внешних)
├── architect/  (9)        # архитектура, API, данные, безопасность
├── devops/     (6)        # Docker, CI/CD, GitOps
├── founder/    (5)        # идеи, анализ конкурентов, питчи
├── imported/   (12)       # внешние super-skills (отслеживаются через upstream.json)
├── operator/   (5)        # инциденты, runbook, postmortem
├── oss-dev/    (5+refs)   # open-source разработка + языковые references/
├── php/        (7)        # Laravel, пакеты, тесты, паттерны
├── pm/         (8)        # BRD, PRD, roadmap, монетизация
├── quality/    (4)        # code review, тесты, техдолг
└── roles/      (4)        # персоны: tech-lead, startup-cto, ...

profiles/                  # тип проекта → набор bucket-ов
configs/                   # готовые конфиги: пресеты permissions для Claude Code
references/                # каталог внешних источников (что брать, статус)
adapters/                  # доки по интеграции: claude-code, cursor, perplexity
scripts/                   # validate, update-upstreams, scanner, apply-permissions
generate-skill/            # мета-скилл создания новых скиллов
skills.json                # реестр (генерируется sync.sh, с provenance)
docs/                      # документация (VitePress)
```

> `references/` в корне — каталог внешних источников для отбора;
> `skills/oss-dev/references/` — языковые reference-файлы внутри bucket-а. Это разные вещи.

## Установка

Установщик сам определяет тип проекта и ставит подходящий набор скиллов:

```bash
# Laravel-проект (artisan+composer.json) → architect, php, devops, quality, operator
cd ~/projects/my-laravel-app
~/projects/packages/swissknifeman/install.sh --target . --agent claude

# Obsidian vault (.obsidian/) → architect, pm, founder, operator, roles, imported
~/projects/packages/swissknifeman/install.sh --target ~/vaults/brain

# Превью без установки
./install.sh --target ~/projects/my-app --list

# Явный профиль / bucket-ы / исключения
./install.sh --target . --profile php-package
./install.sh --target . --buckets php,quality --exclude botkit

# Глобально в home (~/.claude/skills)
./install.sh --target ~ --agent claude

# Legacy-режим (deprecated): копия bucket-а как есть
./install.sh ~/.ai/skills php
```

**`--agent claude`** раскладывает скиллы плоско (`.claude/skills/<name>/SKILL.md`) —
Claude Code не видит вложенные bucket-структуры. Коллизии имён разрешаются
префиксом bucket-а. Внимание: установка в общий `~/.claude/skills` может
перекрыть одноимённые скиллы, поставленные не отсюда. Переустановка чистит
только то, что ставила сама (манифест `.swissknifeman-manifest.json`).

Проект может зафиксировать свою конфигурацию в `.swissknife.json`
(см. [.swissknife.example.json](.swissknife.example.json)) — приоритет:
флаги → `.swissknife.json` → автодетект.

## Пресеты permissions для Claude Code

Готовые наборы разрешений ([configs/claude-code/](configs/claude-code/README.md)),
чтобы агент в новом проекте работал без permission-промптов:

```bash
# base + автодетект стека (artisan → laravel, package.json → node, ...)
./scripts/apply-permissions.sh --target ~/projects/my-laravel-app

# Явный набор / превью
./scripts/apply-permissions.sh --target . --preset base,laravel,docker
./scripts/apply-permissions.sh --target . --dry-run
```

Пресеты: `base`, `laravel`, `php-package`, `node`, `python`, `docker`, `yolo`.
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

`skills.json` генерируется `./sync.sh --update-registry`: путь, версия, sha256
и provenance каждого скилла (`source: local|github|http`, `upstream` URL,
`fetched_at`).

```bash
./sync.sh --update-registry                    # пересобрать реестр
BRAIN_PATH=~/path/to/brain ./sync.sh           # + зеркало в brain/.ai/skills-registry/
```

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
| `sync-to-brain.yml` | Ежедневное зеркало в academici/brain |
| `scanner-pr.yml` | Еженедельный PR от сканера |
