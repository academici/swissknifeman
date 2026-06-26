> 🌐 Перевод для человека. Агент использует SKILL.md, не этот файл.

---
name: laravel-package-expressive
bucket: php-packages
version: 0.3.0
description: "Upstream-скилл для работы НАД самим пакетом WendellAdriel/laravel-expressive (starter kit), не общий скилл пакетной разработки: placeholders, configure flow, starter defaults, root guidance, local skills, temporary phase tests, dist hygiene, scaffold-wide conventions. Do not use for ordinary package feature work after a package has been configured."
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

# Разработка Expressive

## Главная цель

Развивать starter kit, не делая его менее полезным для будущих авторов пакетов.

## Рабочий процесс

1. Сохраняй общие плейсхолдеры, такие как `Wendell Adriel`, `Expressive`, `wendelladriel` и `expressive`, до тех пор, пока их не заменит configure flow (поток настройки).
2. Держи стартовое руководство минимальным и разделяй правила сопровождения expressive и правила автора пакета.
3. Используй временные phase-тесты scaffold-а (каркаса), когда проверяешь форму репозитория, паритет файлов или сгенерированный scaffolding (каркасную генерацию); удаляй эти тесты перед финальной валидацией.
4. Держи `.claude/skills` и `.agents/skills` зеркально синхронизированными при добавлении или редактировании локальных скиллов.
5. Держи карты прунинга (отсечения) фич и инструментов в `configure.php` согласованными со service provider, метаданными Composer, разделами README, документацией, AI-руководством, скиллами и публикуемыми файлами.
6. Держи файлы авторского процесса (development-time) вне dist-архивов Composer с помощью `.gitattributes`, когда они не являются рантайм-файлами пакета.

## Ссылки

- `AGENTS.md`
- `CLAUDE.md`
- `.agents/skills/`
- `.claude/skills/`
- `configure.php`
- `.gitattributes`
- `PLAN.md`, `REQS.md` и `phases/`, когда они присутствуют

## Примеры

- Добавляй или переименовывай локальный скилл, обновляя обе агентные экосистемы, имена во front matter, корневое руководство и любые проверки консистентности scaffold-а.
- Добавляй временные Phase-тесты, чтобы зафиксировать форму сгенерированных файлов, запускай их, чтобы доказать изменение, затем удаляй их перед финальным `composer test`.
- Обновляй документацию, чувствительную к плейсхолдерам, сохраняя содержимое delete-fence (блока-ограждения на удаление), которое должно исчезнуть после настройки.
- При добавлении выбираемой фичи пакета добавляй и стартовые файлы, и соответствующее поведение прунинга в configure, чтобы авторы пакетов могли чисто от неё отказаться.

## Анти-паттерны

- Оставлять временные phase-тесты в поставляемом стартовом наборе тестов.
- Помещать правила сопровождения expressive в скиллы, обращённые к пакету (package-facing).
- Заменять плейсхолдеры одним реальным именем пакета в стартовых файлах.
- Добавлять рантайм-зависимости ради удобства сопровождения репозитория.
