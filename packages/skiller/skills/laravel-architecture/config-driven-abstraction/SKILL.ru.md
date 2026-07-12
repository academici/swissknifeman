> 🌐 Перевод для человека. Агент использует SKILL.md, не этот файл.

---
name: config-driven-abstraction
bucket: laravel-architecture
version: 0.1.0
description: "Config-driven cache-safe Registry+Builder для мульти-панель/мульти-тенант Laravel: иммутабельный реестр key→instance, fluent builder с feature-флагами, name-maps в конфиге вместо closures, per-variant — конкретный класс, не runtime $table. Активировать при проектировании мульти-панель/мульти-тенант резолва, подключаемых драйверов. Триггеры: registry, builder pattern, config:cache, driver resolution."
risk: write
persona: oss-dev
tags: ["php", "laravel", "architecture", "config", "registry", "multi-tenant"]
requires: []
produces_for: []
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Config-Driven Abstraction (Registry + Builder)

Cache-safe подключаемые абстракции для мульти-панель / мульти-тенант / резолва драйверов.

## Правила

1. **Иммутабельный Registry: key → instance.** Резолвь панель/драйвер/стратегию по ключу из иммутабельного
   реестра, собранного на boot. Без мутаций после boot (предсказуемо, безопасно).
2. **`config:cache`-безопасность — никаких closures в конфиге.** Конфиг-массивы должны сериализоваться: карты
   имён на классы-строки (`'driver' => DatabaseDriver::class`), НЕ closures. Closure в конфиге молча ломает
   `php artisan config:cache`.
3. **Fluent builder; feature-флаги как методы.** `Panel::make()->withReactions()->withThreads()` — флаги это
   методы, не гигантский массив: поверхность типизирована и видна.
4. **Shared-дефолт + opt-in per-item.** По умолчанию общая схема/таблица; элемент явно opt-in'ит свою
   (per-panel таблицу) — не навязывай per-tenant-инфру всем.
5. **Per-variant = конкретный класс, не runtime `$table`.** Модель, меняющая `$table` в рантайме — footgun
   (кэш, связи, IDE). Определяй/генери конкретный сабкласс на вариант.
6. **`final` блокирует extend-and-swap.** Если потребители обязаны сабклассить под вариант — не помечай модель
   `final` (sibling-класс-обходка в тесте = запах дизайна).

## Красные флаги (реальные инциденты)

- Closures в конфиге → `config:cache` падает.
- Одна shared-модель с `setTable()` в рантайме на панель.
- `final` на модели, которую дизайн вариантов обязан расширять.

## Связанные

- `laravel-architecture:modular-architecture`, `php:production-readiness-checklist`.
