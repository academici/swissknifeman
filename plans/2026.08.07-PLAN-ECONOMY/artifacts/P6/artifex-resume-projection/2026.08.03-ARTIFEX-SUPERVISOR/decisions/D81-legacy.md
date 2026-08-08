---
id: D81
date: 2026-08-04
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

P2's `prototype-manifest-v1.json` and validator remain byte-stable historical evidence for item commit `6c2c2ef3`; they are not regenerated and are no longer invoked as a current-tree equality gate after a declared P3 successor edits P2-owned files. P3.4's additive `adapter-manifest-v1.json` becomes the sole successor snapshot: it pins the P2 manifest path/SHA-256 `bbd19ef8dab464e33b58be07519173127103528dcd321449557a4c771db312a1`/commit, recomputes every P2 row from that Git snapshot, and separately pins/recomputes current P3 implementation, tests, admissions, parity and minimized readiness evidence. **Consequences:** P3.4 validation stops claiming the terminal P2 validator is green on evolved bytes; its P3 validator must prove both generations, and any missing Git anchor, changed P2 carrier or current P3 drift fails closed. RAG:— (repo-grounded: `findings/P3.4-successor-manifest-conflict-2026-08-04.md`; `research/25-p3.4-successor-manifest-design.md`; terminal P2.6 commit and current P3.4 Files).

## Почему

A predecessor snapshot and a successor snapshot describe different generations; anchoring both preserves provenance and allows lawful additive evolution without rewriting history or accepting a known-red check.
