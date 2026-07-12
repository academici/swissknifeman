> 🌐 Перевод для человека. Агент использует SKILL.md, не этот файл.

---
name: transactional-outbox-relay
bucket: php
version: 0.1.0
description: "At-least-once async event delivery via transactional outbox: write+outbox in one transaction, relay-sweep sole retry owner, idempotent consumers, backoff+DLQ, after-commit effects. Activate wiring webhook/event delivery, an outbox, or async jobs that must not be lost/double-fired. Triggers: outbox, at-least-once, duplicate events, relay sweep."
risk: write
persona: oss-dev
tags: ["php", "laravel", "queue", "outbox", "reliability", "async"]
requires: []
produces_for: []
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Transactional Outbox + Relay

Надёжная доставка async-событий (webhooks, интеграционные события) без потерь и дублей.

## Ключевые инварианты

1. **Persist + outbox в ОДНОЙ транзакции.** Доменная запись и строка outbox коммитятся вместе
   (`DB::transaction`). Никогда не пиши outbox «best effort» после commit — падение между ними теряет событие.
2. **Единственный владелец retry — relay-sweep.** Фоновый relay опрашивает неотправленные строки outbox и
   доставляет. Job доставки НЕ должна сама вызывать `release()`/re-dispatch при сбое — два владельца
   (queue-retry + relay) гонятся за `attempts` и шлют дважды. Выбери ОДНО: retry владеет relay, job только
   репортит успех/сбой.
3. **Идемпотентные консьюмеры.** At-least-once → доставка может повториться. Консьюмер дедупит по стабильному
   event-id (unique-constraint / `INSERT … ON CONFLICT DO NOTHING`), НЕ read-then-insert (гонка под конкуренцией).
4. **Захват под локом.** Relay берёт пачку через `lockForUpdate` (или CAS по `claimed_at`), чтобы два
   relay-воркера не взяли одни строки.
5. **Backoff + DLQ.** Экспоненциальный backoff на транзиентных сбоях; после N попыток → dead-letter (не
   ретраить вечно, не терять молча).
6. **Side-effects после commit.** Broadcast/нотификации — в after-commit-листенере (`dispatchAfterCommit` /
   `->afterCommit()`), НЕ внутри транзакции: откат не должен оставить отправленный webhook.

## Красные флаги (реальные инциденты)

- Вставка outbox вне доменной транзакции.
- `ShouldQueue`-job зовёт `$this->release()`, пока relay тоже пере-свипает → гонка на `attempts` (двойная доставка).
- Консьюмер делает `if (!exists) insert` вместо unique-constraint.
- Событие диспатчится внутри `DB::transaction` (откат листенера ≠ откат события).

## Связанные

- `php:production-readiness-checklist` — проверочный проход (атомарность / гонки / after-commit).
- `php:repositories` — слоистость персистенса для доменной записи.
