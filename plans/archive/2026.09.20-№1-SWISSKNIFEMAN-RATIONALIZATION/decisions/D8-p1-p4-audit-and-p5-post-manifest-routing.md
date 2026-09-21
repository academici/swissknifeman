---
id: D8
date: 2026-09-20
status: accepted
item: P1.1
items: [P1.1, P2.1, P3.1, P4.1, P5.1]
supersedes: [D3]
superseded_by: null
---
# D8 — Seal P1–P4 globally and route P5 after P4 admission

**Actor:** gpt-5.6-sol/high
**Evidence:** RAG:— final whole-plan design-audit findings and current P1–P5 contracts, 2026-09-20

## Решение

P1–P5 по-прежнему детализируются до любого execution. Предварительный
global design audit запечатывает exact batches, order, model/effort, capabilities
и review только для P1–P4, а для P5 — только правило выбора. Exact P5
route/review записываются лишь после terminal GREEN P4 и admission его
nonempty digest-bound `producer-readiness/v1`; до этого P5 остаётся
`dependency-not-ready`.

Правило P5 детерминировано самим admitted GO manifest. Если все его
rows ограничены одним package, internal, non-release и не затрагивают
public/security/provider-parity boundary, P5 получает `Composer 2.5`,
implementation/high и light review. Любой row с release-visible, public-contract,
security, provider-parity или cross-package flag повышает весь P5 batch до
`Grok 4.6`, frontier/high и full review. Неразрешённый или неоднозначный
manifest не получает default route и блокирует P5 admission.

## Почему

P1–P4 уже имеют полные стабильные contracts, поэтому whole-plan audit
может выбрать их exact execution routes. P5 Files, impact и release/provider
flags появляются только в terminal P4 GO manifest; более ранний exact route
фабриковал бы неизвестный scope и review risk.

## Consequences

D3 заменён, но его design-all order, one-audit/one-fix-pass budget и запрет
execution до GREEN re-check сохраняются. Global audit открывает только
P1–P4. P5 получает отдельный post-P4 routing admission; empty GO-set
по-прежнему требует owner D# по D6 и не авторизует P5.

## Global audit seal — 2026-09-20

P1–P4 остаются четырьмя solo batches в dependency order. P1–P3 используют
`frontier/high`: Cursor `Grok 4.6`, Codex `gpt-5.6-sol/high`; P1 не требует
отдельного review, P2/P3 имеют light review. P4 использует
`implementation/high`: Cursor `Composer 2.5`, Codex `gpt-5.6-terra/high`, light review.
Эти provider projections имеют одинаковый semantic class/effort и не меняют
item scope. Правило P5 остаётся без изменений и не материализует route до P4.
