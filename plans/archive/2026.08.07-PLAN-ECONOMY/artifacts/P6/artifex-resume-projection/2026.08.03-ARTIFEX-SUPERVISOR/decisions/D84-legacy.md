---
id: D84
date: 2026-08-04
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

Historical P3.4 prose/commit is not rewritten to pretend `d1362247` contained later design carriers. The P3.5–P3.7 specifications carry exhaustive Required Reads/Files and must be committed cleanly before P3.5 mutation; the append-only Update Log records the missing P3.1–P3.4 commit map. RAG:— (repo-grounded: audit F4/F6; `findings/P3-audit-reopen-recon-2026-08-04.md`; `research/26-p3-audit-reopen-design.md`).

## Почему

Provenance is repaired forward with a checkable precondition while the historical defect remains visible instead of being erased by post-hoc specification edits.
