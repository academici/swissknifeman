# P3→P6 early-package finish recon — 2026-08-04

## Environment and baseline

- Target plan paths were clean before design writes; the broader worktree contains unrelated
  owner changes and remains outside this pass.
- `codex doctor --json` reported the expected `gpt-5.6-sol` runtime, approval `Never` and
  unrestricted filesystem sandbox.
- `packages/maind/bin/maind health --cwd --json` returned `connected` with memory round-trip,
  mAInd MCP, code MCP and both provider-trust rows GREEN.
- The worktree-local effective Codex hook dry-run exited 0 but returned `Статус: warning` with
  exactly two `stale-source → update` actions. This is not GREEN and remains owned by P4.6/P4.4;
  no repair was run.
- Initial plan lint was `0 ERROR / 0 WARN`; the phase set contains 39 items and no live skeleton
  marker.

## F1 — promotion evidence would drift under P4

P3.8 currently produces a package-promotion manifest and requires its validator to be GREEN.
P4.1 then adds package files, while P4.2–P4.5 modify the exact `packages/artifex` runtime that
P3.8 promoted. A current-tree equality interpretation of the P3.8 manifest therefore becomes
red as soon as P4 performs its specified work. Later P4/P5/P6 items nevertheless require all
terminal P3 validators to stay GREEN.

This is the same repository-grounded evidence-class defect already repaired at P2→P3 by D81:
an immutable predecessor generation and an evolved current generation need separate carriers.
The required repair is a generation chain, not regeneration of historical P3 evidence.

## F2 — package and root instruction projections lacked generator ownership

The root instruction canon and its generated projections still state:

- exactly five package roots;
- root routing without `swissknifeman artifex`;
- exactly six managed instruction scopes in `packages/harness/lib/harness/instructions.py`.

P3.8 cannot hand-author only `packages/artifex/AGENTS.md`: provider parity requires a shared
Artifex instruction meaning plus generated `CLAUDE.md` and `AGENTS.md`, and the root package-scope
rule requires that guide before package implementation. The first P3.8 substep must therefore
extend the Harness instruction owner, generate both package projections, and restart from the new
package cwd before runtime writes. P6.2 later updates the existing root instruction scope and
regenerates root projections for the sixth package/root route; it does not recreate the Artifex
package scope.

## Reconciled ownership

- P3.8 owns the immutable package-promotion baseline and initial Artifex instruction scope.
- P4.5 owns the current assured package snapshot after all P4 package evolution.
- P5 observes and validates the P4.5 snapshot but does not mutate package/product bytes.
- P6.2 owns the public-integration successor snapshot and root instruction/router projections.
- P6.3 owns the operations/docs/changelog successor snapshot.
- P6.4 independently validates the complete chain and never repairs it.

No frozen P1/P2 carrier, terminal P3.1–P3.4 history, implementation byte, hook deployment or
unrelated worktree path was changed during this recon.

## Verification status

- RAG: 0 external queries; every verdict above is repo-grounded in the named plan files,
  `AGENTS.md`, Harness instruction sources/generator and observed local preflight outputs.
- Unverified → repeat pass: none.
- Workarounds/[POSSIBLE-DEFECT]: none accepted; exit-0 hook warning remains an explicit P4-owned
  defect rather than a substituted GREEN.
