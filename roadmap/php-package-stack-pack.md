# Roadmap: стек-пак `php-package` (dev-loop для пакетов, не приложений)

**Статус:** отложено. **Критерий внедрения:** замеренное трение при использовании `backend-laravel`
на пакетах — даже после деуниверсализации (v0.3.0) пак сохраняет app-ориентированные допущения
(маршруты/контроллеры/policy, «вертикальный срез route→controller→Action→DTO»), которых у библиотеки
нет. Если онбординги пакетов повторно упираются в это — заводим отдельный пак.

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
