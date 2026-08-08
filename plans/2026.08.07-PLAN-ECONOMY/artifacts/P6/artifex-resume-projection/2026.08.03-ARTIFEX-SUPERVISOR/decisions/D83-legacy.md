---
id: D83
date: 2026-08-04
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

P3 remediation is a sequential three-item chain: P3.5 binds indexed admission→exact adapter→bounded normalized worker activity; P3.6 replaces the synthetic writer with the same-path real preflight/probe and implements strict historical-P2/current-P3 hash validation; P3.7 repairs the Task invariant regression and reruns the closure fan-in. No workflow is created because each item consumes the previous item's deliverables. RAG:— (repo-grounded: `research/26-p3-audit-reopen-design.md`; current runtime/evidence code).

## Почему

One runtime owner, one evidence owner and one final regression/gate owner prevent another mixed implementation/bookkeeping close and keep provider-free P2 seams intact.
