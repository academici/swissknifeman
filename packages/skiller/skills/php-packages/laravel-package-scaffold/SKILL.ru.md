> 🌐 Перевод для человека. Агент использует SKILL.md, не этот файл.

---
name: laravel-package-scaffold
bucket: php-packages
version: 0.3.0
description: "Use this skill when adding Laravel package capabilities or package shape changes after creating a package from this starter: commands, migrations, routes, config, views, assets, middleware, workbench files, or new publishable resources."
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

# Каркас пакета (Package Scaffold)

## Главная цель

Добавлять возможности пакета в правильное место, сохраняя согласованность имён пакетов, пространств имён (namespaces), ключей конфигурации (config keys) и тегов публикации (publish tags).

## Рабочий процесс (Workflow)

1. Перед созданием файлов изучите существующую структуру пакета, примеры из соседних (sibling) пакетов, заметки по настройке в README и текущий сервис-провайдер (service provider); коротко: сначала изучите существующую структуру пакета и соседние примеры.
2. Определите, чего касается запрос: команд (commands), миграций (migrations), маршрутов (routes), конфигурации (config), представлений (views), ассетов (assets), изменений формы пакета (package shape changes), тестов (tests), документации (docs), совместимости (compatibility) или процесса релиза (release flow).
3. Используйте нативные для Laravel конвенции пакетов и сохраняйте согласованность пространств имён, тегов публикации, документации, ключей конфигурации, URL и бейджей (badges) с настроенным пакетом.
4. Используйте `package-service-provider` для подключения провайдера (provider wiring), `package-testing` для покрытия тестами, `package-docs` для документации, `package-compatibility` для изменений, чувствительных к матрице совместимости (matrix-sensitive), и `package-release` для задач релиза.
5. Если этот стартер ещё не был сконфигурирован, сохраняйте сопоставления (mappings) в `configure.php` при добавлении или удалении выбираемых возможностей (selectable capabilities), чтобы очистка при отказе (opt-out cleanup) оставалась точной.
6. Добавляйте только те файлы, которые нужны для запрошенной возможности, и проверяйте самой узкой релевантной командой перед более широкими проверками.

## Справочные материалы (References)

- `src/*ServiceProvider.php`
- `config/*.php`
- `routes/*.php`
- `resources/views/`
- `database/migrations/`
- `public/`
- `tests/Feature/` и `tests/Unit/`

## Примеры (Examples)

- Добавить Artisan-команду: создайте класс команды в `src/Console/Commands`, зарегистрируйте его в провайдере, добавьте feature-тест на наблюдаемый вывод консоли (observable console output) и задокументируйте команду, если она обращена к пользователю (user-facing).
- Добавить публикуемую миграцию: поместите миграцию в `database/migrations`, подключите её через провайдер с тегом `expressive-migrations` и протестируйте поведение публикации (publish behavior) с помощью Testbench.

## Антипаттерны (Anti-Patterns)

- Добавлять неиспользуемый каркас (scaffolding), потому что пакету это может понадобиться позже.
- Смешивать старые имена-заглушки (placeholder names) с настроенным именем пакета.
- Избегайте изменения зависимостей без согласования.
- Заменять явный код Laravel-пакета абстракцией-хелпером, когда хватило бы одного изменения под конкретную возможность.
