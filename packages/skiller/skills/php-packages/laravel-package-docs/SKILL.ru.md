> 🌐 Перевод для человека. Агент использует SKILL.md, не этот файл.

---
name: laravel-package-docs
bucket: php-packages
version: 0.3.0
description: "Use this skill when writing or revising package documentation after creating a package from this starter: README content, VitePress pages, contributing docs, upgrade notes, installation, usage, testing, workbench docs, or examples."
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

# Документация пакета

## Главная цель

Держите документацию пакета лаконичной, точной и полезной для разработчиков, которые устанавливают, настраивают, тестируют пакет и вносят в него вклад.

## Рабочий процесс

1. Изучите `README.md`, `docs/`, `docs/.vitepress/config.ts` и документацию для контрибьюторов, прежде чем писать новую документацию.
2. Используйте согласованно настроенные имя пакета (package name), vendor-slug, namespace, команды, ключи конфигурации (config keys) и publish-теги.
3. Удаляйте заметки по настройке, специфичные только для стартера (starter-only), как только они перестают применяться к настроенному пакету.
4. Покрывайте README, страницы VitePress, документацию для контрибьюторов, заметки по обновлению (upgrade notes), если они добавлены позже, и примеры использования пакета, выдерживая тон экосистемы Laravel.
5. Пишите прямую документацию в стиле Laravel: короткие абзацы, шаги настройки в повелительном наклонении, конкретные примеры и без маркетингового наполнения.
6. Держите содержимое README на высоком уровне (high level) и переносите более длинные руководства на страницы VitePress, когда детали отвлекают от первоначальной настройки пакета (first-run package setup).

## Правила написания

- Предпочитайте практические примеры абстрактным описаниям.
- Используйте настроенную идентичность пакета (package identity) в командах, URL, бейджах, namespace и publish-тегах.
- Делайте инструкции по установке, настройке, публикации, использованию, тестированию и workbench удобными для беглого просмотра.
- Объясняйте только то поведение, которое существует в реализованной возможности пакета (implemented package feature).
- Держите заголовки стабильными и предсказуемыми, чтобы авторы ниже по цепочке (downstream) могли безопасно удалять или расширять разделы.

## Справочные материалы

- `README.md`
- `docs/index.md`
- `docs/getting-started/installation.md`
- `docs/getting-started/configuration.md`
- `docs/getting-started/changelog.md`
- `docs/basics/defining-expressives.md`
- `docs/basics/converting-models.md`
- `docs/basics/relationships.md`
- `docs/basics/serialization.md`
- `docs/basics/persistence.md`
- `docs/commands/generator.md`
- `docs/commands/syncing.md`
- `.github/CONTRIBUTING.md`
- `docs/.vitepress/config.ts`

## Примеры

- Добавьте документацию по установке, которая показывает `composer require wendelladriel/laravel-expressive`, publish-теги и шаги миграции, когда это уместно.
- Добавьте документацию по установке и использованию, которая объясняет настройку пакета без избыточного документирования внутренностей (internals).

## Антипаттерны

- Документировать невыпущенные или нереализованные возможности пакета так, будто они существуют.
- Ломать плейсхолдеры (placeholders) или заменять их реальным именем vendor/пакета слишком рано.
- Дублировать крупные разделы между README и VitePress, когда достаточно короткой перекрёстной ссылки (cross-reference).
- Просачивать инструкции, специфичные только для стартера (starter-only), в документацию готового пакета.
