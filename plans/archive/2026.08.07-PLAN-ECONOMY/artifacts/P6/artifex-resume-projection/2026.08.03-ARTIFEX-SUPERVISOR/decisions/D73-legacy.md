---
id: D73
date: 2026-08-04
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

D73 supersedes D72 only where it claimed that the read-set repair made P3.4 executable. **Consequences:** P3.4 remains `🔴 Blocked` and P3/P4–P6 cannot claim a live provider path until the owner selects either (a) a scoped successor-contract redesign reopening P1.2/P1.3 and P2.4/P2.5 for one frozen manifest→dispatch/authority/budget carrier, or (b) a scope reduction removing live dispatch and reconciling downstream claims. P1.2 omits P2 scheduler's authority and complete numeric budget input; the frozen P1.3 mandate excludes P3 provider/routes; and P2 CLI has no dispatch surface. Implementation-local defaults, bypasses, or contract edits are forbidden. RAG:— (repo-grounded: `findings/P3.4-bridge-contract-conflict-2026-08-04.md`; `research/19-p3.4-bridge-feasibility.md`; frozen P1.2/P1.3 contracts and terminal P2 code).

## Почему

The complete read chain exposed a genuine frozen-carrier conflict, so continuing P3.4 would silently mint a fourth contract or widen authority; either coherent repair changes product/frozen-contract scope and needs the owner's explicit choice.
