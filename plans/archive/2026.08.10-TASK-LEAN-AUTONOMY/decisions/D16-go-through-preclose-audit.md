---
id: D16
date: 2026-08-11
status: superseded
item: P1.2
items: [P1.2]
supersedes: [D8]
superseded_by: D17
actor: plan-designer
model: gpt-5.6-sol/high (semantic plan-design route; actual selector/effort not independently attested)
evidence: RAG:— decisions/D14-preclose-audit-and-item-reconciliation.md + phases/P1/P1.2.md
---

## Решение

P1.2 GO переводит P1 в terminal-item candidate и направляет Next в
`audit-phase: task:plan-audit 2026.08.10-TASK-LEAN-AUTONOMY P1`. Только fresh GREEN по
candidate fingerprint разрешает `task:plan-close 2026.08.10-TASK-LEAN-AUTONOMY P1`.
ADJUST остаётся nonterminal переходом D8: один durable DecisionRequest и structural waiting
на exact owning continuation.

Это решение supersedes D8 только в GO-ветке прямого phase close; owner-approved D14 является
authoritative lifecycle boundary.

## Consequences

GO покупает один обязательный fresh audit кандидата до close, но исключает прежний
`close → audit RED → reopen/repair → close` цикл.

## Почему

D8 был принят до D14 и оставил normal Next `close P1`, который теперь нарушает pre-close audit
gate. Append-only D16 синхронизирует remaining P1.2 spec, roadmap и handoff с D14 без
переписывания исторического решения. RAG:— (repo-grounded:
`decisions/D8-go-adjust-transition.md`, `decisions/D14-preclose-audit-and-item-reconciliation.md`,
`findings/07-preclose-audit-lifecycle.md`).
