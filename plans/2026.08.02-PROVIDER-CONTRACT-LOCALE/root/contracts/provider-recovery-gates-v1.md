# Provider recovery gates

**Version:** v1.0.0

**Status:** frozen

**Approval Owner:** repository owner

**Approval:** D63, 2026-08-10

## Purpose

This additive successor to `provider-migration-gates.md` makes recovery evidence
binary before later provider, locale, and fleet work. It does not alter the
predecessor's G01–G11 obligations, authorize a fleet write, or turn an observed
provider projection into canonical intent.

## Invariants

- Claude Code and Codex are independent required observations; one green row never
  masks a red, unavailable, or skipped row of the other provider.
- Trust, approval policy, sandbox, credential containment, dirty-tree status, and
  release evidence are separate axes.
- Missing, stale, uncommitted, malformed, privacy-unsafe, or partial evidence fails.
- A local override, stale copy, or ambiguous artifact is preserved until a later item
  has ownership, preimage, rollback, and the required authority.
- P0 and this contract contain no fleet, Brain, credential, trust, or provider write.

## Predecessor table

| Predecessor | Version | Preserved obligation |
|:--|:--|:--|
| `provider-migration-gates.md` | v1.0.0 | G01–G11 binary transition and no-fleet-write rules |
| `provider-capability-contract.md` | v1.0.0 | provider-specific capability admission |
| `provider-artifact-contract.md` | v1.3.0 | ownership, provenance, preimage, rollback |
| `provider-config-contract.md` | v1.0.0 | canonical intent remains separate from projections |
| `provider-harness-contract.md` | v1.0.0 | trust/approval/sandbox axes stay independent |
| `provider-instruction-contract.md` | v1.0.0 | shared meaning plus additive provider adapters |
| `provider-command-routing-contract.md` | v1.0.0 | provider-native routing remains explicit |

## Recovery transition matrix

| Gate | Transition | Producer | Independent verifier | Required evidence | Owner | Pass rule | Failure action |
|:--|:--|:--|:--|:--|:--|:--|:--|
| R01 | P0 → P1 | P0.1–P0.4 | P7.4 | P0 baseline, matrix, recovery check, P0.4 verdict | repository owner | P0 evidence is committed and exact branch passes | keep P1 closed |
| R02 | P1 → P2 | P1.1–P1.3 | P7.4 | frozen desired/skill/adapter contracts | P1 contract owner | both providers and rollback gates pass | repair owning P1 item |
| R03 | P2 → P3 | P2.1–P2.3 | P7.4 | locale and authoring conformance | P2 contract owner | deterministic English source and overlay checks pass | repair owning P2 item |
| R04 | P3 → P4 | P3.1–P3.3 | P7.4 | control-plane and provider parity evidence | P3 owner | adapters stay additive and provider rows pass | repair owning P3 item |
| R05 | P4 → P5 | P4.1–P4.6 | P7.4 | locale/corpus migration evidence | P4 owner | generated views and provider semantics pass | repair owning P4 item |
| R06 | P5 → P6 | P5.1–P5.4 | P7.4 | frozen action set and fleet convergence | P5 owner | every mutation has ownership/preimage/rollback | stop and preserve affected target |
| R07 | P6 → P7 | P6.1–P6.3 | P7.4 | health and external-fleet exact-set evidence | P6 owner | both provider health rows pass without masking | repair owning P6 item |

## P0.4 admission

The no-op branch requires a fresh redacted detector and trust evidence with
`action_set=[]`, `plaintext_secret_findings=0`, `protected_target_delta=0`, and
green rows for both providers. It requires no mutation decision.

A mutation branch is refused unless a separate immutable accepted decision has
`type: containment_mutation_decision` and names the exact target, action, preimage,
backup, rollback, and stop rule. D63 is a contract-freeze decision and can never
authorize such a mutation.

## Validation

`artifacts/p0-recovery-gates-check.py` pins this contract, P0.1 manifest, P0.2
classification, action matrix, checker bytes, and the immutable D63 record. Any
digest drift, unknown branch, generated decision view, missing gate field, or
privacy leak fails closed.
