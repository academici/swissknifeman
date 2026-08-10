---
id: D67
date: 2026-08-04
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

P2.1 supersedes D32's two-source acquisition wording with the existing three-source process contract: S1 `plan-lint --json` owns the complete parsed plan/item model and all 16 fields; S2 `task.task_contract build` owns route, acceptance, evidence and content hash; S3 Harness dry-run independently cross-checks order/status/route and supplies exact `Exec`. A manual route's `EXEC-NOT-PLAN-EXEC` is expected Harness evidence, never Artifex authority. Strict S1 `Files` projection and S1/S2 read/validation/deliverables equality close the missing scope bundle without package/API changes, Markdown parsing or P1 reopen. **Consequences:** P2.1 adds one bounded subprocess and three-way drift tests; any source-shape disagreement refuses before candidate writes, while downstream outputs/routes remain unchanged. RAG:— (repo-grounded: `findings/12-p2.1-process-projection-recon-2026-08-04.md`; `research/14-p2.1-source-reconciliation.md`; active `driver-plan-protocol-v2` §2/§4.5).

## Почему

The original attempt omitted an already-owned source and misread a driver refusal as a compiler refusal; reusing the existing owner projection is narrower and safer than extending Task/Harness or weakening the frozen slice contract.
