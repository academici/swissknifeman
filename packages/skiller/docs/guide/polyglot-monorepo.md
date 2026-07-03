# Polyglot-монорепо: как устроен platform-service

Гид по монорепо с несколькими языками/рантаймами под одной крышей — `services/` (ядро),
`packages/js|php|flutter/` (SDK), `apps/` (демо/потребители), `infra/` (Docker/K8s). Паттерн
встречается у externalized-платформ (например Loqum) — когда один продукт отдаёт SDK на
нескольких языках вокруг общего runtime-ядра (референс — `research/AUDIT-loqum-findings.md`
в корне репозитория).

## Когда монорепо, а когда — отдельные репозитории

**Монорепо оправдан**, если:
- SDK на разных языках **обязаны** синхронно следовать за одним protocol/contract (breaking
  change в контракте — заведомо breaking для всех SDK разом);
- есть общий CI, который должен провалиться, если PHP-SDK и Flutter-SDK разошлись по контракту;
- одна команда (или тесно связанные команды) владеет и ядром, и SDK.

**Отдельные репозитории лучше**, если:
- SDK развиваются разными командами с разным темпом релизов и не обязаны быть синхронны;
- языковые экосистемы тянут несовместимый тулинг (свои раннеры CI, свои релиз-циклы) и монорепо
  добавляет только оверхед синхронизации, не давая гарантий согласованности;
- потребители SDK не нуждаются в атомарных кросс-языковых коммитах.

Правило по умолчанию: **если контракт/protocol — общий и меняется одним PR** → монорепо.
Если каждый SDK — независимый продукт со своим roadmap → отдельные репозитории + version pinning
на контракт (semver-зависимость, не git submodule).

## Структура

```
<repo>/
├── services/
│   └── core/            # runtime-ядро (один язык, source of truth поведения)
├── contracts/            # protocol/schema — SSOT для codegen (см. ниже)
├── packages/
│   ├── js/               # SDK для Node/browser — codegen из contracts/
│   ├── php/              # SDK для PHP-потребителей — codegen из contracts/
│   └── flutter/          # SDK для Dart/Flutter — codegen из contracts/
├── apps/                 # демо-приложения / эталонные потребители SDK
└── infra/                # Docker, K8s-манифесты, CI-инфраструктура
```

Ядро (`services/core`) не обязано быть единственным — но если ядер несколько, у каждого свой
подкаталог в `services/`, а не смешение с SDK-пакетами в `packages/`.

## Dependency direction: строго вниз

```
contracts/  →  services/  →  packages/*  →  apps/
```

- **Contracts не зависят ни от чего** — это листовой узел графа зависимостей, чистое описание
  протокола (schema/IDL), без импорта рантайм-кода.
