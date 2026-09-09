---
id: D8
date: 2026-09-09
status: accepted
item: P3.1
items: [P3.1, P3.2, P3.3, P3.4]
supersedes: []
superseded_by: null
---
# D8 — Use one phase-assurance and evidence lineage

**Actor:** design-author/gpt-5.6-sol/high
**Evidence:** RAG:— `research/04-p3-proportional-assurance.md` and preserved P0/P1/P5/P6/P9/P10/P11 incidents

## Решение

Use one runtime-built phase candidate lineage across audit admission, impact classification,
validation reuse and close. `Phase Assurance | v1` owns the author's semantic impact declaration;
`audit-impact/v1` owns field-level change classification; item terminal events own
`validation-receipt/v2`; and one derived spec→product→closure graph owns anchors and dependency
closure. P3.2 must consume the P1.2/D6 normalized Routing compiler output rather than add a parser.
Unknown impact gathers evidence or requests owner review and never implicitly authorizes `full`.

## Почему

Historical `Review`, item count and aggregate hash mismatch cannot distinguish first-audit risk,
bookkeeping rebind, bounded material delta and broad change. One lineage keeps those decisions
reproducible without a parallel handwritten risk map, while separated owners prevent assurance,
receipts and anchor topology from becoming one oversized mutable carrier.

## Consequences

New plans use the structured assurance block; legacy plans take one conservative recoverable
baseline path. Deterministic receipts are reusable only on exact identity; live checks remain live.
One full baseline is normal, a second requires closed material justification, and a third requires
durable owner authority. Schemas and writer enforcement are forward-only; historical bytes remain
readable.
