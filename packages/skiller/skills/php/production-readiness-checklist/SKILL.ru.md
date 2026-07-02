> 🌐 Перевод для человека. Агент использует SKILL.md, не этот файл.

---
name: production-readiness-checklist
bucket: php
version: 0.1.0
description: "Verify production-readiness invariants happy-path tests miss: transaction atomicity, race-condition-safe idempotency, config defaults, non-nullable cursor keys, after-commit side-effects, soft-delete, id-strategy compatibility, single queue-retry owner, atomic state transitions. Activate before/at review of risky Laravel slices (services, queues, drivers, migrations), queue semantics, or before merge."
risk: read
persona: oss-dev
tags: ["php", "laravel", "review", "production", "reliability", "quality"]
requires: []
produces_for: []
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Production-Readiness Checklist

Целый класс дефектов невидим per-unit happy-path тестам (они форсят нужное состояние). Проверь это на
рисковых срезах ДО merge — рассуждением, не только по зелёным тестам.

## Атомарность и side-effects

- Multi-table мутации внутри `DB::transaction` (откат не оставляет полу-записи)?
- События/broadcast/джобы — ПОСЛЕ commit (`dispatchAfterCommit` / after-commit-листенер), не внутри транзакции?

## Race-safety / идемпотентность

- Конкурентные retry не двоят: дедуп через unique / `INSERT … ON CONFLICT` либо `lockForUpdate` при
  read-before-write — НЕ голый read-then-insert.
- Ровно ОДИН владелец retry (queue ИЛИ relay-sweep, не оба — двойной владелец гонится за `attempts`).
- Переходы состояния атомарны: check+update под транзакцией/локом, с валидным исходным состоянием.

## Config-honesty

- Дефолт работает из коробки ИЛИ явно `null` + `throw` при использовании. Анти-паттерн: `?? 'echo'` без
  зарегистрированного драйвера (тест, форсящий `'null'`, это маскирует).

## Форма данных

- Cursor/seek-пагинация по NON-nullable сортируемой колонке (NULL не сравним → нестабильный cursor; тест,
  штампующий timestamp, это прячет).
- Soft-delete там, где важна потеря данных / каскад (не hard `delete()`).
- Поведение держится на ВСЕХ используемых id-стратегиях (uuid7 / ulid / bigint) — никакой uuid-строки в
  bigint-колонку.

## Queue-семантика

- Тесты `ShouldQueue`, зовущие `handle()` напрямую, НЕ покрывают `release()/backoff()/visibility` и
  конкурентных воркеров — пометь «queue-семантика не покрыта».

## Честность тестов

- Любая обходка/форс-конфиг в тесте — флаг `[POSSIBLE-DEFECT]` (>60% попаданий на реальный баг): ищи
  первопричину, не маскируй.

## Связанные

- `php:transactional-outbox-relay`, `laravel-architecture:enum-state-machine`, `php:cursor-pagination-design`, `quality:code-review`.
