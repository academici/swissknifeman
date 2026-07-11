---
name: release-engineering
bucket: oss-dev
version: 0.1.0
description: SemVer-стратегия, CHANGELOG, релизный pipeline (CI/CD), pre-releases, deprecation policy для OSS-пакета
risk: draft
persona: oss-dev
tags: [oss, semver, release, changelog, ci]
requires: [oss-development]
produces_for: [github-flow]
outputs: ["ProjectName/RELEASING.md", "ProjectName/CHANGELOG.md"]
sha256: ""
adapters: [claude, cursor, fable]
---

# Skill: Release Engineering

Применять когда: OSS-проект нужно довести до **первого публичного релиза** (`v0.1.0` / `v1.0.0`) или **формализовать релизный процесс** для уже существующего пакета. Решает вопросы: версионирование, changelog, теги, pre-releases, deprecation, hotfix-flow.

Должен быть **выполнен после `oss-development`** (нужна базовая структура репо и `Architecture.md`). Часто идёт в паре с `dependency-audit` (определить SBOM перед публикацией) и `dx-design` (определить, что break/feature/fix значит для пользователя).

---

## Когда НЕ применять

- Проект внутренний / приватный без публичных потребителей — версионирование можно делать по дате, не SemVer. Использовать упрощённый процесс.
- Уже есть устойчивый release-flow и его не нужно менять — отказать, не плодить процесс.
- Первый `v0.1.0` ещё не вышел и нет даже README — сначала `oss-development` и `dx-design`.

---

## 5 решений на этом этапе

### 1. SemVer-контракт
Зафиксировать **что для этого пакета считается** `MAJOR`/`MINOR`/`PATCH`:

| Тип изменения | Класс | Пример |
|:---|:---|:---|
| Удаление публичного API / breaking signature | MAJOR | удалён `Brain.query()`, переименован параметр |
| Изменение поведения существующего API (но контракт сохранён) | MINOR или MAJOR? | **Зависит от пакета. Зафиксировать** |
| Новый публичный API, не ломающий существующее | MINOR | добавлен `Brain.stream()` |
| Bug-fix без изменения публичного API | PATCH | исправлен race в `Brain.query()` |
| Изменение приватного кода / refactor | PATCH или skip | внутренние правки |
| Добавление experimental API под флагом | MINOR | `experimental.stream()` |
| Зависимости: обновление minor/patch | PATCH | bumped lodash |
| Зависимости: обновление major транзитивной зависимости | MINOR или MAJOR | **если в peerDeps → MAJOR** |

Что **отдельно зафиксировать в RELEASING.md**:
- Что считается публичным API (всё ли экспортируемое? только то, что в `index.ts`?)
- Считается ли изменение `engines.node` MAJOR (рекомендую — да)
- Считается ли изменение TS-типов MAJOR (если используют как библиотеку — да; если internal — нет)
- Платформенные требования (минимальный PHP/Node/Dart) — MAJOR при изменении

### 2. Pre-release стратегия
Перед `1.0.0` — `0.x.y`. После `1.0.0`:
- `1.2.0-alpha.1` — внутренние эксперименты, **нет** обещаний стабильности
- `1.2.0-beta.1` — публичные тесты, API заморожен, ловим баги
- `1.2.0-rc.1` — кандидат, только blocker-фиксы
- `1.2.0` — стабильный

**Правило тэгов npm/Packagist/pub.dev**: alpha/beta/rc публикуются под dist-tag `next` или `beta`, **не на `latest`**.

