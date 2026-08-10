---
id: D146
date: 2026-08-09
status: accepted
item: P5
items: [P5, P5.4, P5.5]
supersedes: []
superseded_by: null
---

## Решение

**Повторно реоткрыть P5 после RED-аудита (заход 2) и исправить её теми же владельцами
P5.4 → P5.5.** P5.4 вводит один semantic-outcome reducer для state/pending/owner/join consumers,
считает 2–5 substantive options отдельно от mandatory `escalate`/`reject` и делает exact
request/resolve retry идемпотентным; continuation публикуется только после свежести journal,
item/status и owner-gate views. P5.5 расширяет executable acceptance producer/error-сценариями и
повторяет detached item-tree proof. RAG:— (repo-grounded: `phases/P5/P5.md` Audit P5, заход 2;
`research/23-p5-audit-reopen-round2-2026-08-09.md`).

## Почему

D144 правильно зафиксировал frozen semantics и owners, но реализация разошлась между consumer APIs,
не отделила reserved options от substantive bounds и оставила append→projection failure без exact
retry. Новый item или расфриз contract v1 лечил бы не owning layer. Append-only carrier исключает
rollback как честную общую транзакцию; idempotent repair сохраняет provenance и сходится после
transient failure.

## Consequences

**Consequences:** версия плана поднимается до 0.30.0; P5, P5.4 и P5.5 возвращаются в `🟡`, старый
Phase Handoff инвалидируется, root handoff указывает на P5.4. Цена — test-only RED commit до fix,
повторные item commits/closure/audit и более широкая acceptance matrix. D144/D145 остаются в силе;
frozen `decision-request` v1/`authority-frame` v1, owner hash D143, P4 contracts/packet/cap,
reader-contract paths, P5.1–P5.3, P6 и `packages/artifex` не меняются.
