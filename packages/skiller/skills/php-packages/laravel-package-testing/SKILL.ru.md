> 🌐 Перевод для человека. Агент использует SKILL.md, не этот файл.

---
name: laravel-package-testing
bucket: php-packages
version: 0.3.0
description: "Use this skill when writing, editing, fixing, or reviewing package tests with Pest 4 and Orchestra Testbench, including TDD, feature tests, unit tests, type coverage, arch tests, workbench behavior, commands, routes, config, migrations, and publishable resources."
risk: write
persona: oss-dev
tags: ["php", "laravel", "package-dev"]
requires: []
produces_for: []
outputs: []
adapters: [claude, cursor, fable]
upstream: WendellAdriel/laravel-expressive
license: MIT
sha256: ""
---

# Тестирование пакета

## Главная цель

Доказать поведение пакета с помощью Pest 4, Orchestra Testbench и локальной настройки `tests/TestCase.php` — до реализации или параллельно с ней.

## Рабочий процесс

1. Начинай с TDD: напиши наименьший падающий тест пакета для запрошенного поведения, затем реализуй наименьшее изменение, которое заставляет его проходить.
2. Покрывай happy-path (успешный сценарий), unhappy-path (сценарий с ошибкой) и граничные случаи, когда у фичи есть значимые режимы отказа.
3. Предпочитай сфокусированные feature-тесты для поведения интеграции пакета и arch-тесты для широких ограничений.
4. Используй `composer test:unit -- --filter ...` во время итераций, `composer test:types` — когда менялись типочувствительные тесты или код, и `composer test` — перед завершением.
5. Держи реальные тесты пакета в наборе и удаляй только одноразовые тесты, явно созданные для локальных экспериментов со скаффолдингом.

## Справочные материалы

- `tests/TestCase.php`
- `tests/Pest.php`
- `tests/Feature/`
- `tests/Unit/`
- `tests/ArchTest.php`
- скрипты `composer.json`

## Примеры

- Протестируй слияние конфига и переопределение конфига: сначала проверь дефолтный конфиг пакета, затем переопредели значение в хост-конфиге в приложении Testbench.
- Протестируй публикуемые ассеты, миграции, представления (views), файлы переводов (lang) или конфиг: вызови поведение vendor publish и проверь, что целевой путь существует.
- Протестируй маршруты через HTTP-запросы Testbench, команды — через Artisan-ассерты, миграции — с тестовой базой SQLite, и поведение workbench — после `composer build`, когда это нужно.

## Антипаттерны

- Удаление реальных тестов пакета только потому, что они неудобны.
- Опора только на smoke-тесты, когда поведение требует ассертов.
- Тестирование деталей реализации, когда доступно наблюдаемое поведение пакета.
- Хранение одноразовых тестов-экспериментов со скаффолдингом в наборе тестов пакета.

## Ссылки

- Скилл `quality/test-strategy` — стратегия пирамиды и coverage policy
