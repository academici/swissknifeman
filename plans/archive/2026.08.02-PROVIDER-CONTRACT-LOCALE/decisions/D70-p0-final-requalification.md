---
id: D70
date: 2026-08-14
status: superseded
item: ''
items: [P0.9, P0.10]
supersedes: [D64]
superseded_by: D71
---
## Решение

P0 receives one final bounded forward-repair chain, P0.9→P0.10. P0.9 rebinds the regenerated
classification digest graph only after proving exact set, class, disposition, policy and known-case
semantic identity. P0.10 replaces persisted ten-minute authorization with a two-part boundary:
integrity-checkable stored observation plus a non-persisted live `admit` command executed by the
final P0 audit and again immediately before P1's first mutation. The frozen recovery contract
v1.0.1 and D67 bytes remain unchanged. The next P0 audit is the last planned audit invocation;
reversible in-scope findings are repaired inside that audit root, while only a reproduced owner or
frozen-contract authority boundary may return to design. RAG:— (repo-grounded:
`brief/04-final-p0-requalification-2026-08-14.md`, `phases/P0/P0.md` audit attempt 2 and
`research/13-p0-final-requalification-design.md`)

## Почему

Extending a persisted TTL only moves the race, and accepting the stale digest graph would make
production checkers disagree with the phase verdict. Use-site live admission preserves fail-closed
security semantics without a wall-clock lease spanning separate roots; forward digest rebinding
preserves immutable history without treating stale generated evidence as current.

## Consequences

D64 is superseded only in its “P0.5–P0.8 is the terminal remediation chain” clause; its immutable-
history, P1–P7 and no-external-mutation boundaries remain. D69 remains immutable historical
evidence for the P0.8 close; D70 owns the new current digest binding while preserving D69's
compact-read and anti-displacement design. The plan grows from 34 to 36 items, P1 stays closed until P0.9/P0.10, phase close and one
final GREEN P0 audit complete, and P1 must execute the live admission gate again before mutation.
