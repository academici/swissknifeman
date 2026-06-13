# GitHub Flow Skill — Анализ и Спецификация

> **Назначение документа:** глубокий анализ существующего покрытия в `academici/swissknifeman`,
> выявление пробелов и полная спецификация нового скилла `github-flow` для агентов
> Claude (Code), Cursor и Windsurf — охватывающего весь цикл публикации PHP-пакета:
> Issues → PR → Conventional Commits → SemVer → Packagist / Composer metadata → pre-deploy checklist.

---

## 1. Что уже есть в репозитории

Репозиторий организован по бакетам (`skills/<bucket>/<skill>/`); конфиг `.swissknife.example.json`
задаёт `project_type`, `buckets`, `agent` (claude | cursor | generic).

### 1.1 Покрытые области (существующие скиллы)

| Скилл | Бакет | Что покрывает | Пробел |
|---|---|---|---|
| `git-commit-rules` | `general` | Базовые правила коммитов | Нет Conventional Commits scope/breaking, нет PHP-контекста |
| `ticket-workflow` | `general` | Работа с тикетами | Нет связи Issue → PR → Version |
| `oss-development` | `oss-dev` | Общие OSS-практики | Нет пошагового GitHub-флоу |
| `oss-governance` | `oss-dev` | Лицензии, CoC, governance | Нет release-gate checklist |
| `release-engineering` | `oss-dev` | Release-процесс | Не специфичен для PHP/Composer/Packagist |
| `dependency-audit` | `oss-dev` | Аудит зависимостей | Не связан с версионированием |
| `dx-design` | `oss-dev` | Developer experience | Нет |
| `mcp-development` | `general` | MCP-протокол | Нет |
| `cross-layer-change-checklist` | `general` | Чеклист изменений | Близко, но не GitHub-специфично |
| `project-map` | `general` | Карта проекта | Нет |
| `packages-stack` | `general` | Стек пакетов | Нет версионной стратегии |

### 1.2 Выявленные пробелы

Ни один существующий скилл не закрывает следующие области в связке:

1. **Полный lifecycle Issue → Branch → Commit → PR → Merge → Tag → Release**
2. **Conventional Commits** с PHP/Laravel-специфичными типами и scope
3. **SemVer-оракул** — автоматическое определение следующей версии по типам коммитов
4. **PHP-package metadata** — `composer.json` keywords, type, extra, PHP-версия, stability
5. **Packagist / GitHub Releases** — последовательность действий перед деплоем
6. **PR-шаблоны** и автоматическое заполнение Labels, Milestone, связанных Issues
7. **CHANGELOG автогенерация** по стандарту Keep a Changelog + CC

---

## 2. Архитектура нового скилла `github-flow`

### 2.1 Размещение и конфигурация

```
skills/
└── general/
    └── github-flow/              ← новый скилл
        ├── skill.md              ← основной файл (загружается агентом)
        ├── commit-types.json     ← машиночитаемая таблица типов
        ├── version-oracle.md     ← SemVer-логика
        └── php-package-gate.md  ← pre-deploy чеклист для PHP-пакетов
```

Скилл добавляется в `buckets.json` и `skills.json`. Для PHP-пакетов он должен
включаться автоматически через профиль `php-package` в `profiles/`.

### 2.2 Подключение в `.swissknife.json` проекта

```json
{
  "project_type": "php-package",
  "buckets": ["php", "oss-dev", "general"],
  "skills_path": ".claude/skills",
  "agent": "claude"
}
```

При `project_type: php-package` менеджер должен автоматически добавлять
`github-flow` в установку без явного указания в `buckets`.

---

## 3. Спецификация `skill.md` — полный текст скилла

Ниже — готовый текст файла `skills/general/github-flow/skill.md`,
написанный в формате, совместимом с `.claude-plugin` и Cursor Rules.

---

### 3.1 Заголовок и meta

```markdown
---
name: github-flow
description: >
  Полный GitHub-флоу для PHP-пакетов: Issues, PR, Conventional Commits,
  SemVer-оракул, Packagist-деплой и CHANGELOG. Агент запрашивает
  недостающий контекст перед каждым действием.
tags: [github, git, php, composer, semver, release, issues, pr]
applies_to: [php-package, laravel-project]
agent_compat: [claude, cursor, windsurf, generic]
version: 1.0.0
---
```

