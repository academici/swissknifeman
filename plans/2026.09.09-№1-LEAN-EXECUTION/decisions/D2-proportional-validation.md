---
id: D2
date: 2026-09-09
status: accepted
item: P1.1
items: [P1.1, P1.2, P1.3, P2.1, P2.2, P2.3, P3.1, P3.2, P3.3, P3.4, P4.1, P4.2, P5.1, P5.2, P6.1, P6.2, P6.3, P6.4]
supersedes: []
superseded_by: null
---
# D2 — Use adjacent batches and proportional evidence reuse

**Actor:** design-author/gpt-5.6-sol/high
**Evidence:** RAG:— task-development-philosophy and triggered audit-cost incidents

## Решение

Group producer/consumer items within each phase, run focused checks first, and allow one full audit
for a material phase baseline. A second full audit requires a new broad material change; otherwise
use changed-item plus dependency closure or gate rebind. A third full audit requires owner choice.

## Почему

This preserves adversarial confidence while preventing audit bookkeeping and generated drift from
replaying unchanged product validation.

**Consequences:** item evidence must be digest-bound and reusable; phase close must classify impact.
