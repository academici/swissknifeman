---
name: oss-governance
bucket: oss-dev
version: 0.1.0
description: LICENSE, CoC, CONTRIBUTING, MAINTAINERS, RFC-процесс, security policy для OSS-проекта
risk: draft
persona: oss-dev
tags: [oss, compliance]
requires: [oss-development]
produces_for: []
outputs: ["ProjectName/LICENSE", "ProjectName/CODE_OF_CONDUCT.md", "ProjectName/CONTRIBUTING.md", "ProjectName/MAINTAINERS.md", "ProjectName/SECURITY.md"]
sha256: ""
adapters: [claude, cursor, fable]
---

# Skill: OSS Governance

Применять когда: OSS-проект публикуется впервые **или** начинает принимать внешние контрибьюции. Governance — это про **прозрачность правил и границ ответственности**: кто решает, как контрибьютить, как сообщать уязвимости, что разрешено сообществу.

Должен быть **выполнен после `oss-development`** (есть базовая структура). Парится с `dependency-audit` (compliance) и `dx-design` (issue/PR templates — стык DX и governance).

---

## Когда НЕ применять

- Личный pet-project, не принимающий PR — достаточно LICENSE + минимального README. Не плодить процесс.
- Внутренний пакет компании — governance заменяется внутренним процессом code review.
- Уже есть зрелые governance-файлы — отказать, не переписывать.

---

## 6 артефактов governance (по приоритету)

### 1. LICENSE (обязательно перед публикацией)

| Лицензия | Когда выбирать | Плюсы | Минусы |
|:---|:---|:---|:---|
| **MIT** | Дефолт для библиотек | Максимальная adopt-rate, простая | Нет copyleft, не защищает от форков-в-проприетарь |
| **Apache-2.0** | Если важна patent-grant | Явный patent grant, защита от submarine patents | Чуть сложнее, требует NOTICE |
| **BSD-3-Clause** | Аналог MIT с no-endorsement clause | Простая, BSD-семья | Аналогично MIT по adopt |
| **MPL-2.0** | Если хочется file-level copyleft | Можно линковать в проприетарь, но изменения в файлах MPL остаются открытыми | Меньше известна |
| **AGPL-3.0** | SaaS-сервис, который ты сам хостишь | Защищает от competitive hosting | Многие компании запрещают AGPL в продукте — резко снижает adopt |
| **GPL-3.0** | Полностью copyleft library | Сильная защита открытости | Заразность — конец adoption в commercial |
| **BUSL-1.1 / SSPL** | source-available, не OSS | Защита бизнес-модели | **Это не OSS** — нельзя называть OSI-compliant |

**Дефолт для vault-проектов:** MIT. **Исключения:**
- Если есть патенты или сильный риск patent troll → Apache-2.0
- Если SaaS-конкуренция (типа Elastic) → подумать про AGPL или BUSL, но это уже не OSS

**Внутри файла LICENSE — текст лицензии полностью**, не ссылка. SPDX-идентификатор в `package.json`/`composer.json` обязателен.