### 3.2 Блок: Issues

````markdown
## Issues

### Обязательные вопросы перед созданием Issue

Агент ДОЛЖЕН запросить у пользователя:
1. **Тип** — bug | feature | enhancement | security | docs | refactor | chore
2. **Приоритет** — critical | high | normal | low
3. **Затронутый компонент** — (список из project-map, если есть)
4. **Версия пакета**, в которой воспроизводится проблема

### Именование Issue

```
[TYPE] Краткое описание в повелительном наклонении (до 72 символов)
```

Примеры:
- `[bug] Fix middleware ordering in ThreatDetector pipeline`
- `[feature] Add entity-scoped role resolution via context bag`
- `[security] Prevent SQL injection in dynamic scope builder`

### Labels

Агент назначает labels автоматически по типу:

| Тип Issue | Label(s) |
|---|---|
| bug | `bug`, `needs-triage` |
| feature | `enhancement` |
| security | `security`, `priority:critical` |
| docs | `documentation` |
| refactor | `refactor`, `tech-debt` |
| chore | `chore` |

Дополнительные meta-labels: `semver:patch`, `semver:minor`, `semver:major` —
проставляются агентом на основе оценки влияния (см. SemVer-оракул).
````

### 3.3 Блок: Ветки

````markdown
## Branch Naming

Формат:
```
<type>/<issue-number>-<slug>
```

Правила slug:
- Только строчные буквы, цифры и дефисы
- Максимум 50 символов после `<type>/`
- Слова разделяются дефисом, не underscore

Типы веток:
- `feat/` — новая функциональность
- `fix/` — исправление бага
- `hotfix/` — критический патч в main/master
- `docs/` — только документация
- `refactor/` — рефакторинг без функциональных изменений
- `chore/` — зависимости, CI, инфраструктура
- `security/` — уязвимости

Примеры:
```
feat/42-entity-scoped-roles
fix/17-middleware-stack-order
hotfix/55-injection-bypass
docs/61-api-reference-update
security/38-sql-injection-scope-builder
```

Агент создаёт ветку автоматически после подтверждения Issue, используя
`gh issue view <N>` для получения заголовка.
````

### 3.4 Блок: Conventional Commits

````markdown
## Conventional Commits

Стандарт: https://www.conventionalcommits.org/en/v1.0.0/

### Формат

```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

### Таблица типов (PHP/Laravel-контекст)

| Тип | SemVer bump | Когда использовать |
|---|---|---|
| `feat` | MINOR | Новая публичная функция или поведение |
| `fix` | PATCH | Исправление бага |
| `docs` | — (нет bump) | Только документация |
| `style` | — | Форматирование, без логики |
| `refactor` | — | Рефакторинг без изменения API |
| `perf` | PATCH | Оптимизация производительности |
| `test` | — | Тесты |
| `build` | — | composer.json, CI, build-скрипты |
| `ci` | — | GitHub Actions, workflows |
| `chore` | — | Обслуживание, зависимости |
| `security` | PATCH или MAJOR | Исправление уязвимости |
| `revert` | зависит | Откат коммита |

**BREAKING CHANGE:** добавляется в footer как `BREAKING CHANGE: <description>`
или через `!` после типа: `feat!: ...` → MAJOR bump.

### Scopes для PHP-пакетов

Агент предлагает scope из списка, определённого в `commit-types.json`
текущего проекта. Если файл отсутствует — использует дефолтный набор:

```
middleware | provider | facade | contract | model | migration |
config | command | gate | policy | event | listener |
exception | cast | rule | observer | scope | macro
```

### Правила описания (subject)

- Повелительное наклонение: "add", "fix", "remove" — не "added", не "adding"
- Нет заглавной буквы в начале
- Нет точки в конце
- До 72 символов

### Автозаполнение агентом

Перед коммитом агент ДОЛЖЕН:
1. Показать сгенерированное сообщение пользователю
2. Указать предполагаемый SemVer-bump
3. Запросить подтверждение или правку
4. Добавить `Closes #<N>` в footer, если коммит закрывает Issue

