# Skills System — Master Plan v3

> **Статус:** Итерация 3 (финал) · Дата: 10.06.2026  
> **Исполнитель:** Fable (Claude Code Agent)  
> **Источник истины:** `academici/brain` → `academici/skills`

---

## Executive Summary

Система скиллов строится как **независимый репозиторий-реестр** (`academici/skills`), который:

1. Является единственным источником истины — `SKILL.md` провайдер-нейтрален
2. Каждый скилл — **папка-плагин** с собственным `SKILL.md` + `snippets/` + опциональный `adapters/`
3. Совместим с уже существующим `skills-lock.json` schema в `brain` (version 3, buckets, sha256)
4. Расширяет существующие 36 скиллов из `brain` новыми доменами: `devops`, `php`, `laravel`, `roles`
5. Поддерживает Laravel Boost — пакеты публикуют свои скиллы через `vendor:publish`

---

## 1. Анализ существующего `brain`

### Текущее состояние `skills-lock.json` (version 3)

Уже есть **36 скиллов** в 6 bucket-ах:

| Bucket | Скиллы | Зрелость |
|---|---|---|
| `founder` | idea-discovery, competitive-analysis, new-project, risk-assessment, pitch-deck | draft |
| `pm` | brd, prd-from-brd, business-process, product-roadmap, go-to-market, monetization-design, requirement-critic, unit-economics | draft |
| `architect` | architecture, api-design, data-schema, agent-design, eval-design, security-design, observability-design, legal-compliance, tech-stack-selection | draft |
| `oss-dev` | oss-development, oss-governance, release-engineering, dependency-audit, dx-design | draft |
| `quality` | code-review, test-strategy, tech-debt-audit, refactoring-plan | draft |
| `operator` | incident-response, postmortem, runbook, oncall-rotation, capacity-planning | draft |

**Что отсутствует и нужно добавить:**
- Весь `devops` домен (Docker, CI/CD, GitOps) — 0 скиллов
- PHP/Laravel специфика — только `references/oss-php.md`, нет отдельных скиллов
- Roles как отдельные персоны (tech-lead, startup-cto) — нет
- Сниппеты — нет ни одного кодового файла

---

## 2. Архитектурный принцип: Skill-as-Plugin

### Правило папки

Каждый скилл — директория. Плоские `.md` файлы допускаются только как `references/` внутри другого скилла.

```
skills/
└── {bucket}/
    └── {skill-name}/          ← папка-плагин
        ├── SKILL.md            ← канонический, провайдер-нейтральный
        ├── snippets/           ← кодовые файлы (опционально, но рекомендуется)
        │   ├── index.json      ← манифест сниппетов
        │   └── *.php / *.yml / *.sh / *.md
        └── adapters/           ← только если есть реальные отличия
            ├── claude.md       ← дельта для Claude Code
            ├── cursor.md       ← дельта для Cursor
            └── fable.md        ← дельта для Fable-агента
```

### Принцип единственного источника истины

```
SKILL.md  ←── единственный source of truth
    │
    ├── adapters/claude.md   (ТОЛЬКО delta: overrides, дополнительные инструкции)
    ├── adapters/cursor.md   (ТОЛЬКО delta: .cursorrules specific)
    └── adapters/fable.md    (ТОЛЬКО delta: automation hooks, output paths)
```

**Адаптер НЕ дублирует SKILL.md.** Он содержит только строки вида:
```markdown
## Override: output_format
Вместо markdown используй JSON с полями: ...

## Additional: pre_flight
Перед выполнением проверь наличие файла composer.json
```

---

## 3. Структура репозитория `academici/skills`

