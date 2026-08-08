---
id: D109
date: 2026-08-05
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

D109 supersedes D107 only where D107 waits for an unnamed future grant and leaves P5.2 as the successor consumer. D108 is now the exact grant, and additive item P5.5 is the sole G2B producer executed before P5.2. P5.2/P5.3/P5.4 IDs and all terminal P5.1 bytes remain unchanged because D105 hashes bind those parent IDs; roadmap order is P5.1→P5.5→P5.2→P5.3→P5.4. P5.2–P5.4 must rerun the same P5.5 validator and pin G2B; P5.4 G3 pins G2B; P6 consumes G1→G2→G2B→G3 and protects G2B during G4. D108 does not extend D105 expiry or its exact 14-dispatch ceiling: an expired admission pauses before intent for a new owner carrier/additive item and never permits local P5.1 regeneration. **Consequences:** execution order is intentionally non-numeric inside P5, the phase grows from four to five items, P5.5 changes package bytes so later current-tree checks must use G2B rather than G2, and any provider-version drift reopens P5.5 instead of being patched in a pilot. RAG:— (repo-grounded: terminal D105 parent bindings, `research/35-p5-phase-successor-topology.md`, phases/P5.md and phases/P6.md).

## Почему

A separate producer and one shared downstream pin prevent the third local P5.2 fix from breaking recovery, economics or P6 while preserving immutable trial authority.
