# Audit 8 authority/generator reconciliation

## Sources

- `brief/16-audit8-owner-carriers-and-execution.md`
- `findings/P3-P6-audit8-owner-generator-recon-2026-08-04.md`
- `plan.md` → audit pass 8 F1–F4
- `phases/P3.md` P3.7/P3.8 and `phases/P6.md` P6.1/P6.2

## Synthesis

The repair has four separate contracts and must not collapse them into one broad permission.

1. D86 continues to authorize the finished `packages/artifex/**` result. A new exact grant owns
   only the Harness Artifex instruction sources/tests/shared lock that P3.8 must change before the
   package projections can lawfully exist.
2. D87 continues to authorize the root router and generated root outputs. A second exact grant
   owns only the Harness root instruction sources/tests/shared lock that P6.2 changes after P6.1
   freezes the integration rows.
3. Harness generation is a three-gate transaction: no-write plan with exact action-set check →
   apply with exact ordered generated targets → clean check. The lock is an implicit deterministic
   output of the apply and remains explicitly owner-scoped.
4. P3.7 does not become a co-owner of P3.6 evidence. Fresh side-effecting probe output is temporary;
   the committed P3.6 evidence and validator inputs are read-only and must remain clean.

RAG:— (owner/repo-grounded: the two source files above and the Harness instruction implementation).

## Producer → consumer result

| Producer | Carrier | Consumer | Refusal boundary |
|:--|:--|:--|:--|
| Owner/D91 | exact P3.8 Harness source/test/lock marker | P3.8 stage 1 | missing/revoked/path mismatch → P3.8 stays open |
| P3.8 stage 1 | exact plan actions, applied package guides, next lock, clean check, atomic stage commit | P3.8 package-cwd continuation | no full restart or dirty stage paths → no package-runtime write |
| P3.6 | committed provider smoke/manifest/validators | P3.7 read-only fan-in | any before/after diff → P3.7 stays open |
| P3.7 temp probe | disposable provider smoke only | P3.7 process smoke | any write outside temp → P3.7 stays open |
| Owner/D92 | exact P6.2 Harness root source/test/lock marker | P6.1 freeze and P6.2 | missing/revoked/path mismatch → P6.1/P6.2 stays open |
| P6.2 generator stage | exact plan actions, applied root guides, next lock, clean check | G4 validator/P6.3 | action-set, parity or provenance mismatch → P6.2 stays open |

## Cross-phase consequences

- G1→G5 order is unchanged. The shared lock is versioned by P3.8 and later P6.2, never replayed
  as if the earlier current generation remained current.
- P3.8 and P6.2 remain implementation/high manual items; no new item or orchestration carrier is
  needed.
- P3.7 keeps its single-file implementation scope. Its validation is executable without taking
  ownership of P3.6 outputs.
- Frozen P1/P2, terminal P3.1–P3.4 and all current item statuses remain unchanged.

RAG:— (repo-grounded: D89 generation policy, plan Routing and plan-protocol worktree ownership).

## DoR verdict

With D91–D94 and synchronized P3/P6/roadmap/handoff carriers, all four audit blockers have exact
authority, commands, inputs, outputs and refusal behavior. The next legal step is a new cold design
audit, not item execution.