```
academici/skills/
│
├── README.md
├── skills.json                    ← реестр (аналог skills-lock.json, но источник)
├── SKILL_TEMPLATE.md              ← шаблон для новых скиллов
├── install.sh                     ← CLI установщик
├── sync.sh                        ← синхронизация в brain/другие репо
│
├── skills/
│   │
│   ├── founder/
│   │   ├── idea-discovery/
│   │   │   ├── SKILL.md
│   │   │   └── snippets/
│   │   │       └── lean-canvas.md
│   │   ├── competitive-analysis/
│   │   │   ├── SKILL.md
│   │   │   └── snippets/
│   │   │       └── competitor-matrix.md
│   │   ├── new-project/
│   │   │   ├── SKILL.md
│   │   │   └── snippets/
│   │   │       └── project-folder-structure.md
│   │   ├── risk-assessment/
│   │   │   └── SKILL.md
│   │   └── pitch-deck/
│   │       ├── SKILL.md
│   │       └── snippets/
│   │           └── yc-deck-template.md
│   │
│   ├── pm/
│   │   ├── brd/
│   │   │   ├── SKILL.md
│   │   │   └── snippets/
│   │   │       └── brd-template.md
│   │   ├── prd-from-brd/
│   │   ├── business-process/
│   │   │   └── snippets/
│   │   │       └── fsm-mermaid.md
│   │   ├── product-roadmap/
│   │   │   └── snippets/
│   │   │       └── rice-scoring.md
│   │   ├── go-to-market/
│   │   ├── monetization-design/
│   │   │   └── snippets/
│   │   │       └── business-model-tradeoff.md
│   │   ├── requirement-critic/
│   │   └── unit-economics/
│   │       └── snippets/
│   │           └── ltv-cac-spreadsheet.md
│   │
│   ├── architect/
│   │   ├── architecture/
│   │   │   ├── SKILL.md
│   │   │   └── snippets/
│   │   │       ├── c4-context.md
│   │   │       ├── c4-container.md
│   │   │       └── adr-template.md
│   │   ├── api-design/
│   │   │   └── snippets/
│   │   │       ├── rest-conventions.md
│   │   │       └── openapi-stub.yml
│   │   ├── data-schema/
│   │   │   └── snippets/
│   │   │       └── entity-table.md
│   │   ├── agent-design/
│   │   │   └── snippets/
│   │   │       ├── agentic-loop.md
│   │   │       └── tool-contract.md
│   │   ├── eval-design/
│   │   ├── security-design/
│   │   │   └── snippets/
│   │   │       └── stride-threat-model.md
│   │   ├── observability-design/
│   │   │   └── snippets/
│   │   │       └── slo-sli-template.md
│   │   ├── legal-compliance/
│   │   └── tech-stack-selection/
│   │       └── snippets/
│   │           └── tradeoff-matrix.md
│   │
│   ├── oss-dev/
│   │   ├── oss-development/
│   │   │   ├── SKILL.md
│   │   │   └── snippets/
│   │   │       ├── readme-template.md
│   │   │       └── architecture-template.md
│   │   ├── oss-governance/
│   │   │   └── snippets/
│   │   │       ├── contributing-template.md
│   │   │       └── security-policy.md
│   │   ├── release-engineering/
│   │   │   └── snippets/
│   │   │       ├── changelog-template.md
│   │   │       └── semver-decision-tree.md
│   │   ├── dependency-audit/
│   │   ├── dx-design/
│   │   │   └── snippets/
│   │   │       └── quickstart-60sec.md
│   │   └── references/
│   │       ├── oss-php.md
│   │       ├── oss-js.md
│   │       ├── oss-dart.md
│   │       └── oss-py.md
│   │
│   ├── quality/
│   │   ├── code-review/
│   │   │   ├── SKILL.md
│   │   │   └── snippets/
│   │   │       ├── pr-comment-template.md
│   │   │       └── severity-guide.md
│   │   ├── test-strategy/
│   │   │   └── snippets/
│   │   │       └── test-pyramid.md
│   │   ├── tech-debt-audit/
│   │   │   └── snippets/
│   │   │       └── debt-register.md
│   │   └── refactoring-plan/
│   │       └── snippets/
│   │           └── mikado-template.md
│   │
│   ├── operator/
│   │   ├── incident-response/
│   │   │   ├── SKILL.md
│   │   │   └── snippets/
│   │   │       └── incident-timeline.md
│   │   ├── postmortem/
│   │   │   └── snippets/
│   │   │       └── 5-whys-template.md
│   │   ├── runbook/
│   │   │   └── snippets/
│   │   │       └── runbook-template.md
│   │   ├── oncall-rotation/
│   │   └── capacity-planning/
│   │       └── snippets/
│   │           └── load-forecast.md
│   │
│   ├── devops/                    ← НОВЫЙ BUCKET
│   │   ├── docker/
│   │   │   ├── php/
│   │   │   │   ├── SKILL.md
│   │   │   │   └── snippets/
│   │   │   │       ├── Dockerfile.php-fpm
│   │   │   │       ├── Dockerfile.php-cli
│   │   │   │       ├── php.ini.production
│   │   │   │       └── opcache.ini
│   │   │   ├── vite/
│   │   │   │   ├── SKILL.md
│   │   │   │   └── snippets/
│   │   │   │       ├── Dockerfile.node
│   │   │   │       └── vite.config.docker.ts
│   │   │   ├── postgres/
│   │   │   │   ├── SKILL.md
│   │   │   │   └── snippets/
│   │   │   │       ├── postgres.conf
│   │   │   │       └── init.sql
│   │   │   └── dev-prod/
│   │   │       ├── SKILL.md
│   │   │       └── snippets/
│   │   │           ├── docker-compose.yml
│   │   │           ├── docker-compose.override.yml
│   │   │           ├── docker-compose.prod.yml
│   │   │           ├── .env.example
│   │   │           └── Makefile
│   │   │
│   │   ├── ci-cd/
│   │   │   ├── SKILL.md
│   │   │   └── snippets/
│   │   │       ├── github-actions-laravel.yml
│   │   │       ├── github-actions-release.yml
│   │   │       └── github-actions-docker.yml
│   │   │
│   │   └── gitops/
│   │       ├── SKILL.md
│   │       └── snippets/
│   │           ├── branch-strategy.md
│   │           └── commit-conventions.md
│   │
│   ├── php/                       ← НОВЫЙ BUCKET
│   │   ├── laravel/
│   │   │   ├── SKILL.md
│   │   │   └── snippets/
│   │   │       ├── service-provider.php
│   │   │       ├── repository-pattern.php
│   │   │       ├── action-class.php
│   │   │       ├── form-request.php
│   │   │       ├── api-resource.php
│   │   │       ├── event-listener.php
│   │   │       └── custom-middleware.php
│   │   │
│   │   ├── laravel-permissions/
│   │   │   ├── SKILL.md
│   │   │   └── snippets/
│   │   │       ├── rbac-setup.php
│   │   │       ├── policy-class.php
│   │   │       └── gate-definition.php
│   │   │
│   │   ├── laravel-testing/
│   │   │   ├── SKILL.md
│   │   │   └── snippets/
│   │   │       ├── feature-test.php
│   │   │       ├── unit-test.php
│   │   │       ├── factory-pattern.php
│   │   │       └── pest-test.php
│   │   │
│   │   ├── laravel-packages/
│   │   │   ├── SKILL.md
│   │   │   └── snippets/
│   │   │       ├── composer.json.stub
│   │   │       ├── ServiceProvider.stub.php
│   │   │       ├── config.stub.php
│   │   │       ├── boost-skill-publisher.php
│   │   │       └── TestCase.stub.php
│   │   │
│   │   └── php-patterns/
│   │       ├── SKILL.md
│   │       └── snippets/
│   │           ├── value-object.php
│   │           ├── dto.php
│   │           ├── pipeline.php
│   │           └── specification.php
│   │
│   └── roles/                     ← НОВЫЙ BUCKET
│       ├── startup-cto/
│       │   ├── SKILL.md
│       │   └── snippets/
│       │       ├── tech-radar.md
│       │       └── hiring-rubric.md
│       │
│       ├── tech-lead/
│       │   ├── SKILL.md
│       │   └── snippets/
│       │       ├── sprint-kickoff.md
│       │       └── 1on1-template.md
│       │
│       ├── open-source-maintainer/
│       │   ├── SKILL.md
│       │   └── snippets/
│       │       ├── issue-triage.md
│       │       ├── pr-review-checklist.md
│       │       └── release-announcement.md
│       │
│       └── solo-founder/
│           ├── SKILL.md
│           └── snippets/
│               ├── weekly-review.md
│               └── decision-log.md
│
├── generate-skill/                ← META-SKILL
│   ├── SKILL.md
│   └── snippets/
│       └── SKILL_TEMPLATE.md
│
└── .github/
    ├── workflows/
    │   ├── validate.yml
    │   ├── sync-to-brain.yml
    │   └── sha256-update.yml
    └── CODEOWNERS
```