### Примеры

```
feat(gate): add entity-scoped role resolution via ContextBag

Resolves the ambiguity when a user holds roles in multiple entity
contexts simultaneously. Introduces ContextBag::forEntity() helper.

Closes #42
```

```
fix(middleware): correct threat level evaluation order in pipeline

Previously, HIGH threats could bypass the rate-limiter if the
injection detector ran after it.

Closes #17
```

```
feat!: remove deprecated withPermissions() method

BREAKING CHANGE: withPermissions() was deprecated in v2.3.0.
Use authorize() with a Gate contract instead.
```
````

### 3.5 Блок: Pull Requests

`````markdown
## Pull Requests

### Обязательные вопросы перед созданием PR

Агент ДОЛЖЕН запросить или вычислить:
1. **Связанные Issues** (через `Closes #N` или `Refs #N`)
2. **Тип изменения** — bugfix | feature | breaking | security | docs
3. **Затронутые компоненты** (из diff)
4. **Нужен ли CHANGELOG-entry**

### Шаблон заголовка PR

```
<type>(<scope>): <description> (#<issue>)
```

Пример:
```
feat(gate): entity-scoped role resolution (#42)
```

### Шаблон тела PR (агент заполняет автоматически)

````markdown
## Summary
<!-- Что сделано и зачем -->

## Changes
- [ ] Список конкретных изменений

## Breaking Changes
<!-- BREAKING CHANGE или "None" -->

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests added/updated
- [ ] Manual testing steps

## Checklist
- [ ] Conventional Commit message applied
- [ ] CHANGELOG updated
- [ ] composer.json version NOT bumped (bumped on release only)
- [ ] PHPDoc blocks updated
- [ ] No debug code left

## Related Issues
Closes #N
````

### Labels на PR

Назначаются автоматически зеркально с Issue плюс:
- `ready-for-review` — когда PR не draft
- `needs-changelog` — если CHANGELOG не обновлён
- `breaking-change` — если есть BREAKING CHANGE footer
`````

### 3.6 Блок: SemVer-оракул

````markdown
## SemVer Oracle — автоопределение следующей версии

### Алгоритм

Агент анализирует коммиты между последним тегом и HEAD:

```
1. Есть хотя бы один `BREAKING CHANGE` footer или `!` тип → MAJOR
2. Есть хотя бы один `feat` (без breaking) → MINOR
3. Есть `fix`, `perf`, `security` → PATCH
4. Только `docs`, `style`, `test`, `ci`, `chore` → NO BUMP (только pre-release tag)
```

### Вопросы агента перед деплоем

```
Текущая версия: X.Y.Z (из composer.json / последнего тега)
Обнаруженные типы коммитов: feat(2), fix(1), docs(3)
Предлагаемая следующая версия: X.(Y+1).0