### 2. CODE_OF_CONDUCT.md
Стандарт — **Contributor Covenant v2.1** (https://www.contributor-covenant.org). Не сочинять свой.

Что добавить от себя:
- Email для сообщений о нарушениях (отдельный, не личный)
- Reporting flow (анонимность, конфиденциальность)
- Enforcement ladder (warning → temp ban → permanent ban)

### 3. CONTRIBUTING.md
**Структура:**

```markdown
# Contributing to [ProjectName]

## Quick start (dev)
[install + run tests за 3 команды]

## Code style
- Linter: ...
- Format: ...
- Pre-commit: ...

## Commits
- Conventional Commits (feat:, fix:, ...)
- Reference issue: `fix: handle X (#42)`

## Branch / PR flow
- Fork → branch → PR → review → squash merge

## Tests
- Unit, integration, e2e
- Coverage threshold: X%
- Что обязательно покрывать

## Documentation
- Любое изменение публичного API → обновить docs/ + CHANGELOG
- Скриншоты для UI-изменений

## Что МЫ ПРИНИМАЕМ
- bug fixes
- documentation
- new features ПОСЛЕ согласования в issue / RFC

## Что МЫ НЕ ПРИНИМАЕМ
- Refactor без обоснования
- Breaking changes без RFC
- Code style PR (это автоматизируем)
```

**Цель:** контрибьютор должен понять «как помочь» за 2 минуты чтения.

### 4. MAINTAINERS.md
Кто принимает решения и где их найти:

```markdown
# Maintainers

## Core
- @username (GitHub) — TZ, responsibilities, contact preference

## Active reviewers
- @username — areas: docs, ci

## Decision process
- Bug fixes / docs: 1 maintainer approval
- New features: 2 approvals + RFC если major
- Breaking changes: lazy consensus 7 days
- Security: maintainer + 1 reviewer, expedited

## Becoming a maintainer
[критерии: X merged PRs, Y месяцев активности, etc.]
```

### 5. SECURITY.md
**GitHub-стандарт.** Структура:

```markdown
# Security Policy

## Supported versions
| Version | Supported |
|:---|:---|
| 2.x | ✅ |
| 1.x | ✅ (security fixes only, до YYYY-MM) |
| < 1.0 | ❌ |

## Reporting a vulnerability
- **Не открывать публичный issue.**
- Email: security@[domain] (или privately disclosed GitHub Security Advisory)
- PGP key: [ссылка]
- Ожидаемый response: 48 часов
- Disclosure timeline: 90 дней по умолчанию (negotiable)

## Scope
- В scope: [...]
- Не в scope: [...]
```

### 6. RFC-процесс (для проектов с активным community)
Когда применять: feature affects > 1 публичный API surface, или меняет dx-контракт, или break-change.

```
docs/rfcs/
├── 0000-template.md
├── 0001-streaming-api.md
└── 0002-deprecation-of-foo.md
```

**Шаблон RFC**: Summary → Motivation → Detailed design → Drawbacks → Alternatives → Open questions → Migration path.

**Процесс:**
1. PR с RFC в `docs/rfcs/` (статус `draft`)
2. Discussion ≥ 14 дней
3. Lazy consensus или vote от maintainers
4. Принят → статус `accepted` + issue для implementation
5. Реализован → статус `implemented` + ссылка на release

Для small-team проектов — упрощается до «RFC = GitHub Discussion с шаблоном».

---

## Что агент добавляет сам

- **DCO vs CLA.** Для большинства OSS-проектов **достаточно DCO** (Developer Certificate of Origin — `git commit -s`). CLA — только если планируется потенциальная коммерциализация / re-licensing.
- **Bus factor.** В `MAINTAINERS.md` — указать что делать, если активный мейнтейнер пропадёт (наследование репо, fallback контакт).
- **Funding.** `.github/FUNDING.yml` — если применимо (GitHub Sponsors, OpenCollective). Не для всех проектов.
- **Issue / PR templates.** `.github/ISSUE_TEMPLATE/*.yml`, `.github/PULL_REQUEST_TEMPLATE.md`. Частично пересекается с `dx-design`.
- **Branch protection.** Не забыть включить (admin task): требовать review, требовать CI, запретить force-push в main и release/.

---

## Структура output-файлов

### `ProjectName/LICENSE`
Полный текст выбранной лицензии (берётся из https://choosealicense.com). Не редактировать сам текст.

### `ProjectName/CODE_OF_CONDUCT.md`
Contributor Covenant 2.1 с подставленным email для reports.

### `ProjectName/CONTRIBUTING.md`
По структуре выше.

### `ProjectName/MAINTAINERS.md`
По структуре выше с указанием реальных людей.

### `ProjectName/SECURITY.md`
По структуре выше.

### (опционально) `ProjectName/docs/rfcs/0000-template.md`
Шаблон RFC если включён процесс.

---

## Жёсткие запреты

НЕЛЬЗЯ:
- Публиковать без LICENSE (юридически репо без лицензии = "all rights reserved", никто не может использовать)
- Сочинять свой CoC — Contributor Covenant покрывает 99% случаев
- Smешивать LICENSE.md с README (это отдельные файлы по конвенции)
- Использовать AGPL/BUSL без явного бизнес-обоснования (резкая потеря adopt)
- Не указывать SPDX в `package.json`/`composer.json` (бьёт по dependency-audit потребителей)
- Принимать PR без CONTRIBUTING.md (нет правил → каждый PR review — переговоры с нуля)
- Игнорировать SECURITY.md (без него уязвимости приходят в публичные issues)
