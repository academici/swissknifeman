---
id: D64
date: 2026-08-10
status: superseded
item: ''
items: [P0.5, P0.6, P0.7, P0.8]
supersedes: [D55, D62]
superseded_by: D70
---
## Решение

The independent P0 audit RED reopens P0 through the additive sequential chain
P0.5→P0.6→P0.7→P0.8. P0.1–P0.4 specs, commits and journal history remain immutable; P1–P7
semantics and phase topology remain unchanged. The work stays in this master plan and does not
duplicate `2026.08.03-ARTIFEX-SUPERVISOR`. This decision replaces only D55/D62's now-obsolete
30-item/next-step clauses: the plan has 34 items, the next action is P0.5, and no ninth whole-plan
design audit is introduced. RAG:— (repo-grounded: `phases/P0/P0.md` audit F1–F7,
`brief/03-p0-audit-reopen-2026-08-10.md`, `research/11-p0-audit-reopen-design.md`).

## Почему

Forward remediation makes the audited product/evidence failures falsifiable without rewriting
terminal history or widening into later phases, fleet mutation or supervisor runtime.

## Consequences

The execution map grows by four sequential P0 items and P1 stays closed until P0 re-closes and
passes a second independent phase audit. The plan pays for new bundles, state/status/roadmap views,
another P0 close and audit pass; it preserves D55's one-control-tower boundary, D62's accepted P1–P7
design and audit-cap decision, and all external no-write/owner gates.
