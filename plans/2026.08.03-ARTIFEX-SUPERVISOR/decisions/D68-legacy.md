---
id: D68
date: 2026-08-04
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

Terminal P0.2 keeps `brief/01-refinements.md` byte-frozen at the hash in `owner-mandate-input-v1.json`; every later owner refinement is appended in a new `brief/NN-*.md` carrier and is not retroactively inserted into the frozen authority source set. The P2.1 redesign directives move to `brief/02-p2.1-remediation.md`, while `brief/01-refinements.md` is restored exactly. RAG:— (repo-grounded: `artifacts/P0/owner-mandate-input-v1.json`; `artifacts/P0/validate-authority.py`; `brief/02-p2.1-remediation.md`).

## Почему

This preserves both append-only layer-0 provenance and the terminal P0 validation boundary without mutating a frozen contract, losing owner input, or reopening P0/P1.