---

## 4. Формат SKILL.md (канонический)

```markdown
---
name: docker-php
bucket: devops
version: 0.2.0
description: "Production-ready PHP-FPM Docker образ с opcache, healthcheck и non-root user"
risk: write
persona: operator
tags: [docker, php, devops]
requires: []
produces_for: [docker-dev-prod]
outputs:
  - "infra/docker/php/Dockerfile"
  - "infra/docker/php/php.ini"
snippets:
  - Dockerfile.php-fpm
  - php.ini.production
  - opcache.ini
adapters: [claude, cursor, fable]
sha256: ""                         # заполняется автоматически sync.sh
---

## Контекст

Когда использовать этот скилл и почему он нужен.

## Входные данные

Что агент должен знать перед выполнением (версия PHP, нужен ли xdebug и т.д.)

## Алгоритм

Пошаговые инструкции для агента.

## Выходные данные

Конкретные файлы которые будут созданы.

## Чеклист качества

- [ ] non-root user в Dockerfile
- [ ] opcache включён в production
- [ ] healthcheck настроен
- [ ] .dockerignore актуален

## Ссылки

- snippets/Dockerfile.php-fpm
- snippets/opcache.ini
```

---

## 5. Структура `snippets/index.json`

```json
{
  "skill": "docker-php",
  "snippets": [
    {
      "file": "Dockerfile.php-fpm",
      "description": "Production PHP-FPM образ с opcache и non-root user",
      "tags": ["dockerfile", "php", "production"],
      "php_versions": ["8.2", "8.3", "8.4"]
    },
    {
      "file": "php.ini.production",
      "description": "Оптимизированный php.ini для production",
      "tags": ["config", "performance"]
    },
    {
      "file": "opcache.ini",
      "description": "Конфигурация OPcache для production",
      "tags": ["config", "performance", "opcache"]
    }
  ]
}
```

