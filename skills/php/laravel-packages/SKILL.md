---
name: laravel-packages
bucket: php
version: 0.3.0
description: "Создание Laravel-пакетов: scaffold, тесты, публикация скиллов пакета потребителям через vendor:publish"
risk: write
persona: oss-dev
tags: ["php", "laravel"]
requires: []
produces_for: []
outputs: []
snippets: ["composer.json.stub", "ServiceProvider.stub.php", "config.stub.php", "boost-skill-publisher.php", "TestCase.stub.php"]
adapters: [claude, cursor, fable]
sha256: ""
---

## Контекст

Создание Laravel-пакета с нуля или доработка существующего: scaffold
(composer.json, ServiceProvider, config, тесты) и — если пакет несёт доменную
экспертизу — публикация собственных скиллов потребителям через `vendor:publish`.

Принцип vendor-skills: пакет, который решает доменную задачу (безопасность,
биллинг, интеграции), знает о своей предметной области больше, чем универсальный
реестр. Такой пакет возит свои скиллы с собой — потребитель ставит пакет и
одной artisan-командой получает скиллы для работы AI-агента с этим пакетом.

## Входные данные

- Название пакета (`vendor/package`) и его назначение
- Целевые версии PHP/Laravel
- Есть ли у пакета доменные знания, полезные агенту потребителя
  (паттерны использования, миграционные сценарии, типовые ошибки)

## Алгоритм

1. Scaffold по сниппетам: `composer.json.stub`, `ServiceProvider.stub.php`,
   `config.stub.php`, `TestCase.stub.php`. Заменить плейсхолдеры на имя пакета.
2. Если пакет публикует скиллы:
   - создать `resources/skills/<package>-<skill>/SKILL.md` (+ `snippets/`).
     Имя папки скилла — **с префиксом пакета**, чтобы у потребителя не было
     коллизий с другими источниками;
   - добавить в ServiceProvider публикацию по `boost-skill-publisher.php`:
     агент-нейтральная раскладка (`.ai/skills/vendor/<package>/`) и/или плоская
     для Claude Code (`.claude/skills/`);
   - тег публикации — `<package>-skills`.
3. Тест полного цикла: `composer install` в тестовом приложении →
   `php artisan vendor:publish --tag=<package>-skills` → проверить, что
   `SKILL.md` лёг по ожидаемому пути и агент его видит.
4. Прогнать тесты пакета и линтеры (pest/phpunit, pint, phpstan).

## Выходные данные

- Рабочий scaffold пакета
- `resources/skills/` с публикуемыми скиллами (если применимо)
- Публикация в ServiceProvider с тегом `<package>-skills`

## Чеклист качества

- [ ] composer.json: PSR-4, поддерживаемые версии PHP/Laravel, extra.laravel
- [ ] Публикуемые скиллы имеют валидный frontmatter (`name`, `description`)
- [ ] Имена папок скиллов префиксованы именем пакета
- [ ] `vendor:publish --tag=<package>-skills` проверен в чистом приложении
- [ ] Тесты и статанализ зелёные

## Ссылки

- snippets/boost-skill-publisher.php
- snippets/ServiceProvider.stub.php
- snippets/composer.json.stub