- **services/** зависят только от `contracts/`.
- **packages/*** (SDK) зависят от `contracts/` (через codegen) и, при необходимости, от `services/`
  как reference-реализации — но не наоборот.
- **apps/** зависят от `packages/*`, никогда не наоборот.
- **Upward-импорт запрещён**: `contracts/` не импортирует из `services/`; `services/` не
  импортирует из `packages/`.
- **App→app импорт запрещён**: приложения в `apps/` не импортируют друг друга напрямую — общий
  код между ними либо уже в `packages/`, либо не общий.

Нарушение направления — самый частый источник циклических зависимостей в polyglot-монорепо
(см. gotchas ниже); держите его видимым в CI (lint правил импорта/зависимостей per-package), а не
только в документации.

## Protocol/contracts как SSOT + codegen

Один источник истины формы данных и вызовов — `contracts/` (schema, IDL, OpenAPI/protobuf/аналог
в зависимости от протокола). Из него **генерируется** код для каждого языка-SDK, а не пишется
руками параллельно в трёх местах:

- contracts меняются одним PR → codegen перегенерирует клиентские типы для JS/PHP/Dart;
- ручной дрейф (кто-то поправил только PHP-SDK) невозможен структурно — сгенерированный код не
  редактируется вручную (гейт: генерируемые файлы — read-only в ревью, дифф релевантен только в
  `contracts/` и в codegen-конфиге);
- CI обязан проверять актуальность codegen (regenerate + diff --exit-code), а не доверять, что
  разработчик запустил генератор перед коммитом.

Без этого правила SDK неизбежно расходятся: PHP-SDK получит новое поле раньше Flutter-SDK, и
баг-репорты будут «поле есть в одном SDK и нет в другом» — а не «протокол изменился».

## Версионирование: per-package (дефолт), unified — только для узких lockstep-случаев

**Per-package semver — дефолт** для polyglot-монорепо: каждый SDK (`packages/js`, `packages/php`,
`packages/flutter`) версионируется независимо, публикуется в свой реестр (npm/Packagist/pub.dev) со
своим номером версии. Причины:
- SDK на разных языках редко релизятся синхронно (у Flutter-релиза может не быть breaking change,
  когда PHP получает major);
- потребители одного SDK не должны апгрейдиться из-за изменения в другом;
- это стандарт для polyglot monorepo tooling (см. Nx/Nrwl — независимые пакеты со своим
  версионированием как базовый режим, lockstep — опциональный режим поверх).

**Unified/lockstep-версионирование** (все пакеты одной версии одним релизом) оправдано только для
**узких, одноязычных** случаев — когда пакеты монорепо тесно связаны, релизятся всегда вместе и
предназначены одному кругу потребителей (типичный пример — набор пакетов одного фреймворка на
одном языке). Для polyglot-платформы с разными языками-потребителями lockstep создаёт ложную
синхронность: PHP-потребитель вынужден воспринимать "version bump", вызванный изменением только в
Flutter-SDK.

## Lockfiles: отдельные на менеджер, не общий

Каждый языковой пакет держит свой lockfile своего менеджера — не пытайтесь свести их в общий:

```
packages/js/package-lock.json     # npm/pnpm/yarn — свой lockfile
packages/php/composer.lock        # Composer — свой lockfile
packages/flutter/pubspec.lock     # pub — свой lockfile
```

Не смешивайте резолвинг зависимостей между экосистемами и не выносите один lockfile на корень
монорепо, покрывающий все языки — менеджеры разных экосистем не умеют читать чужие lockfiles, и
попытка унификации даёт либо нерабочий файл, либо ложное ощущение синхронизации версий, которого
на самом деле нет.

## CI: multi-lang

Матрица CI должна отражать реальные границы зависимостей, а не гонять всё на каждый PR:

- **Path-based триггеры**: изменение только в `packages/php/` не обязано гонять Flutter-тесты
  (и наоборот) — если только это не PR, трогающий `contracts/` (тогда гоняются **все** SDK, потому
  что контракт общий).
- **Отдельные job'ы на язык**: PHP job (composer install + PHPUnit), Node job (npm ci + vitest/jest),
  Flutter job (pub get + flutter test) — не один универсальный контейнер со всеми тулчейнами разом.
- **Codegen-проверка** — отдельный обязательный job: `regenerate contracts → git diff --exit-code`
  (ловит забытый ре-генерейт).
- **Build order** соответствует dependency direction: `contracts` codegen → `services` build/test →
  `packages/*` build/test (параллельно между языками, раз они не зависят друг от друга) → `apps`
  build/test.

## Gotchas

- **Циклические импорты** обычно означают нарушение dependency direction (см. выше) — SDK,
  импортирующий что-то из `apps/`, или `services/`, тянущий тип из конкретного SDK вместо
  `contracts/`. Чинится возвратом обязанности в `contracts/`, а не хаком в билд-графе.
- **Build order** — забытая сборка `contracts/` перед SDK даёт устаревший сгенерированный код,
  который молча компилируется (типы валидны, но не те). Явный шаг codegen перед сборкой каждого
  SDK, не полагаться на кэш.
- **Ложное ощущение синхронности** от unified-версионирования (см. выше) — тянет ненужные релизы.
- **Общий lockfile-соблазн** — не поддавайтесь: у каждого языка свой резолвер, свой lockfile.
- **Один CI-job на всё** — течёт время сборки линейно с числом языков; путайте параллельность
  языковых job'ов с параллельностью зависимостей (SDK можно билдить параллельно между собой, но
  не раньше `contracts`/`services`).
- **PR, трогающий только один SDK**, не должен требовать ревью от людей, незнакомых с этим языком —
  path-based CODEOWNERS снижает шум, но не отменяет обязательный codegen-check при правках
  `contracts/`.

## Skiller-интеграция

Для проекта такой формы (`services/` + `packages/js|php|flutter/` + `apps/` + `infra/`) в skiller
уже есть **project_type `platform-service`** ([профиль](https://github.com/academici/swissknifeman/blob/main/packages/skiller/profiles/platform-service.json)) —
включает бакеты `architect, ai, oss-dev, general, php, php-packages, frontend, frontend-vue,
frontend-backend, devops` + MCP `context7`. Использование:

```bash
skiller connect --profile platform-service
skiller vendor --profile platform-service
```

Кластерный **preset `polyglot-node-php-flutter`** (сквозной набор скиллов под эту связку языков
поверх профиля, по находке [#3 аудита интеграции Loqum](https://github.com/academici/swissknifeman/blob/main/research/AUDIT-loqum-findings.md))
на момент написания этого гайда **ещё не создан** — числится в бэклоге вместе с находкой
[#1](https://github.com/academici/swissknifeman/blob/main/research/AUDIT-loqum-findings.md), которая уже закрыта профилем `platform-service` выше. До появления пресета
переопределяйте бакеты профиля точечно через `buckets`/`exclude` в `.swissknife.json` /
`.swissknifeman/config.json` (см. [Профили и автодетект](./profiles) и [Чеклист
интеграции](./integration-checklist)).

## См. также
- [Профили и автодетект](./profiles) — как работает `project_type` → `buckets`.
- [Чеклист интеграции](./integration-checklist) — визард `skiller integrate` и ручные шаги.
- [Архитектура скиллов](./skills-architecture) — CORE-политика, два канала, два конфига.
