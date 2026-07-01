> 🌐 Перевод для человека. Агент использует SKILL.md, не этот файл.

---
name: config-driven-abstraction
bucket: laravel-architecture
version: 0.1.0
description: "Config-driven, cache-safe abstractions for multi-panel / multi-tenant Laravel: an immutable Registry (key→instance), a fluent Builder with feature-flags as methods, name maps in config (never closures — config:cache safe), shared schema + opt-in per-item, per-variant = a concrete class (not a shared model with runtime $table). Activate when designing multi-panel/multi-tenant resolution, pluggable drivers, a registry+builder. Triggers: multi-panel, multi-tenant, registry, builder pattern, config:cache, runtime table, driver resolution, per-panel."
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
