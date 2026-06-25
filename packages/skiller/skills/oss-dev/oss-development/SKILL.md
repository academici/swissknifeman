---
name: oss-development
bucket: oss-dev
version: 0.1.0
description: OSS-проект: repo structure, README, Architecture, ADR, SemVer, CI/CD. PHP-специфика в ../references/oss-php.md
risk: write
persona: oss-dev
tags: [oss, architecture, documentation, ci]
requires: []
produces_for: [release-engineering, dx-design, oss-governance, dependency-audit]
outputs: ["ProjectName/ProjectName.md", "ProjectName/Architecture.md", "ProjectName/Roadmap.md", "ProjectName/ADR/"]
sha256: ""
adapters: [claude, cursor, fable]
---

# Skill: OSS Development

Применять когда: задача на OpenSource проект (BrainKit, AzGuard, ThemeOn и другие OSS).
Это инженерный трек — упор на архитектуру, код, документацию для разработчиков.

---

## Отличие от стартап-трека

| | Стартап-трек | OSS-трек |
|:---|:---|:---|
| Аудитория | Инвесторы, пользователи, команда | Разработчики, контрибьюторы |
| Документация | BRD, GTM, Unit Economics | README, API docs, Contributing guide |
| Фокус | Бизнес-ценность | Техническая корректность |
| Метрики | MAU, Revenue, Churn | GitHub stars, forks, npm downloads, contributors |

---

## Шаг 1. Repo Structure

Детальная структура OSS-репозитория (директории, обязательные файлы) — [references/repo-structure.md](references/repo-structure.md).

## Шаг 2. README структура

README — лицо проекта. Структура:

```markdown
# ProjectName

[Одна строка: что делает + для кого]

[![npm version](badge)] [![license](badge)] [![CI](badge)]

## Почему [ProjectName]?
[3-5 конкретных преимущества перед альтернативами]

## Быстрый старт
[Минимум 3 строки кода для получения результата]

## Установка
[Команда установки]

## Использование
[Основные примеры]

## API / Документация
[Ссылка на полную документацию или inline]

## Требования
[Версии зависимостей]

## Контрибьюция
[Ссылка на CONTRIBUTING.md]

## Лицензия
[Тип лицензии]
```

---

## Шаг 3. Архитектура

Использовать C4 model (текстовый вариант):

**Level 1 — Context:** Кто использует, какие внешние системы
**Level 2 — Container:** Основные компоненты и их взаимодействие
**Level 3 — Component:** Детали ключевых компонентов
**ADR:** Каждое нетривиальное решение → отдельный ADR файл

Mermaid-диаграммы для визуализации — обязательны в Architecture.md.

---

## Шаг 4. Versioning Strategy

**SemVer:** `MAJOR.MINOR.PATCH`
- MAJOR: breaking changes
- MINOR: новые фичи, обратная совместимость
- PATCH: bug fixes

**Правила:**
- `0.x.x` — экспериментальная стадия, любые breaking changes допустимы
- `1.0.0` — стабильный публичный API, breaking changes только в MAJOR
- Всегда обновлять CHANGELOG.md перед релизом

---

## Шаг 5. Contributing Guide

CONTRIBUTING.md должен содержать:

```markdown
## Как запустить локально
[Команды для setup]

## Структура проекта
[Кратко что где лежит]

## Как запустить тесты
[Команда]

## Как создать PR
1. Fork репозитория
2. Создать ветку: `git checkout -b feature/название`
3. Коммиты: [conventional commits формат]
4. Тесты: все должны проходить
5. PR: заполнить шаблон

## Code style
[Линтер, форматтер, pre-commit hooks]
```

---

## Шаг 6. CI/CD минимум

```yaml
# .github/workflows/ci.yml
- Lint
- Type check (если TypeScript/Go/Rust)
- Tests
- Build
- (опционально) Publish на npm/crates.io при теге
```

---

## Форматы файлов в vault (OSS проект)

```
05 - Projects/03 - OpenSource/ProjectName/
├── ProjectName.md          # Индекс: статус, ссылка на GitHub, ключевые решения
├── Architecture.md         # C4 + Mermaid
├── ADR/
│   └── ADR-001_*.md
├── Roadmap.md              # Фазы, planned features
└── _index.md
```

---

## Метрики здоровья OSS-проекта

| Метрика | Цель |
|:---|:---|
| Test coverage | ≥ 80% |
| CI pass rate | ≥ 95% |
| Issue response time | < 48 часов |
| PR review time | < 1 недели |
| Документация актуальна | Обновляется с каждым MINOR |

---

## Что агент добавляет сам

- License рекомендация (MIT для максимального adoption, Apache 2.0 если нужна patent protection)
- Security policy (`SECURITY.md`) если проект имеет отношение к безопасности
- Badges для README (npm version, CI status, coverage, license)
- Предупреждение о semver если API меняется без версионирования

---

## PHP-специфика

См. [[../references/oss-php]] (файл `../references/oss-php.md` относительно этого скилла) — composer.json, PSR-стандарты, PHPStan, PHPUnit, Packagist, CI matrix.

---

## Ссылки

Этот скилл — корень OSS-трека; от него отходят:

- `oss-dev/release-engineering` — SemVer-контракт, CHANGELOG, релизный pipeline.
- `oss-dev/dx-design` — README/quick-start, API-эргономика, error-messages.
- `oss-dev/oss-governance` — LICENSE, CoC, CONTRIBUTING, SECURITY, RFC.
- `oss-dev/dependency-audit` — vuln/license/supply-chain аудит зависимостей.
- `oss-dev/github-flow` — процессная цепочка Issue→PR→Tag→Release на GitHub.

Смежное (вход/детализация):

- `architect/tech-stack-selection` — выбор стека ДО структуры репо (ADR-первый шаг).
- `architect/architecture` — C4/ADR-детализация (здесь — только базовый уровень).
- `devops/ci-cd` — GitHub Actions pipelines (здесь — только минимум CI).
- `php/laravel-packages` — scaffold/публикация Laravel-пакетов (язык-специфика).

---

## Жёсткие запреты

НЕЛЬЗЯ:
- Бизнес-документы (BRD, GTM, Unit Economics) в OSS-треке
- Коммиты напрямую в main (только PR)
- Merge без зелёного CI
- Breaking changes без MAJOR версии (если ≥ 1.0.0)
- PHP-пакет без PSR-4 autoloading
- Публиковать на Packagist без тестов (coverage < 80%)
