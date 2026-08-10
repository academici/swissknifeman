---
id: D89
date: 2026-08-04
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

D89 supersedes D88 only where an unqualified P3.8 promotion validator could be treated as current-tree equality after P4 evolves the package. G1 `package-promotion-manifest-v1.json` is immutable P3.8 baseline evidence: it validates current bytes at P3.8 close and later recomputes those bytes from the terminal P3.8 item commit. P4.5 becomes the sole G2 current-package snapshot through P5 and the P6.1 pre-write gate; P6.2/G4 and P6.3/G5 are explicit successor manifests. P5 is observational and cannot mutate G2; P6.2 proves the protected runtime subset remains G2-identical while changing only allowlisted integration rows. **Consequences:** later phases must not regenerate or current-root replay historical G1/G2 carriers after an authorized successor begins; each successor pins its predecessor plus a closed current file set, and P6.4 validates the whole chain. RAG:— (repo-grounded: `findings/P3-P6-early-package-finish-recon-2026-08-04.md`; `research/28-early-package-cross-phase-finish.md`; D81 predecessor/current precedent).

## Почему

P4 is required to modify the package that P3.8 created; without generation ownership the first lawful assurance fix would falsely invalidate its own predecessor gate.