Подтвердить? [Y] Изменить вручную? [введи версию] Отменить? [N]
```

### Формат тегов

```
vX.Y.Z          — stable release
vX.Y.Z-alpha.N  — alpha
vX.Y.Z-beta.N   — beta
vX.Y.Z-rc.N     — release candidate
```

Тег создаётся ТОЛЬКО после:
1. Подтверждения версии пользователем
2. Обновления `composer.json` → `"version": "X.Y.Z"`
3. Обновления CHANGELOG.md
4. Merge PR в main/master
````

### 3.7 Блок: PHP Package Metadata

````markdown
## PHP Package Metadata (composer.json)

### Обязательные поля для публикации на Packagist

Агент проверяет наличие и корректность ВСЕХ полей перед деплоем:

```json
{
    "name": "vendor/package-name",
    "description": "One-line description (50-100 chars)",
    "type": "library",
    "keywords": ["laravel", "php", "<domain-keyword-1>", "<domain-keyword-2>"],
    "license": "MIT",
    "authors": [{"name": "...", "email": "..."}],
    "require": {
        "php": "^8.1|^8.2|^8.3",
        "illuminate/support": "^10.0|^11.0|^12.0"
    },
    "require-dev": {...},
    "autoload": {
        "psr-4": {"Vendor\\Package\\": "src/"}
    },
    "extra": {
        "laravel": {
            "providers": ["Vendor\\Package\\PackageServiceProvider"],
            "aliases": {}
        }
    },
    "minimum-stability": "stable",
    "prefer-stable": true
}
```

### Keywords (теги для Packagist)

Агент запрашивает домен пакета и предлагает keywords из следующих категорий:

**Базовые (всегда):** `laravel`, `php`, `package`

**По домену:**
| Домен | Рекомендуемые keywords |
|---|---|
| Permissions / ACL | `permissions`, `authorization`, `acl`, `rbac`, `roles`, `gates` |
| Security | `security`, `middleware`, `threat-detection`, `injection` |
| Auth | `authentication`, `auth`, `guards` |
| Bot / Telegram | `telegram`, `bot`, `botkit`, `webhook` |
| Admin panel | `filament`, `admin`, `dashboard` |
| API | `api`, `rest`, `resource` |

Максимум 5-7 keywords (Packagist не индексирует более ~10 эффективно).

### Versioning в composer.json

- Поле `"version"` в `composer.json` — опционально для Packagist (берётся из тега)
- Если присутствует — ДОЛЖНО совпадать с тегом
- Агент синхронизирует его автоматически на шаге деплоя
````

### 3.8 Блок: Pre-Deploy Checklist

````markdown
## Pre-Deploy Gate — чеклист перед созданием тега/релиза

Агент выполняет проверки последовательно и останавливается при fail:

### Автоматические проверки (агент читает файлы)

- [ ] `composer.json` валиден (`composer validate --strict`)
- [ ] Версия в `composer.json` (если задана) = предполагаемому тегу
- [ ] `CHANGELOG.md` содержит раздел для новой версии с датой
- [ ] Нет незакрытых `TODO:` / `FIXME:` / `@deprecated` без задокументированного плана
- [ ] Все `use` statements не содержат dev-пакеты в production-классах
- [ ] Нет `dd()`, `dump()`, `var_dump()`, `ray()` в src/
- [ ] `.gitignore` содержит `vendor/`, `.env`
- [ ] GitHub Actions (если есть) прошли на целевой ветке

### Вопросы агента пользователю

1. Прогоняли ли тесты локально? `vendor/bin/phpunit` / `php artisan test`
2. Обновлён ли README для новых возможностей?
3. Есть ли breaking changes, задокументированные в UPGRADE.md?
4. Нужен ли GitHub Release с release notes (авто из CHANGELOG)?

### Последовательность деплоя

```
1. git checkout main && git pull
2. [агент] bump version in composer.json
3. [агент] update CHANGELOG.md — дата раздела
4. git add composer.json CHANGELOG.md
5. git commit -m "chore(release): bump version to vX.Y.Z"
6. git tag vX.Y.Z -m "Release vX.Y.Z"
7. git push origin main --tags
8. [агент] создать GitHub Release через API (из CHANGELOG-секции)
9. [Packagist] обновляется автоматически через webhook
```
````

### 3.9 Блок: CHANGELOG

`````markdown
## CHANGELOG (Keep a Changelog)

Формат: https://keepachangelog.com/en/1.1.0/

### Структура раздела

````markdown
## [X.Y.Z] - YYYY-MM-DD

### Added
- feat-коммиты

### Changed
- Изменения поведения без breaking

### Deprecated
- Помечено к удалению

### Removed
- Удалённый функционал (breaking)

### Fixed
- fix-коммиты

### Security
- security-коммиты
````

### Автозаполнение агентом

