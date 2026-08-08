---
id: D98
date: 2026-08-05
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

The repository owner closes the pre-exec design-audit loop after ten historical passes: audit-10 F1/F2 are remediated in current carriers, deterministic lint/conflict/citation/Task Contract/DoR/generation gates are the execution admission proof, no audit 11 is authorized, and the current Next is `2026.08.03-ARTIFEX-SUPERVISOR P3.5`. D98 supersedes D63/D75/D76/D85 only where their live successor wording requires another design audit before execution; all other decisions, historical audit blocks, frozen P1/P2, terminal P3.1–P3.4 history, item contracts/statuses, protected authority and G1→G5 topology remain binding. Every later audit checkpoint is capped at two total passes and two occurrences of the same finding, matching `packages/task/lib/task/review_policy.py`; after the second non-GREEN there is no automatic third audit, only bounded forward remediation plus deterministic validation, unless a genuine safety/authority/frozen-contract/acceptance gate requires the owner. **Consequences:** the owner accepts the absence of an additional independent post-remediation design attestation; D98 does not weaken item validation, security, protected grants, P6.4 finished-product acceptance or release authority, and it forbids audit-of-audit recursion without a new explicit owner decision. RAG:— (direct owner decision; repo-grounded: `brief/18-owner-close-design-audit-loop.md`; `packages/task/lib/task/review_policy.py`).

## Почему

Ten passes demonstrated that an uncapped re-audit handoff can perpetually manufacture a new pre-exec gate; a finite owner-approved stop rule restores progress while retaining deterministic and protected execution gates.
