# Roadmap: стек-пак `php-package` (dev-loop для пакетов, не приложений)

**Статус: реализовано** в `agent-packs/laravel-package@0.1.0` (мастер-план `SKM-MASTER-002`,
фаза F / P6). Критерий внедрения (замеренное трение на azguard, ниже) сработал, отдельный пак
заведён. Текст ниже (проблема/дизайн/риски) сохранён как история задумки; фактическая реализация
разошлась с ней в нескольких пунктах — **принятые отклонения**:

- **Отдельный пак вместо режима внутри `backend-laravel`.** Задумка не обсуждала форму; по факту
  дизайн-фаза (D12) сначала попробовала bool-флаг `IS_LARAVEL_PACKAGE` поверх `backend-laravel` и
  выпилила его — идентичность агентов «пакет ≠ приложение» не сводится к условной ветке в общем
  паке, потребовался самостоятельный `packages/harness/configs/claude-code/agent-packs/laravel-package/`.
- **`src_pack`-реюз вместо копирования.** `review-gate.sh`/`review-gate.env.ini`/
  `settings.fragment.json` не задублированы в новом паке — движок `harness agent-packs` получил
  поле `src_pack` (files[] резолвит исходник из каталога другого пака), новый пак лишь владеет
  файлом в проекте, содержимое общее с `backend-laravel`.
- **Parity-тест shared-блоков.** Общая проза (severity-формат, «Детект ≠ гейтинг» и т.п.) размечена
  `<!-- shared:name -->` в обоих паках и сверяется байт-в-байт тестом (`test_agentpacks_shared.py`) —
  анти-дубль зафиксирован машиной, а не полагается на ручную дисциплину при правках.
- **BC-ось через Roave при наличии бинаря, не обязательный инструмент.** `BC_CHECK_CMD` —
  интервью-проба (`test -x vendor/bin/roave-backward-compatibility-check`); пустой ответ — валидное
  состояние, ось остаётся прозой в reviewer вместо жёсткого требования зависимости.

Пилоты — azguard (одиночный пакет) и chatom (монорепо `packages/*/src`); профиль
`packages/skiller/profiles/php-package.json` называет `agent_pack: ["laravel-package", "_common"]`.

## Проблема

Стек-паки сейчас: `backend-laravel`, `node-frontend`, `python-backend`, `dart-flutter`. Для **PHP-пакета**
(не приложения) подходящего нет. `backend-laravel` — ближайший, но его dev-loop заточен под
**приложение**: slice-builder строит `route → controller → Action/Repository → DTO → policy`,
rules/api-controllers.md и migrations.md предполагают HTTP-слой и схему приложения. Пакет же:
- тестируется через **Orchestra Testbench** (in-memory sqlite), а не `php artisan test`;
- часто **не имеет** маршрутов/контроллеров (core-логика, сервис-провайдер, контракты);
- **владеет своими миграциями** и публикуемыми ресурсами (config/views/migrations publish);
- цикл — «контракт → реализация → Pest-тест на Testbench → mutation (infection) → ревью».

Поймано на онбординге **azguard** (RBAC-пакет: core + Filament + context). `backend-laravel` v0.3.0
после фикса работает, но идентичность агентов всё ещё «срез поверх моделей приложения».

## Дизайн (когда дойдём)

- Новый пак `php-package` (`packages/harness/configs/claude-code/agent-packs/php-package/`):
  - **слайс-юнит = «фича пакета»**, а не route-срез: контракт/интерфейс → реализация (Action/Service/
    value-object) → публикуемые ресурсы (миграции/конфиг) при необходимости.
  - **test-writer** на Testbench: `orchestra/testbench`, `TestCase` пакета, in-memory sqlite,
    `loadMigrationsFrom`/package providers; `{{TEST_FRAMEWORK}}` (Pest/PHPUnit).
  - **reviewer** с упором на публичный API/BC (semver), `phpstan`/`larastan` уровень, mutation-score
    (`infection`), а не на access-layer приложения.
  - rules: `public-api-bc.md` (обратная совместимость), `package-resources.md` (publish/discovery),
    вместо `api-controllers.md`.
  - requires.skills: `php-packages/*` (scaffold/service-provider/testing/packages), `laravel-testing`,
    `quality/mutation-testing`, `architect/security-design`.
- Профиль `php-package` (`packages/skiller/profiles/php-package.json`) получает `agent_pack: "php-package"`
  (сейчас стек-пак из профиля не ставится — пакеты онбордятся без dev-loop стек-пака либо берут
  `backend-laravel` вручную).
- Роль-пак `role-maintainer` остаётся поверх (OSS-сопровождение) — ортогонален стеку.

## Риски / почему осторожно

- Не плодить пак ради пака: `backend-laravel` v0.3.0 уже параметричен и **рабочий** для пакета.
  Заводить отдельный только при повторном замеренном трении (несколько пакетов, не один azguard).
- Дубль с `backend-laravel`: вынести общий каркас (`_common`, review-gate, git-дисциплина) в общую
  основу, специфика пакета — поверх, чтобы не копировать шаблоны.

## Связано

- `field-feedback-loop` — этот файл = путь 2 (новое/проектируемое), поймано на azguard.
- `project-tooling-runbook` §«Агенты/роли (agent-packs)» — как паки ставятся из профиля.
- CHANGELOG `backend-laravel` 0.3.0 — деуниверсализация шаблонов (предшествующий путь-1 фикс).