Агент генерирует CHANGELOG-секцию автоматически из коммитов:
```
git log vX.Y.Z-1..HEAD --pretty=format:"%s" --no-merges
```
Фильтрует по типу → раскладывает по подразделам → запрашивает подтверждение.
`````

---

## 4. Файл `commit-types.json` — машиночитаемая конфигурация

Размещается в корне PHP-пакета как `.swissknife.commit-types.json`
или в `.claude/` для Claude Code. Позволяет кастомизировать scopes под проект.

```json
{
  "$schema": "https://swissknifeman.dev/schemas/commit-types.json",
  "project": "vendor/my-package",
  "default_branch": "main",
  "scopes": [
    "middleware", "provider", "facade", "contract",
    "model", "config", "command", "gate", "policy",
    "event", "listener", "exception", "rule", "scope"
  ],
  "labels": {
    "feat":     { "semver": "minor", "color": "0075ca" },
    "fix":      { "semver": "patch", "color": "d73a4a" },
    "security": { "semver": "patch", "color": "e4e669", "priority": "critical" },
    "docs":     { "semver": null,    "color": "0075ca" },
    "breaking": { "semver": "major", "color": "b60205" }
  },
  "release_branch": "main",
  "changelog_path": "CHANGELOG.md",
  "packagist": {
    "vendor": "your-vendor",
    "auto_webhook": true
  }
}
```

---

## 5. Интеграция с IDE и агентами

### 5.1 Claude Code (`.claude/`)

```
.claude/
├── skills/
│   └── github-flow/
│       ├── skill.md            ← основной файл
│       ├── commit-types.json
│       ├── version-oracle.md
│       └── php-package-gate.md
└── CLAUDE.md                   ← @-import скилла
```

В `CLAUDE.md` добавить:
```markdown
@.claude/skills/github-flow/skill.md
```

### 5.2 Cursor (`.cursor/rules/`)

Создать `.cursor/rules/github-flow.mdc`:
```
---
description: GitHub flow for PHP packages
globs: ["composer.json", "CHANGELOG.md", ".github/**"]
alwaysApply: false
---

[вставить содержимое skill.md]
```

Файл активируется автоматически при редактировании `composer.json` или
файлов в `.github/`.

### 5.3 Windsurf (`.windsurf/rules/`)

Аналогично Cursor, файл `github-flow.md` в `.windsurf/rules/`.
Windsurf поддерживает `glob`-активацию с версии 1.x.

### 5.4 GitHub Copilot (`.github/copilot-instructions.md`)

Добавить в `.github/copilot-instructions.md`:
```markdown
## Git & Release Workflow
Follow Conventional Commits (conventionalcommits.org).
PHP package scopes: middleware, provider, gate, policy, rule, scope.
SemVer: feat→minor, fix/security→patch, BREAKING CHANGE→major.
Always update CHANGELOG.md before tagging a release.
```

---

## 6. Сравнение покрытия: до и после скилла

| Область | До (существующие скиллы) | После `github-flow` |
|---|---|---|
| Issue naming | `ticket-workflow` (частично) | Полный шаблон с типами и labels |
| Branch naming | Нет | Формат `type/N-slug` |
| Commit message | `git-commit-rules` (базово) | Conventional Commits + PHP scopes |
| SemVer bump | Нет | Автооракул по типам коммитов |
| PR шаблон | Нет | Полный шаблон с чеклистом |
| PHP metadata | `packages-stack` (частично) | `composer.json` gate + keywords |
| CHANGELOG | `release-engineering` (общо) | Keep a Changelog + автогенерация |
| Pre-deploy gate | `cross-layer-change-checklist` | Специфичный для PHP/Packagist |
| Packagist deploy | Нет | Пошаговая последовательность |
| Агент-вопросы | Нет | Обязательные clarifying questions |

---

## 7. Рекомендуемая последовательность внедрения

1. Создать `skills/general/github-flow/` со всеми файлами из §3 и §4
2. Добавить скилл в `skills.json` и `buckets.json` (бакет `general`)
3. Добавить `github-flow` в профиль `profiles/php-package.json`
4. Добавить `.swissknife.commit-types.json` в каждый PHP-пакет
5. Для AzGuard и botkit-dev: добавить `.github/PULL_REQUEST_TEMPLATE.md` и `ISSUE_TEMPLATE/`
6. Настроить Packagist webhook для автопубликации при push тега
7. Добавить GitHub Actions workflow `release.yml`:
   ```yaml
   on:
     push:
       tags: ['v*.*.*']
   jobs:
     release:
       runs-on: ubuntu-latest
       steps:
         - uses: softprops/action-gh-release@v2
           with:
             body_path: CHANGELOG_LATEST.md
   ```

