# Design-audit RED remediation — owning-root synthesis

Sources: owner refinement in `brief/01-refinements.md`; findings F4.1–F4.4 in
`findings/13-design-audit-2026-08-07.md`; session-continuity synthesis in
`research/17-session-continuity-adaptive-review-2026-08-08.md`; decisions D123–D125.

## 1. Owner outcome

The owner delegated the technical choice and requires the debt-free outcome. Accepting the plan as
`🟠` is therefore not a valid branch. The remediation stays in the current owning root and does not
spend a fifth independent audit: D123 authorized one whole-plan audit and explicitly routed its
result back to the owning run.

## 2. Machine canary contract

P6.7 must predeclare `session_canary` inside `acceptance-protocol-v1.manifest.json`, independently
from the D2 two-arm measurement. It has one production-path command, required result keys, and four
closed branch ids:

| Branch | root_restarts | reviewer_calls | root_identity | root_carrier_rereads | Extra gate |
|:--|--:|--:|:--|--:|:--|
| `first-local` | 0 | 0 | `same` | 0 | deterministic Validation rerun |
| `same-fingerprint-repeat` | 0 | 1 | `same` | 0 | reviewer actor/route differs from root |
| `risk-first` | 0 | 1 | `same` | 0 | reviewer actor/route differs from root |
| `hard-boundary` | 1 | 0 | `changed` | 1 | exact reason from D125 |

`root_carrier_rereads` counts full root-path rereads, not the bounded reviewer capsule. Bytes/tokens
are recorded as non-negative observations and remain separate from the D2 read budget. The manifest
contains expectations only; no observed value is legal before P6.8.

P6.8 produces `artifacts/P6/session-canary-results.json`. Its Validation compares every observed
branch against the frozen manifest field by field, requires root actor/route and reviewer
actor/route provenance (reviewer actor differs on both isolated-review branches), rejects
missing/extra branches, rejects aggregation, and checks the exact D125 boundary reason. The general
two-arm acceptance cannot substitute for this comparator.

## 3. Roadmap and DoR reconciliation

- B1/B2 are sequential manual item execution, not workflows or plan-level steps; under the current
  provider-neutral enum their launch context is `same-session — item`.
- P1/P4/P5/P6 DoR inventories explicitly name D123–D126 and findings/19 R23–R25 where the new
  manager/specialist, selective-review, continuation and context-policy facts are load-bearing.
- `roadmap.md` is anchored to plan v0.24.0 and D126; the duplicate module pair in its coupling list is
  removed while rebuilding the map.

## 4. Closure and continuation

F4.1–F4.4 are closed by D126 and the concrete phase/roadmap edits above. No fifth audit is scheduled.
The next executable item remains `2026.08.07-PLAN-ECONOMY P1.5`, whose owner gate freezes the reader
contracts before P2 starts.
