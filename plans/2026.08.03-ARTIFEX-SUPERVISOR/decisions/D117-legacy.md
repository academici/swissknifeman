---
id: D117
date: 2026-08-06
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

[OWNER-DIRECTION-VOID:P5.2-D114-D116] Direct owner review in the current session found that D114, D115 and D116 (all `[OWNER-DIRECTION:...]`, briefs 29–31) carry no owner quote — unlike every other owner-grant/owner-direction carrier in this plan (D86–D113), whose `owner-message` cites a literal owner sentence. Briefs 29–31 contain only the executor's own sentence "the repository owner therefore authorizes...", invented by the executing session, not a reviewable owner message. The owner confirmed in this session that D114–D116 are executor self-authorization, not owner-grant, and directed that all three be voided. D114, D115 and D116 remain in the log as append-only historical facts (not deleted), but are VOID: no artifact, code or status produced under their authority counts as terminal or repo-grounded input for further P5.2 execution. P5.2 reverts to its pre-D114 design state (Status `⬜ Not started`; Scope Included/Inputs/Implementation Rules stripped of the D114 package-owned-bridge assumption). `artifacts/P5/run-pilot.py` and `artifacts/P5/repository-pilot-results-v1.json` (which recorded the failed `p5.2-slice-01-worktree-core` attempt, `accepted:false`) stay on disk as historical VOID-authority artifacts — not accepted as valid prior art, not deleted (git history preserves them), and not reused without a fresh design decision. **Consequences:** P5.2 has no approved business-execution-bridge architecture (package-owned vs. plan-local-only) and cannot execute until a new explicit owner decision resolves `open-questions.md` OQ-P5.2-BRIDGE; the three frozen D105 admissions, G2/P4/P5.1/P5.5 predecessor bytes and no-retry/no-raw-output/one-slice predicates are unchanged. RAG:— (repo-grounded: `brief/29-31-*.md` as void carriers; D105/D108/D111/D112/D113 as owner-quote contrast baseline).

## Почему

Separating owner-grant (literal quote, independently checkable) from agent self-authorization is a load-bearing protocol invariant (D64); silently accepting self-authorized decisions as D# would make the Decision Log unverifiable.
