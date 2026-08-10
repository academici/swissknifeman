---
id: D66
date: 2026-08-10
status: accepted
item: P0.8
items: [P0.8]
supersedes: []
superseded_by: null
---
## Решение

P0 execution provenance is repaired forward: P0.8 writes one deterministic ledger over the
existing commits/journal/spec timing, validates original Task Contract codes and routes, then
appends bounded reconciliation events for P0.1–P0.4 so generated state views carry the canonical
write-site line and honest deviations. Historical commits, specs and journal rows are never
rewritten; the current reconciler actor is not presented as the historical executor. RAG:—
(repo-grounded: audit F6/F7, `research/11-p0-audit-reopen-design.md`, append-only journal and v2
state generator).

## Почему

A new truthful carrier can restore cold-start auditability; changing old bytes would erase the
very execution defects the audit must preserve as evidence.