### 3. CHANGELOG.md формат
**Keep a Changelog** (https://keepachangelog.com) — стандарт:

```markdown
## [Unreleased]
### Added
- ...
### Changed
- ...
### Deprecated
- ...
### Removed
- ...
### Fixed
- ...
### Security
- ...

## [1.2.0] - 2026-01-15
### Added
- `Brain.stream()` — стриминг ответов агента ([#42](link))
### Fixed
- Race в `Brain.query()` при concurrent calls ([#51](link))

## [1.1.0] - 2025-12-10

Пример заполненного CHANGELOG (Keep a Changelog) с разбором секций — [references/changelog-example.md](references/changelog-example.md).

## Что агент добавляет сам

- **Минимальная Node/PHP/Dart версия.** Указать в `engines.node` / `composer.json:require.php` / `pubspec.yaml:environment.sdk`. Никаких «работает на любой версии».
- **`provenance` / `signed releases.`** Для `v1.0+` без вариантов. Объяснить как настроить OIDC.
- **`peerDependencies` ловушки.** Если пакет — плагин (для фреймворка), `peerDeps` определяет MAJOR-сцепку.
- **Hotfix-flow.** Описать что делать при критическом баге в `1.2.3` если main уже на `1.3-alpha`: ветка `release/1.2.x`, fix, `1.2.4`, backport в main.
- **LTS-стратегия (если применимо).** Для библиотек уровня BrainKit — нет. Для core-инфраструктуры — да, 1 LTS параллельно с current.

---

## Повседневная дисциплина CHANGELOG

Этот скилл активируется на релизных задачах — но CHANGELOG портится не в релиз, а между
ними: пропущенная строка в `[Unreleased]` копится молча, и систематизировать батч задним
числом уже почти невозможно. Поэтому дисциплина — не «раз в релиз», а **каждый содержательный
коммит**. Два контура, по типу репозитория:

**Пакеты (SemVer-строгие).** Тип берём из conventional commit: `fix:` → PATCH, `feat:` →
MINOR. **MAJOR — ВСЕГДА ручное решение владельца**, breaking-change автоматикой НЕ
выводится — только человек решает, что достаточно ломает контракт для мажора. Каждый
содержательный коммит оставляет строку в `[Unreleased]` нужной группы Keep a Changelog
(Added/Changed/Deprecated/Removed/Fixed/Security).

**Проекты (без SemVer).** Компактная запись + ссылка на коммит в GitHub-стиле:
`- краткое описание ([abc1234](…/commit/abc1234))`. Систематизация в цельное описание —
батчем, при релизе, а не построчно.

Формат записей в обоих контурах — Keep a Changelog (см. выше), язык — русский
(`writing-style`).

**Enforcement.** Дисциплина держится не на памяти сессии: commit-гейт `harness`
(`--changelog-gate`, хук `changelog-gate` на `git commit`) предупреждает в контекст модели,
если дифф содержательный, а CHANGELOG не тронут — **warning, не блок**. Осознанное
исключение (docs/chore-коммит) гейт пропускает по типу коммита автоматически; для остального
— явный skip-маркер `[changelog-skip]` в сообщении коммита. Механизация сборки версии из
`[Unreleased]` + conventional commits — `skiller release` (опционально, umbrella-тег
`vX.Y.Z`).

---

## Структура output-файла

### `ProjectName/RELEASING.md`

```markdown
---
project: [ProjectName]
type: oss-process
based_on: oss-development.md
---

# Releasing [ProjectName]

## SemVer-контракт
[таблица «что является MAJOR/MINOR/PATCH» для этого пакета]

## Публичный API
- Что считается публичным: [...]
- Что приватно: [...]
- Платформенные требования (min runtime): [...]

## Pre-release
- alpha / beta / rc → dist-tag
- Когда публиковать на `latest`

## CHANGELOG
- Стандарт: Keep a Changelog
- Автоматизация: [changesets / release-please / manual]

## Release pipeline
- Триггер: push tag `v*`
- Шаги: test → build → publish → sign → changelog
- Secrets: [...]
- 2FA: [...]

## Deprecation policy
- Mark → Wait (≥ 1 MAJOR) → Remove

## Hotfix flow
- ветка `release/X.Y.x` → fix → tag `X.Y.Z+1` → backport в main

## Чек-лист для нового релиза
- [ ] Все тесты зелёные на всех платформах
- [ ] CHANGELOG [Unreleased] → новая версия
- [ ] Версия в `package.json`/`composer.json`/`pubspec.yaml` поднята
- [ ] Тэг `vX.Y.Z` создан
- [ ] GitHub Release с release notes опубликован
- [ ] Артефакт опубликован на registry с provenance
- [ ] Twitter / Discord / mailing list уведомлены (для MAJOR)
```

### `ProjectName/CHANGELOG.md`

См. формат Keep a Changelog выше. Создаётся пустым с секцией `[Unreleased]` если её нет.

---

## Ссылки

- `oss-dev/oss-development` — предпосылка: базовая структура репо и `Architecture.md`.
- `oss-dev/github-flow` — потребитель: процессная цепочка Issue→PR→Tag→Release исполняет этот SemVer-контракт и CHANGELOG-формат.
- `oss-dev/dependency-audit` — SBOM как release artefact; vuln-фиксы влияют на версию.
- `oss-dev/dx-design` — что break/feature/fix значит для пользователя; TS-типы как публичный API.
- `general/git-commit-rules` — формат коммитов, по которым SemVer-оракул определяет bump.
- `devops/ci-cd` — GitHub Actions release-pipeline (тег → test → build → publish).
- `php-packages/laravel-package-release` — release-нотки/теги/валидация для PHP-пакетов (язык-специфика).

---

## Жёсткие запреты

НЕЛЬЗЯ:
- Публиковать `1.0.0` без RELEASING.md и CHANGELOG.md
- Делать MAJOR без миграционного гайда в release notes
- Удалять публичный API в MINOR (даже «никто не использует» — нет)
- Force-push в тэг (релизные тэги immutable)
- Публиковать без 2FA / provenance для `v1.0+`
- Использовать «git log dump» вместо changelog
- Закрывать содержательный коммит (feat/fix/perf/refactor) без строки в `[Unreleased]` —
  кроме docs/chore/test или явного skip-маркера
