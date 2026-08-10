---
id: D78
date: 2026-08-04
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

D78 supersedes D76's claim that admission-aware P5 inputs were complete. P5.1 becomes the sole no-provider producer of catalog-bound business grant requests, owner-approved grants, per-trial dispatch manifests/replay rows/admissions and an immutable index for every P5.2 repository slice, P5.3 recovery/provider-failure dispatch and P5.4 candidate battle wave. Materialization requires a later Decision Log carrier `[OWNER-GRANT:G-OWNER-P5-BUSINESS]` binding exact catalog/request hashes, providers, roots, dispatch count and caps; `G-OWNER-P5.4-SINGLE` remains verdict-only. **Consequences:** P5.1 may pause at a genuine owner gate after proposal hashing, P5.2–P5.4 gain exact indexed inputs and refusal tests, and all D74/P3 smoke grants/admissions become explicitly ineligible business inputs before intent/activity. RAG:— (repo-grounded: `brief/10-post-d76-audit-remediation.md`; latest Audit design F2; `research/23-post-d76-audit-remediation-reconcile.md`; current P5.1–P5.4 specs).

## Почему

Provider dispatch needs independently approved business authority rather than a readiness-smoke ceiling or locally minted JSON; a terminal pre-dispatch producer makes the measured P5 path reachable and auditable.
