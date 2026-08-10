---
id: D52
date: 2026-08-03
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

P6.1 uses its own durable append-only `artifacts/P6/brain-transaction-log.jsonl`: stable Brain/action/boundary IDs, frozen plan/approval/source identities, exact pre/post identities and a canonical hash chain are appended, flushed, `fsync`'d, reopened and verified before and after every public Skiller/Harness/mAInd/P3 write or readback boundary. `resume` first runs deterministic `reconcile`: exact approved postimage gets fresh readback then acceptance, exact preimage is recorded rolled back, a recognized partial/failed postimage triggers whole-Brain rollback, and any third state, torn chain, missing backup or source drift refuses. Result JSON is derived only from a terminal journal; crash injection covers every append and public CLI boundary. RAG:— (repo-grounded: audit F23, D47's measured failure class and P6.1 whole-project rollback promise).

## Почему

Extends durable intent across the live Brain crash window; the cost is a second transaction-specific WAL and explicit resume/reconcile/rollback evidence rather than relying on a post-operation result file.
