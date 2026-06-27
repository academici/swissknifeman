---
name: domain-modeling
bucket: architect
version: 0.1.0
description: "Active domain-model discipline: challenge terms, stress-test with scenarios, RECORD the glossary (CONTEXT.md — domain language only) and ADRs INLINE as they crystallize (not in batches). Multi-context via CONTEXT-MAP.md. Activate when clarifying terminology/ubiquitous language, recording an architectural decision, or when another skill builds a domain model (esp. fintech: banking APIs, fiscal)."
risk: draft
persona: architect
tags: [domain, ddd, glossary, adr, ubiquitous-language]
requires: []
produces_for: [architecture, api-design, data-schema]
outputs: [CONTEXT.md, ADR]
snippets: [CONTEXT-FORMAT.md, ADR-FORMAT.md]
adapters: [claude, cursor, fable]
disable-model-invocation: false
sha256: ""
---

# Domain Modeling

Actively build and sharpen the project's domain model as you design. This is the *active* discipline — challenging terms, inventing edge-case scenarios, and writing the glossary and decisions down the moment they crystallise. (Merely *reading* `CONTEXT.md` for vocabulary is not this skill — that's a one-line habit any skill can do. This skill is for when you're changing the model, not just consuming it.)

## File structure

Most repos have a single context:

```
/
├── CONTEXT.md
├── docs/
│   └── adr/
│       ├── 0001-event-sourced-orders.md
│       └── 0002-postgres-for-write-model.md
└── src/
```

If a `CONTEXT-MAP.md` exists at the root, the repo has multiple contexts. The map points to where each one lives:

```
/
├── CONTEXT-MAP.md
├── docs/
│   └── adr/                          ← system-wide decisions
├── src/
│   ├── ordering/
│   │   ├── CONTEXT.md
│   │   └── docs/adr/                 ← context-specific decisions
│   └── billing/
│       ├── CONTEXT.md
│       └── docs/adr/
```

Create files lazily — only when you have something to write. If no `CONTEXT.md` exists, create one when the first term is resolved. If no `docs/adr/` exists, create it when the first ADR is needed.

> **Мульти-репо (наш кейс).** Когда термин общий для нескольких проектов экосистемы (например
> «фискальный документ», «ОФД», «кассовый чек» — одинаковы во всех POS-проектах), фиксируй его в
> общем словаре уровня экосистемы (хаб mAInd / Brain), а проектный `CONTEXT.md` ссылается на него,
> добавляя только проект-специфичные уточнения.

## During the session

### Challenge against the glossary

When the user uses a term that conflicts with the existing language in `CONTEXT.md`, call it out immediately. "Your glossary defines 'cancellation' as X, but you seem to mean Y — which is it?"

### Sharpen fuzzy language

When the user uses vague or overloaded terms, propose a precise canonical term. "You're saying 'account' — do you mean the Customer or the User? Those are different things." (Финтех: «операция» / «платёж» / «перевод» / «авторизация» значат разное в SberBusiness, НСПК СБП, Модульбанк — не смешивай.)

### Discuss concrete scenarios

When domain relationships are being discussed, stress-test them with specific scenarios. Invent scenarios that probe edge cases and force the user to be precise about the boundaries between concepts.

### Cross-reference with code

When the user states how something works, check whether the code agrees. If you find a contradiction, surface it: "Your code cancels entire Orders, but you just said partial cancellation is possible — which is right?"

### Update CONTEXT.md inline

When a term is resolved, update `CONTEXT.md` right there. Don't batch these up — capture them as they happen. Use the format in [CONTEXT-FORMAT.md](snippets/CONTEXT-FORMAT.md).

`CONTEXT.md` should be totally devoid of implementation details. Do not treat `CONTEXT.md` as a spec, a scratch pad, or a repository for implementation decisions. It is a glossary and nothing else.

### Offer ADRs sparingly

Only offer to create an ADR when all three are true:

1. **Hard to reverse** — the cost of changing your mind later is meaningful
2. **Surprising without context** — a future reader will wonder "why did they do it this way?"
3. **The result of a real trade-off** — there were genuine alternatives and you picked one for specific reasons

If any of the three is missing, skip the ADR. Use the format in [ADR-FORMAT.md](snippets/ADR-FORMAT.md). (Пример из нашего домена: «почему libfptr10 через dart:ffi, а не через shell» — трудно-обратимо, удивит без контекста, был реальный выбор.)

## Связанные скиллы

- `architect/architecture` — процесс ADR в большем масштабе (архитектурные решения системы); domain-modeling даёт инлайн-формат и язык, architecture — полную дисциплину решений.
- `laravel-architecture/modular-architecture` — применение DDD/bounded-context в Laravel (модульный монолит).
- `general/grill-with-docs` — грилинг-сессия, которая зовёт этот скилл и строит CONTEXT.md/ADR на ходу.
- `architect/api-design`, `architect/data-schema` — потребляют зафиксированный глоссарий (этот скилл `produces_for` их).
