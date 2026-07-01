> 🌐 Перевод для человека. Агент использует SKILL.md, не этот файл.

---
name: cursor-pagination-design
bucket: php
version: 0.1.0
description: "Stable keyset (seek) pagination for infinite scroll / feeds: pick a sortable non-nullable key, composite index, handle ties and concurrent inserts, avoid offset drift. Activate when building infinite-scroll, cursor/seek pagination, message/feed lists, or fixing 'duplicates/skips while scrolling'. Triggers: cursor pagination, keyset, seek pagination, infinite scroll, paginate after, nullable order key, offset drift, last_message_at."
risk: write
persona: oss-dev
tags: ["php", "laravel", "pagination", "cursor", "database"]
requires: []
produces_for: []
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Cursor (keyset / seek) Pagination

Стабильная пагинация для лент/infinite-scroll, где строки вставляются, пока пользователь листает.

## Правила

1. **Ключ = сортируемая NON-nullable колонка** — лучше sortable PK (uuid7 / ulid / snowflake) или композит
   `(sort_col, id)`. `NULL`-абельный order-key (напр. `last_message_at`) — КРАСНЫЙ ФЛАГ: `NULL` не сравним,
   cursor пропускает/двоит строки. Фикс: синтетический non-null ключ, `COALESCE` к sentinel + tiebreak, или
   откат на offset.
2. **Композитный tiebreak.** Сортируй по `(sort_col, id)` и сикай `WHERE (sort_col, id) < (?, ?)`, чтобы равные
   `sort_col` не теряли и не повторяли строки.
3. **Композитный индекс** ровно в порядке `(sort_col, id)` — иначе seek сканирует.
4. **Offset нестабилен** при конкурентных вставках (строки сдвигаются) — не используй `OFFSET` для живых лент;
   keyset insert-стабилен.
5. **Непрозрачный cursor.** Кодируй `(sort_col, id)` в токен; не отдавай сырые id/timestamp, которые клиент
   подделает.

## Красный флаг (реальный инцидент)

- `orderBy('last_message_at')->cursorPaginate()`, где `last_message_at` nullable — тест, штампующий `now()`
  на каждую строку, прячет баг NULL-сортировки; продакшен-строки с NULL ломают cursor.

## Связанные

- `php:database` (индексы), `php:production-readiness-checklist` (инвариант cursor).
