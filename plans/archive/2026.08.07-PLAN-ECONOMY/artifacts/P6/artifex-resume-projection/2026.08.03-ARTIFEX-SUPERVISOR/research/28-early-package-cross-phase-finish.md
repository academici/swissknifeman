# Early-package cross-phase finish — 2026-08-04

## Inputs and method

This synthesis consumes `brief/15-early-package-cross-phase-finish.md`,
`brief/14-owner-finished-product-guarantee.md`,
`findings/P3-P6-early-package-finish-recon-2026-08-04.md`,
`research/27-finished-product-outcome-reconcile.md`, D85–D88 and the detailed P3.8/P4/P5/P6
specifications. The reconcile treats code/history as read-only and checks producer order,
generation ownership, package/provider instruction parity, runtime consumers and final public
surfaces.

## Generation chain

| Generation | Producer | Meaning | Later validation |
|:--|:--|:--|:--|
| G0 | terminal P3.7 | repaired plan-local predecessor | immutable provenance only |
| G1 | P3.8 | standalone `packages/artifex`, package guide parity, CLI/tests and promotion manifest | current-tree at P3.8 close; historical Git/blob recomputation after P4 starts |
| G2 | P4.5 | assured current package after P4.1–P4.5 evolution | current equality through P5 and P6.1 pre-write |
| G3 | P5.4 | empirical verdict over exact G2 bytes | observational only; P5 cannot mutate G2 |
| G4 | P6.2 | umbrella/install/instruction integration successor | protected runtime subset remains G2-identical; declared integration paths become G4 |
| G5 | P6.3 | operations/compatibility/rollback/docs/changelog successor | current finished-product input to P6.4 |

An older generation is never regenerated against evolved current bytes and never presented as
current. Every successor pins its predecessor manifest/hash and independently hashes its own
closed file set. P6.4 validates the whole chain from raw bytes/commits plus positive controls.
This closes the same predecessor/current ambiguity that D81 already forbids at P2→P3.

## Package and instruction ownership

P3.8 is intentionally two-stage inside one item:

1. Under Harness package rules, extend the instruction catalog/targets/fragments/tests for one
   additive `artifex` scope and generate both `packages/artifex/CLAUDE.md` and
   `packages/artifex/AGENTS.md` through `harness instructions`; never hand-edit projections.
2. Restart with `codex -C packages/artifex`, read the generated package guide, and only then move
   the GREEN runtime into the standalone package.

P6.2 later updates the already-existing root instruction scope so its repository layout,
ecosystem identity and root router include Artifex. It uses the same Harness owner/generator and
regenerates root `CLAUDE.md`/`AGENTS.md` plus the provider-artifact lock. This is structural public
integration, not runtime migration. P6.3 owns operational behavior and docs/changelog; if a path
is shared with P6.2, P6.1 assigns the exact row and P6.3 consumes the terminal G4 manifest rather
than silently widening Files.

## Producer/consumer verdict

The executable order remains sequential and contains 39 items:

`P3.5 → P3.6 → P3.7 → P3.8/G1 → P4.1 → P4.2 → P4.3 → P4.6 → P4.4 → P4.5/G2 → P5.1 → P5.2 → P5.3 → P5.4/G3 → P6.1 → P6.2/G4 → P6.3/G5 → P6.4`.

P4 and P5 execute package paths only. P6 has no runtime-source migration: P6.2 may change only
allowlisted launcher/config/public integration rows while proving the protected runtime modules
remain G2-identical; P6.3 may change only the allowlisted operations/docs rows. A failed P5 floor,
missing generator provenance, generation drift or RED P6 audit leaves the owning item and plan
non-terminal with a forward remediation target.

## DoR sweep

- Design budget: satisfied (`8/8` plus recorded finish/remediation passes).
- Skeleton markers: none live.
- Scope/anti-scope: present for P3.8/P4/P5/P6 and unchanged for frozen history.
- Routing: all 39 items covered postrow; all remain legal manual routes.
- Orchestration: none required; the active items form dependency chains rather than independent
  deterministic fan-out.
- Required reads: every future-only path in P4–P6 has an earlier named producer; package and root
  instruction generators are now explicit.
- Owner gates: D86 package, D87 router and the later hash-bound P5 business grant remain finite;
  no tag/push/publish/release or rollout authority was added.
- Open questions and clarification markers: none live.

The plan is ready for a cold independent design audit; this finish does not authorize execution
without literal audit GREEN.

## Verification status

- RAG: 0 external queries; the finish verdict uses repository code, canons, plan files and local
  preflight evidence only.
- Unverified → repeat pass: none.
- Workarounds/[POSSIBLE-DEFECT]: none. The known hook warning remains assigned to P4.6/P4.4 and
  was not repaired or waived in design.
