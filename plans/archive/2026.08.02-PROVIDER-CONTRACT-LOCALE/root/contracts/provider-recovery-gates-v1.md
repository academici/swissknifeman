# Provider recovery gates

**Version:** v1.0.1

**Status:** frozen

**Approval Owner:** repository owner

**Approval:** D67, 2026-08-10

## Purpose

This compatible corrective successor makes recovery admission machine-verifiable without
changing the predecessor G01–G11 obligations or granting mutation authority. It replaces the
cyclic future-only verifier topology with one phase-local independent audit before each
consumer phase starts. P7.4 remains an additional final release audit.

## Invariants

- Claude Code and Codex are independent required observations; one green row never masks a
  red, unavailable, unsupported, stale, or skipped row of the other provider.
- Trust, approval policy, sandbox, credential containment, dirty-tree status, and release
  evidence remain separate axes.
- Missing, stale, uncommitted, malformed, privacy-unsafe, partial, orphaned, duplicated, or
  reordered evidence fails closed.
- P0 and this contract contain no fleet, Brain, credential, trust, or provider write.
- A contract-freeze decision approves only the exact contract bytes; it never authorizes a
  containment, provider, fleet, credential, or trust mutation.

## Predecessor source pins

| Predecessor | Version | SHA-256 | Preserved boundary |
|:--|:--|:--|:--|
| `provider-migration-gates.md` | v1.0.0 | sha256:e0b183aa0a14ba66d5e9b59709e5e4b8b324cb3509db088f55a6ebe846b64f6c | G01–G11 transition, evidence, owner, pass/fail, protected-path and no-write obligations |
| `provider-capability-contract.md` | v1.0.0 | sha256:b22e1df11bc31651a2f9a4e4eeaaa2996af1556eac656894e65712cb261c2d56 | provider-specific capability admission and non-masking provider rows |
| `provider-artifact-contract.md` | v1.3.0 | sha256:79591611c409dc873a631a51d17b41a1ced194a2ce363db678b2e5e12a122289 | ownership, provenance, preimage, rollback, drift and no-write checks |
| `provider-config-contract.md` | v1.0.0 | sha256:4456c60713754034050d9ad6e19945b26a3a017ffcda8f3b21924727d7e98a03 | canonical selection intent remains separate from provider projections |
| `provider-harness-contract.md` | v1.0.0 | sha256:7309f3a4e80a2398b0fc7b84300c6cd1dd2a7d62d809b15e726ca78e790f1965 | trust, approval and sandbox axes remain independent |
| `provider-instruction-contract.md` | v1.0.0 | sha256:37ab85d0b0ccc6b59d0fa5b197e17d85c7a31e63381c5f57d7e876ce27251910 | shared meaning plus additive provider extensions |
| `provider-command-routing-contract.md` | v1.0.0 | sha256:940c5492fd45934be63408b5b5f298f106fd45efaffe980eaa4c699ee8a7dbe6 | provider-native routing and two-axis route gates remain explicit |

## Exact G01–G11 obligation mapping

`Source row SHA-256` is the SHA-256 of compact sorted-key UTF-8 JSON built from every cell of
the corresponding row in the pinned predecessor `## Preconditions` table. The checker
recomputes it from the archived bytes; changing, omitting, duplicating, reordering, or
orphaning any obligation is a refusal.

| Obligation | Predecessor gate | Source row SHA-256 | Successor enforcement | Failure action |
|:--|:--|:--|:--|:--|
| O-G01 | G01 | sha256:192d725d992b7aa0565766c7994a42b8d139228970515a72bb2ab2d9c7317c8c | R01 and the second independent P0 audit preserve the P0 contract, ADR, protected-delta and owner gates | keep P1 closed; fix forward P0 and repeat its audit |
| O-G02 | G02 | sha256:08c041ad682a0715f2a43597c4684377506df8adadd0c025a107884ac937c178 | R02 preserves frozen P1 contracts, compatibility evidence, no-write and independent audit | keep P2 closed; fix forward P1 and obtain a new D# for contract change |
| O-G03 | G03 | sha256:861f5f9314ec57eff3ad987c0ed3c0ab4e0631dbbddce933b9e8638ccbc81070 | R04 preserves skill-publication parity before command/harness consumers | keep the dependent consumer closed; repair the owning phase without a dual-tree fork |
| O-G04 | G04 | sha256:75114032944a0621ecf6fa028c11d45c6b23fc47236d4440cc94cc58550b844b | R04 preserves command identity, native invocation, compatibility and fail-closed routing | keep the dependent consumer closed; repair routing without semantic downgrade |
| O-G05 | G05 | sha256:c12459f83ba54a7cccb0394442c17a5ce65d76bfdb041dc8e98db926daa2934c | R05 preserves harness/instruction compatibility, security-axis separation and protected delta | keep deployment closed; repair the owning phase before rollout |
| O-G06 | G06 | sha256:691033e9c9d031a0973c9bf243e526aa34c13e87c9c4b8cd933e3a3e170e56ec | R06 preserves cold committed checkpoint, both-provider evidence and protected delta | keep the next phase closed; fix forward and repeat the cold proof |
| O-G07 | G07 | sha256:9a13a25b9727678c49e3b3d86df4c28b86d42725bde6b0afc51054cf238f5c72 | R07 and final P7.4 preserve exact provider docs/catalog hashes and non-default full access | block release assembly; repair docs and catalog projections |
| O-G08 | G08 | sha256:1a3fa32120bc8125ba5a0361930261a0e09856d5b2fe86f6a0c63d3059864930 | R07 and final P7.4 preserve isolated-before-live, exact approval, rollback and idempotence | leave live targets unchanged until repair and re-approval |
| O-G09 | G09 | sha256:5c31b4059dceb9a281323c10b7cd41e109c9939612caa8d6ec330abdddebdc8b | R07 and final P7.4 preserve ownership, replacement, rollback and dual-provider cleanup proof | keep cleanup read-only; never delete unknown or user-owned paths |
| O-G10 | G10 | sha256:660c4b43df91adfa40d6f4ffab04be028f964242297a0a9abce7c33cb37b800e | final P7.4 preserves literal GREEN, owner approval, clean release scope and FOREMAN no-write | keep FOREMAN paused; route ATTENTION or RED to fix-forward |
| O-G11 | G11 | sha256:60cdaff8993cdd7f82fb6903804f96e0d86e7ba1aee76c62969f2751ead28233 | final P7.4 preserves fleet no-write and a separate future rollout-plan authority | refuse fleet writes; without a separate approved plan the outcome is no-op |

