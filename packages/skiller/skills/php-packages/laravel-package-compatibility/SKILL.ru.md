> 🌐 Перевод для человека. Агент использует SKILL.md, не этот файл.

---
name: laravel-package-compatibility
bucket: php-packages
version: 0.3.0
description: "Use this skill when reviewing Laravel package compatibility across composer constraints, PHP versions, Laravel versions, Testbench versions, dependency stability lanes, Windows CI, or matrix-sensitive code and workflow changes."
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

# Совместимость пакета

## Главная цель

Поддерживать код пакета, его зависимости и workflow-процессы совместимыми с поддерживаемой матрицей Laravel 12/13 и PHP 8.3+.

## Рабочий процесс

1. Сначала прочитай `composer.json`, чтобы определить ограничения по PHP, Laravel и Testbench.
2. Сверяй изменённый код с API Laravel 12/13 и синтаксисом PHP 8.3+ перед тем, как использовать более новые возможности фреймворка или языка.
3. Проверь `.github/workflows/tests.yml` на предмет полос стабильности зависимостей (dependency stability lanes), покрытия prefer-lowest, покрытия prefer-stable и вопросов, связанных с Windows.
4. При изменении зависимостей убедись, что ограничения по-прежнему допускают нужные версии Laravel и Testbench.
5. Проверяй наименьшей доступной локальной командой, а затем полагайся на CI для полного покрытия матрицы по ОС и зависимостям.

## Справочные материалы

- `composer.json`
- `.github/workflows/tests.yml`
- `phpstan.neon.dist`
- `tests/`
- `workbench/`

## Примеры

- Проверь новый вызов API Laravel, убедившись, что он существует в Laravel 12 и Laravel 13, прежде чем вливать его в общий код пакета.
- Проверь повышение версии зависимости, сверив ограничения Composer, ограничения Testbench, поведение prefer-lowest и предположения о путях в Windows.

## Анти-паттерны

- Считать, что последняя локальная версия зависимости представляет всю матрицу поддержки.
- Добавлять синтаксис PHP или API Laravel, выходящие за пределы ограничений `composer.json`.
- Игнорировать разделители путей в Windows, предположения об исполняемых файлах или синтаксис, работающий только в одной оболочке (shell-only), в тестах и workflow-процессах.
- Убирать полосы стабильности зависимостей (dependency stability lanes) только потому, что они медленнее, чем один «счастливый путь» (happy path).
