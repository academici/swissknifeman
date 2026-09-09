---
id: D6
date: 2026-09-09
status: accepted
item: P1.2
items: [P1.2, P1.3]
supersedes: []
superseded_by: null
---
# D6 — Compile authoritative batches from Routing

**Actor:** design-author/gpt-5.6-sol/high
**Evidence:** RAG:— (repo-grounded: `research/02-p1-execution-economy.md`;
`packages/skiller/skills/general/plan-protocol/SKILL.md`)

## Решение

`plan.md §3 Routing` remains the single authoritative batch carrier. P1.2 extends the existing
Task compiler/admission path to consume its `Batch` and ordered `Items` fields before journal start;
it does not add a separately handwritten `execution-batches.json` or parse roadmap prose as policy.
RAG:— (repo-grounded: packages/skiller/skills/general/plan-protocol/SKILL.md:153-182;
research/02-p1-execution-economy.md).

## Почему

The separate-carrier alternative made sense when batch existed only in free-form roadmap text, but
current numbered layout-v2 plans already require Batch row-by-row and plan-lint validates adjacency,
phase locality and one Exec mode. A second mutable map would create a new reconciliation loop. The
compiler can expose one normalized batch object and bind its digest to journal/continuity receipts.

## Consequences

P1.2 owns pre-mutation batch admission and receipt integrity; P1.3 consumes the normalized remaining
suffix. Roadmap stays a human execution map and never overrides Routing. Legacy plans without Batch
remain explicit legacy/unsupported for authoritative batching rather than receiving inferred groups.
