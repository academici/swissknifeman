# P7 RED-audit recovery design

## Inputs and boundary

This synthesis consumes `artifacts/P7-final-release-audit.md`,
`findings/P7-release-verdict.md`, `findings/P7-design-preflight-2026-08-17.md`, D88, D89 and the
current P7 specifications/states. It introduces no release exception and treats the old P7.4 RED,
its reviewer capsule and all external blocker identities as append-only evidence.

## Finding ownership

| Audit finding | Classification | Owner and forward action |
|:--|:--|:--|
| F1 required fleet/P5 blockers | external authority/state | Preserve under D88/D89; a later separately authorized rollout plan may change them. P7 does not. |
| F2 missing frozen verifier CLI | local package-candidate defect | P7.5 implements and negatively tests the exact acceptance/crosswalk/release-tree interface. |
| F3 no committed candidate | integration boundary in a dirty shared tree | P7.5 seals an exact candidate/foreign path partition; P7.6 commits only candidate paths and proves their HEAD equality while foreign bytes remain unchanged. |
| F4 plan lint red | deterministic bookkeeping/read-contract defect | Design-root appends the standalone P7.3 write-site carrier and bounds P7.4 reads; P7.5/P7.6 recheck. |
| F5 live efficacy deferred | external provider capability/authority | Preserve `not-live-verified`/diagnostic-only state under D88; no package or release claim. |
| F6 cold-start carrier drift | generated/navigation defect | Design-root regenerates decisions/status/index/bundles and rewrites roadmap/handoff through their owners. |

F2 and F3 are not independent release features: both are required to produce one machine-verifiable,
committed package candidate. They form the adjacent `p7-red-recovery` batch P7.5–P7.6. F4/F6 do
not justify a product item because their owners are deterministic plan carriers and their repair is
bounded to one regeneration plus gate rerun. F1/F5 would require new authority and external state,
so adding fake P7 implementation items would create an impossible loop.

## Candidate and audit continuation

P7.5 derives an exact candidate path set only from declared P7.1–P7.3 Files/deliverables, D87–D90
records and the bounded recovery Files. Every dirty path is classified exactly once as candidate or
foreign; mixed/unknown paths fail closed. P7.6 verifies preimage hashes, stages only the sealed
candidate set, creates the normal scope/bookkeeping commits, and proves candidate paths equal HEAD
while the foreign-set digest is unchanged. A dirty unrelated worktree is visible but cannot be
silently staged or misreported as candidate dirtiness.

After P7.6 is terminal, P7.4 remains historically RED and is not reopened. Successor P7.7 binds
the new P7.5/P7.6 evidence and performs one delta audit of F2–F6. This monotonic item ordering keeps
future producer outputs out of P7.4's read graph. Unchanged P7.4 GREEN receipts are reused; F1/F5
are rechecked by exact identity rather than by a second fleet/provider execution. The resulting
verdict still cannot authorize release while D89's blocker set is non-empty.

## Validation economy and stop conditions

- P7.5 owns verifier self-tests, exact argv compatibility and candidate-set negatives.
- P7.6 owns candidate/foreign partition, scoped commits and candidate-tree equality.
- P7.7 owns independent recomputation of the repaired interfaces, current D# exact set,
  candidate anchor and plan navigation freshness.
- A second whole-plan/full-suite audit is forbidden; only checks invalidated by P7.5/P7.6 and live
  plan views rerun. The prior green package/provider-doc receipts remain reusable when their input
  hashes are unchanged.
- Missing authority, changed external blocker identity, candidate/foreign overlap, verifier
  mismatch or an unclean candidate path stops the affected item with exact evidence. It never
  widens staging, retries provider access or weakens D88/D89.

RAG:— (repo-grounded: P7.4 audit evidence, plan-protocol validation economy, D88 and D89).
