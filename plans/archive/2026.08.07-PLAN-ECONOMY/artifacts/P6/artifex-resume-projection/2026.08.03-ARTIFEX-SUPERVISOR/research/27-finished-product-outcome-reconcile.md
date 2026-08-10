# Finished-product and early-package reconciliation — 2026-08-04

## Defect

The owner-facing meaning of “complete the Artifex plan” diverged from two executable properties.
First, D19/D56–D61, P5.4 and P6 permitted a successful `NO-GO → roadmap-only` branch with no
live runtime. Second, the first owner-outcome correction still delayed `packages/artifex` until
P6, so P4 assurance and P5 pilots would certify plan-local code and only afterward migrate it into
the product path. That could not guarantee that the delivered package was the code actually tested.

## Reconciled product chain

There is now one successful chain:

`P3 remediation GREEN → P3.8 standalone packages/artifex → P4 assures that package → P5 pilots
that package → P5 GO (release-ready) → P6 umbrella/install/doctor/ops/docs → cold GREEN audit`.

P3.8 consumes the finite D86 package grant and establishes the sole live runtime owner, standalone
CLI, package tests/validation and a prototype→package provenance manifest. Plan-local P0–P3 bytes
remain immutable evidence and cannot be imported by the package. P4 Files and tests target
`packages/artifex`; P5 calls `packages/artifex/bin/artifex`. P6 is therefore integration and
operations work, not another source migration.

P5 still computes the same evidence, thresholds and frozen `GO|NO-GO` values:

- `GO` means release-ready and allows P6 to start;
- `NO-GO` records every failed floor and keeps P5.4 non-terminal until a separately specified
  forward fix and a fresh five-wave adjudication are GREEN;
- unknown, single-provider, synthetic, N<5 or otherwise ineligible evidence cannot be terminalized
  as success or waived into release readiness.

A later owner cancellation is outside the success state and must be recorded as cancellation, not
as successful plan completion.

## Ownership and authority

The runtime owns durable store, scheduler, authority and worker lifecycle, so its home is fixed to
`packages/artifex/`. The owner supplied two independent finite grants:

- D86 package: `packages/artifex/**`, standalone launcher/tests/docs/config and exact package-owned
  projections; consumed for creation by P3.8 and revalidated later;
- D87 router: additive `swissknifeman artifex` and only root installer/doctor/generated/docs paths
  enumerated by P6.1; consumed by P6.1/P6.2.

P6.1 freezes only the remaining root/public/generator scope around the existing package. P6.2 adds
umbrella and installation lifecycle surfaces without relocating runtime modules. P6.3 completes
compatibility, update/doctor/status, default-off onboarding, state migration/rollback, docs and
changelog. P6.4 independently audits the entire finished product.

## Preserved boundaries

The correction does not mutate frozen P1/P2 carriers, terminal P3.1–P3.4 history, P4/P5 evidence
thresholds, provider parity, worktree isolation, stdlib-only runtime, generated-artifact ownership,
default-off rollout, privacy boundaries or release authority. D88 changes only the timing of the
package boundary, the P4/P5 runtime consumer paths and P6's remaining responsibilities.

## Required design consequence

Because P3–P6 phase contracts changed after the earlier `finish` and design audit, execution must
not jump directly to P3.5. The plan requires a new cross-phase `finish`, followed by a cold
`task:plan-audit ... design`; only literal GREEN restores the P3.5 handoff.

RAG:— (owner-grounded: `brief/14-owner-finished-product-guarantee.md`; repo-grounded: D85–D88,
current `phases/P3.md`–`phases/P6.md`, package/single-SSOT/CLI/install canons).
