---
name: static-analysis
bucket: php
version: 0.1.0
description: "Статический анализ и линтинг PHP/Laravel: Laravel Pint, PHPStan и Rector локально и в CI"
risk: write
persona: oss-dev
tags: [php, laravel, quality]
requires: []
produces_for: []
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Статический Анализ и Линтинг (PHP / Laravel)

Для обеспечения высокого качества кода на Backend используются три основных инструмента: **Laravel Pint**, **PHPStan** и **Rector**. 
Они должны использоваться совместно в локальной разработке и запускаться в CI пайплайнах.

## 1. Laravel Pint (Code Styling)

Pint — это opinionated PHP code style fixer для Laravel на базе PHP-CS-Fixer.

**Использование:**
-   Запуск: `./vendor/bin/pint`
-   В CI: `./vendor/bin/pint --test` (чтобы падал, если стиль нарушен).

**Конфигурация (`pint.json`):**
По умолчанию Pint использует пресет `laravel`. Для проектов рекомендуется строго придерживаться его, избегая избыточной кастомизации конфигурации.

## 2. PHPStan (Static Analysis)

PHPStan находит ошибки в коде без его выполнения. В Laravel используется обертка `nunomaduro/larastan`.

**Использование:**
-   Запуск: `./vendor/bin/phpstan analyse`

**Конфигурация (`phpstan.neon`):**
-   **Level:** Рекомендуется начинать с Level 5 для существующих проектов. Для новых (Greenfield) проектов **всегда устанавливайте Level 8 или 9** (максимально строгий).
-   Обязательно включите проверку типов и отсутствие неопределенных переменных.
-   Всегда используйте PHPDoc (`@var`, `@return`, `@param`) там, где стандартная типизация PHP недостаточно описывает структуру данных (например, структуры массивов или генерики коллекций).

## 3. Rector (Instant Upgrades & Refactoring)

Rector автоматически обновляет код до новых версий PHP или фреймворка, а также применяет архитектурные улучшения (Dead Code elimination, Type Declaration).

**Использование:**
-   Анализ (что будет изменено): `vendor/bin/rector process --dry-run`
-   Применение изменений: `vendor/bin/rector process`

**Конфигурация (`rector.php`):**
Обычно подключаются сеты (sets):
-   `SetList::DEAD_CODE` (удаление неиспользуемого кода).
-   `SetList::PHP_82` / `PHP_83` (обновление до актуальной версии языка).
-   `LevelSetList::UP_TO_PHP_8X`
-   Для Laravel проектов используется плагин `rector/rector-laravel`.

## Workflow Разработчика

Перед каждым коммитом или пушем рекомендуется выполнять следующую цепочку:

1.  `vendor/bin/rector process` (оптимизируем код)
2.  `vendor/bin/pint` (форматируем код)
3.  `vendor/bin/phpstan analyse` (убеждаемся, что ничего не сломали)
4.  Запуск тестов (`phpunit` / `pest`)

*Подсказка:* Для удобства добавьте эту цепочку как алиас в `Makefile` (например, `make lint`).
