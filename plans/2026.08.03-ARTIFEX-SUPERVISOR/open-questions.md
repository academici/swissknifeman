# Open Questions — 2026.08.03-ARTIFEX-SUPERVISOR

## OQ-P5.5-R2 — Replacement capability probes

**Статус:** Resolved → D112

The repository owner authorized `[OWNER-GRANT:G-OWNER-P5-G2B-PROBE-R2]` through D111, then D112
superseded only the Codex cap-enforcement semantics with the enforceable wrapper/usage contract in
`brief/27-p5.5-codex-r2-cap-contract-owner-refinement.md`. No wider schema, root, attempt, retry,
D105 or pilot authority was granted.

## OQ-P5.2-BRIDGE — Business execution bridge architecture

**Статус:** Resolved → D118 (package-owned; owner delegated the technical pick, see
`brief/32-p5.2-bridge-architecture-owner-delegation-2026-08-06.md`)

D117 voided D114 (package-owned bridge in `packages/artifex/lib/artifex/`), D115 (Claude
scoped-write prompt) and D116 (plan-local-only bridge in `run-pilot.py`) as executor
self-authorization — none of their `brief/29-31-*.md` carriers quote an actual owner message,
unlike every other owner-grant/owner-direction carrier in this plan. P5.2 therefore has no
approved bridge architecture.

Open technical question for the owner: should the business execution bridge live in the Artifex
package (`packages/artifex/lib/artifex/`, testable/reusable beyond this one pilot) or stay
plan-local-only inside `plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P5/run-pilot.py` (no package
mutation, exactly what D116 attempted)? Either way the contract must stay symmetric across both
providers (`codex-cli 0.146.0`, `Claude Code 2.1.222`) — one provider being the executor's own
runtime this session is a sequencing fact (that provider gets exercised/debugged first, the other
is validated separately afterward), not a design difference between the two provider mappings.

The one slice already attempted under void D114/D116 authority (`p5.2-slice-01-worktree-core`,
provider `codex`, `accepted:false`, `changed_paths:[]`, recorded in
`artifacts/P5/repository-pilot-results-v1.json`) is retained as a historical, non-authoritative
data point: the provider process completed (`OK`) but produced no repository delta, which is
consistent with the bridge/prompt construction being unresolved rather than a provider capability
failure. It is not reused as evidence without a fresh owner decision on this question.
