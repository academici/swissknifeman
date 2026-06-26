> 🌐 Перевод для человека. Агент использует SKILL.md, не этот файл.

---
name: laravel-package-service-provider
bucket: php-packages
version: 0.3.0
description: "Use this skill when changing a Laravel package service provider: config merges, routes, views, translations, publishing, migrations, assets, Blade components, commands, console-only behavior, or package metadata."
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

# Сервис-провайдер пакета

## Главная цель

Подключать возможности пакета через явный код сервис-провайдера Laravel, не уходя по умолчанию в `spatie/laravel-package-tools`.

## Рабочий процесс

1. Изучите сервис-провайдер пакета и сохраните его существующее разделение на методы. Если пакет использует имена вроде `registerResources`, `registerPublishing`, `registerBladeComponents`, `registerConsole` или `registerAboutMetadata` — добавляйте новое поведение в соответствующую зону ответственности.
2. Размещайте привязки контейнера и вызовы `mergeConfigFrom` в `register()`, когда host-приложение должно иметь возможность переопределить конфигурацию.
3. Размещайте загрузку ресурсов в boot-методах с нативными для Laravel API, такими как `loadRoutesFrom`, `loadViewsFrom` и `loadTranslationsFrom`.
4. Оборачивайте только-консольную публикацию и регистрацию команд проверкой `runningInConsole()` перед вызовом `publishes`, `publishesMigrations` или `commands`.
5. Добавляйте тесты для наблюдаемого поведения пакета: слитая конфигурация, загруженные маршруты, теги публикации, регистрация команд или метаданные `about`.

## Ссылки

- `src/*ServiceProvider.php`
- `config/*.php`
- `routes/*.php`
- `resources/views/`
- `lang/`
- `database/migrations/`
- `src/Console/Commands/`

## Примеры

- Подключите новый тег публикации, добавив карту `publishes` внутри существующего метода публикации, защищённого проверкой консоли, и назовите тег по шаблону `expressive-*`.
- Добавьте команду, создав класс команды, импортировав его в провайдере и добавив его в массив `commands` внутри проверки `runningInConsole()`.

## Антипаттерны

- Загрузка состояния host-приложения слишком рано — во время регистрации провайдера.
- Вызов `env()` вне конфиг-файлов; избегайте `env() outside config`, используя вместо этого значения конфигурации после `mergeConfigFrom`.
- Безусловная регистрация только-веб зон ответственности, когда пакет может работать в консольных контекстах.
- Замена явных методов провайдера на `spatie/laravel-package-tools` по умолчанию.
