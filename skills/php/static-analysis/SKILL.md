---
name: static-analysis
bucket: php
version: 0.2.0
description: "Статический анализ и линтинг PHP/Laravel: Laravel Pint, PHPStan и Rector локально и в CI, эталонные конфиги"
risk: write
persona: oss-dev
tags: [php, laravel, quality]
requires: []
produces_for: []
outputs: []
snippets: ["pint.json", "phpstan.neon", "rector.php", "qa-composer-scripts.json"]
adapters: [claude, cursor, fable]
sha256: ""
---

## Контекст

Для обеспечения высокого качества кода на Backend используются три основных инструмента: **Laravel Pint**, **PHPStan** и **Rector**.
Они должны использоваться совместно в локальной разработке и запускаться в CI пайплайнах. Эталонные конфиги — в `snippets/`.

## Алгоритм

### 1. Laravel Pint (Code Styling)

Pint — это opinionated PHP code style fixer для Laravel на базе PHP-CS-Fixer.

**Использование:**
-   Запуск: `./vendor/bin/pint`
-   В CI: `./vendor/bin/pint --test` (чтобы падал, если стиль нарушен).

**Конфигурация (`pint.json`):**
База — пресет `laravel`. Эталонная надстройка (сниппет `pint.json`): `declare_strict_types`, `date_time_immutable`, `final_class`, `fully_qualified_strict_types`, `global_namespace_import`, `mb_str_functions`, `ordered_class_elements`, `strict_comparison`, `protected_to_private`. Избегайте дальнейшей избыточной кастомизации.

> Правило `final_class` конфликтует с гайдлайнами Spatie («не использовать `final` по умолчанию», скилл `code-style-spatie`): проект выбирает один подход и следует ему консистентно.

### 2. PHPStan (Static Analysis)

PHPStan находит ошибки в коде без его выполнения. В Laravel используется обертка `larastan/larastan`.

**Использование:**
-   Запуск: `./vendor/bin/phpstan analyse`

**Конфигурация (`phpstan.neon`, сниппет):**
-   **Level:** для существующих проектов можно начинать с Level 5 и подниматься. Для новых (Greenfield) проектов **сразу устанавливайте `level: max`** — поднимать уровень на живом проекте дороже, чем держать max с первого коммита.
-   Эталон: include larastan, `paths: [app]`, `inferPrivatePropertyTypeFromConstructor: true`.
-   Обязательно включите проверку типов и отсутствие неопределенных переменных.
-   Всегда используйте PHPDoc (`@var`, `@return`, `@param`) там, где стандартная типизация PHP недостаточно описывает структуру данных (например, структуры массивов или генерики коллекций). На `level: max` основная работа — сужать `array` в публичных API: `@return array{...}`, `@phpstan-type`, типизированные DTO.

### 3. Rector (Instant Upgrades & Refactoring)

Rector автоматически обновляет код до новых версий PHP или фреймворка, а также применяет архитектурные улучшения (Dead Code elimination, Type Declaration).

**Использование:**
-   Анализ (что будет изменено): `vendor/bin/rector process --dry-run`
-   Применение изменений: `vendor/bin/rector process`

**Конфигурация (`rector.php`, сниппет):**
-   `withSetProviders(LaravelSetProvider::class)` + `withComposerBased(laravel: true)` (плагин `driftingly/rector-laravel`).
-   Сеты: `SetList::TYPE_DECLARATION` + Laravel-сеты (`LARAVEL_CODE_QUALITY`, `LARAVEL_COLLECTION`, `LARAVEL_FACTORIES`, `LARAVEL_IF_HELPERS` и др.).
-   `withPreparedSets(deadCode, codeQuality, typeDeclarations, privatization, earlyReturn)` и `withPhpSets()` для актуальной версии языка.

### Workflow разработчика: rector → pint → phpstan → tests

Перед каждым коммитом или пушем выполняется строго в этом порядке:

1.  `vendor/bin/rector process` — рефакторинг/модернизация кода
2.  `vendor/bin/pint` — форматирование (подчищает за Rector)
3.  `vendor/bin/phpstan analyse` — убеждаемся, что ничего не сломали
4.  Запуск тестов (`phpunit` / `pest`)

*Подсказка:* цепочка оформляется composer-скриптами (сниппет `qa-composer-scripts.json`: `lint`, `lint:check`, `analyse`, `refactor`, `qa`, `ci:check`) или алиасом в `Makefile`.

## Когда какой сниппет открывать

| Ситуация | Файл |
|:---|:---|
| Настраиваю стиль кода / правила Pint | `pint.json` |
| Подключаю PHPStan/Larastan, выбираю level | `phpstan.neon` |
| Настраиваю Rector с Laravel-сетами | `rector.php` |
| Оформляю QA-конвейер в composer scripts / CI | `qa-composer-scripts.json` |

## Чеклист качества

- [ ] Pint: пресет `laravel` + строгие правила из эталона; в CI — `pint --test`
- [ ] PHPStan: `level: max` для greenfield (для legacy — план повышения уровня)
- [ ] Rector: TYPE_DECLARATION + Laravel-сеты + prepared sets (deadCode/codeQuality/typeDeclarations/privatization/earlyReturn)
- [ ] Порядок прогона: rector → pint → phpstan → tests (и локально, и в CI)
- [ ] Решение по `final_class` согласовано со стилем проекта (см. `code-style-spatie`)
- [ ] Composer-скрипты `lint` / `lint:check` / `analyse` / `refactor` заведены

## Ссылки

- Скилл `code-style-spatie` (bucket php) — стиль кода, конфликт `final_class`
- Скилл `laravel-testing` (bucket php) — тесты и coverage gate в конце конвейера
- https://laravel.com/docs/pint, https://phpstan.org, https://getrector.com