---

## 6. `skills.json` — реестр репозитория

```json
{
  "version": 3,
  "name": "academici-skills",
  "repository": "https://github.com/academici/skills",
  "schema": "https://github.com/academici/skills/blob/main/SKILL_TEMPLATE.md",
  "buckets": {
    "founder": { "count": 5, "status": "migrating" },
    "pm": { "count": 8, "status": "migrating" },
    "architect": { "count": 9, "status": "migrating" },
    "oss-dev": { "count": 5, "status": "migrating" },
    "quality": { "count": 4, "status": "migrating" },
    "operator": { "count": 5, "status": "migrating" },
    "devops": { "count": 6, "status": "new" },
    "php": { "count": 5, "status": "new" },
    "roles": { "count": 4, "status": "new" }
  },
  "skills": []
}
```

---

## 7. Алгоритм агента Fable (SCAN → ANALYZE → EXTRACT → COMMIT)

```
SCAN:
  - Рекурсивно обходить scan_paths из .skills-scanner.json
  - Фильтровать по расширениям: .php, .yml, .sh, .env.example
  - Исключать: vendor/, node_modules/, .git/, storage/

ANALYZE:
  - quality_score по метрикам:
    - docblocks присутствуют (20 pts)
    - type hints полные (20 pts)
    - функции ≤ 20 строк (20 pts)
    - нет magic numbers (20 pts)
    - PSR-12 соответствие (20 pts)
  - Порог для включения: score ≥ 60

EXTRACT:
  - Анонимизировать: убрать namespace конкретных проектов
  - Добавить source comment: // Source: {project}/{file} (anonymized)
  - Определить bucket и skill по пути файла

COMMIT:
  - Создать ветку: feat/scanner-{date}
  - PR с описанием: найденные паттерны, количество сниппетов, source проекты
```

### `.skills-scanner.json`

```json
{
  "version": "1.0",
  "scan_paths": [
    "~/projects/azguard",
    "~/projects/botkit-dev",
    "~/projects/filament-*"
  ],
  "output": {
    "repo": "academici/skills",
    "branch_prefix": "feat/scanner",
    "auto_pr": true
  },
  "quality_threshold": 60,
  "languages": ["php", "yaml", "shell"],
  "exclude_patterns": ["vendor/", "node_modules/", "*.test.php"]
}
```

---

## 8. GitHub Actions

### `validate.yml`
Проверяет каждый `SKILL.md` на наличие обязательных frontmatter полей: `name`, `bucket`, `version`, `description`.

### `sync-to-brain.yml`
Ежедневно в 06:00 UTC: копирует обновлённые скиллы в `academici/brain/skills/`, обновляет `skills-lock.json`.

### `sha256-update.yml`
При push в `main`: пересчитывает `sha256` для каждого `SKILL.md`, коммитит обновлённый `skills.json`.

---

## 9. Sprint-план

### Sprint 1 — Foundation (Неделя 1–2)
- [ ] Создать репозиторий `academici/skills`
- [ ] `SKILL_TEMPLATE.md`, `skills.json`, `install.sh`, `sync.sh`
- [ ] GitHub Actions: `validate.yml` + `sync-to-brain.yml`
- [ ] Импорт 12 скиллов из `get-zeked/perplexity-super-skills`
- [ ] Миграция 36 существующих скиллов из `brain` в папки-плагины

### Sprint 2 — PHP/Laravel (Неделя 3–4)
- [ ] `php/laravel/` — 7 сниппетов
- [ ] `php/laravel-permissions/` — RBAC + AzGuard паттерны
- [ ] `php/laravel-packages/` — boost-skill-publisher
- [ ] `devops/docker/php/` — production Dockerfile
- [ ] `devops/ci-cd/` — GitHub Actions для Laravel

### Sprint 3 — Scanner Agent (Неделя 5–6)
- [ ] `.skills-scanner.json` конфиг
- [ ] Скрипт сканера (PHP или shell)
- [ ] Автоматический PR pipeline
- [ ] Тест на `azguard` и `botkit-dev`

### Sprint 4 — Polish & Expand (Неделя 7–8)
- [ ] `roles/` bucket — 4 персоны
- [ ] `generate-skill/` meta-skill
- [ ] Obsidian интеграция (адаптер для vault)
- [ ] Документация и CONTRIBUTING.md

---

*Версия 3 (финал) · 10 июня 2026 · Для агента Fable*