## Recovery transition matrix

| Gate | Transition | Producer | Independent verifier | Verifier phase | Required evidence | Owner | Pass rule | Failure action |
|:--|:--|:--|:--|:--|:--|:--|:--|:--|
| R01 | P0 → P1 | P0.5–P0.8 | `task:plan-audit 2026.08.02-PROVIDER-CONTRACT-LOCALE P0` second independent pass | P0 | sealed baseline, classification, recovery evidence, executable security evidence and provenance ledger | repository owner | P0 is terminal, committed, exact and the second audit is GREEN | keep P1 closed; fix forward P0 and repeat its audit |
| R02 | P1 → P2 | P1.1–P1.3 | `task:plan-audit 2026.08.02-PROVIDER-CONTRACT-LOCALE P1` | P1 | frozen control-plane, Skill Core, adapter and migration/rollback contracts | P1 contract owner | both provider rows, compatibility and rollback gates pass before P2 starts | repair the owning P1 item and repeat its audit |
| R03 | P2 → P3 | P2.1–P2.3 | `task:plan-audit 2026.08.02-PROVIDER-CONTRACT-LOCALE P2` | P2 | frozen locale, overlay, review and skill-evidence contracts | P2 contract owner | deterministic English source, locale fallback and overlay gates pass before P3 starts | repair the owning P2 item and repeat its audit |
| R04 | P3 → P4 | P3.1–P3.3 | `task:plan-audit 2026.08.02-PROVIDER-CONTRACT-LOCALE P3` | P3 | control-plane, additive adapters, typed audit graph and provider-qualified status evidence | P3 owner | canonical intent stays singular and both provider readbacks pass before P4 starts | repair the owning P3 item and repeat its audit |
| R05 | P4 → P5 | P4.1–P4.6 | `task:plan-audit 2026.08.02-PROVIDER-CONTRACT-LOCALE P4` | P4 | locale runtime, evidence-admission ledger, reviewed corpus and generated readback | P4 owner | generated views and provider semantics pass with immutable-token and rollback proof | repair the owning P4 item and repeat its audit |
| R06 | P5 → P6 | P5.1–P5.4 | `task:plan-audit 2026.08.02-PROVIDER-CONTRACT-LOCALE P5` | P5 | approved action set, append-only transaction log, convergence and rollback evidence | P5 owner | every mutation has ownership, preimage, rollback and terminal journal state | stop and preserve the affected target; repair P5 and repeat its audit |
| R07 | P6 → P7 | P6.1–P6.3 | `task:plan-audit 2026.08.02-PROVIDER-CONTRACT-LOCALE P6` | P6 | Brain disposition, provider-health contract and exact-set fleet evidence | P6 owner | both provider health rows pass without masking before P7 starts | repair the owning P6 item and repeat its audit |

The verifier phase of every row equals the transition's producer phase and therefore exists
after the producer is terminal but before its consumer starts. A self, future, cross-phase,
or P7.4-only transition verifier is invalid.

## Final release audit

| Role | Verifier | Scope | Timing |
|:--|:--|:--|:--|
| additional final release audit | `P7.4` | rechecks R01–R07, G01–G11, provider parity, release evidence, rollback and no-write boundaries | after P7.1–P7.3; never used to open P1–P7 |

## P0.7 admission

The no-op branch requires a fresh executable redacted producer with `action_set=[]`,
`plaintext_secret_findings=0`, `protected_target_delta=0`, command/detector provenance and
green rows for both providers. It requires no mutation decision.

A mutation branch is refused unless a separate immutable accepted decision has
`type: containment_mutation_decision` and names the exact target, action, preimage, backup,
rollback and stop rule. A contract-freeze decision can never authorize containment.

## Compatibility

This v1.0.1 patch preserves all v1.0.0 recovery and predecessor obligations. It strengthens
their machine verification and repairs verifier scheduling without changing pass/fail meaning,
owner authority, protected paths, provider independence, rollback, or fleet no-write.
Unknown major, semantic weakening, missing mapping, or topology drift fails closed.

## Validation

`artifacts/p0-recovery-gates-check.py` validates the exact table schemas and order, predecessor
pins, G01–G11 row fingerprints, R01–R07 field completeness/topology, final P7.4 role, matrix
privacy, immutable decision type/version/hash and evidence digests. Its tests mutate copied real
inputs; no synthetic exception stands in for a checker call.
