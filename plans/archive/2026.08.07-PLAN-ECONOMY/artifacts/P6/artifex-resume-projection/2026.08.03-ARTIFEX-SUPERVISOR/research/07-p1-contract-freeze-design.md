# P1 contract-freeze design

## Sources and current precondition

This synthesis uses `findings/00-repo-recon-2026-08-03.md`,
`findings/01-external-agent-runtime-2026-08-03.md`,
`findings/02-reference-products-2026-08-03.md`,
`findings/04-p0-design-verification-2026-08-03.md`, and
`findings/05-p1-donor-reconciliation-2026-08-03.md`, plus `research/00`–`06` and the six
consumed contracts named in `plan.md` §7. P0 outputs are planned producers, not present inputs:
execution of P1.1 is gated on terminal P0 and successful validation of every file promised by
P0.1–P0.5. RAG:— (repo-grounded design state).

## Contract dependency graph

| Item | Owns | References, never duplicates | Needed by |
|:--|:--|:--|:--|
| P1.1 | run identity, supervisor states/events, hash-chained WAL, side-effect boundary and reconcile | plan journal/status vocabulary, donor item-state machine, FOREMAN run identity, live `harness run` gap | P1.2–P1.5, P2–P6 |
| P1.2 | immutable slice manifest, dependency/readiness graph and compile refusal codes | Task Contract content hash/route/capabilities; fleet execution-policy ceilings | P1.3–P1.5, P2–P5 |
| P1.3 | total AUTO/AUTO-FIX/OWNER decision table, narrowing and attention packet | P0 authority cases; donor risk/review-loop vocabulary | P1.4–P1.5, P2–P6 |
| P1.4 | provider-neutral request/result/event/exit envelope and evidence caps | P0 provider matrix; unified trace identity; P1.2/P1.3 scope/authority | P1.5, P3–P5 |
| P1.5 | normalized economy/privacy evidence, formulas, unknown handling and GO/NO-GO inputs | P0 baseline/acceptance freeze; all four preceding P1 contracts | P4–P6 |

This is a strict producer/consumer chain. P1.2 needs P1.1 identities; P1.3 classifies P1.2
operations; P1.4 carries both; P1.5 measures accepted results defined by all four. Five items with
deterministic validators do not satisfy the workflow criterion because their scopes are not
independent, and the chain has a contract/Owner checkpoint at every item boundary. No workflow is
created. RAG:— (repo-grounded: plan-protocol orchestration criterion and this dependency graph).

## Freeze form and alternatives

Each item produces one readable Markdown contract, one normalized adversarial case bank and one
stdlib validator. P1.5 additionally produces a manifest and aggregate validator that proves the
five contracts reference one another without cyclic ownership or duplicated enums.

Alternatives rejected:

1. One mega-contract would erase ownership/version boundaries and force every consumer to absorb unrelated fields.
2. One shared validator edited by all five items would create a coupling hotspot and let later items reinterpret earlier cases; per-contract validators plus a terminal aggregate check keep expected results independent.
3. Copying donor enums into every new contract would create competing SSOTs. New contracts pin and reference donor identities, adding only supervisor-owned fields.
4. A P1 workflow would either violate the dependency chain or become a second scheduler before the supervisor contract exists.

RAG:— (repo-grounded alternatives against donor boundaries and plan-protocol).

## High-stakes ecosystem-core pre-mortem

Prospective-hindsight prompt: the Artifex contract freeze failed 6–12 months after adoption.
Independent causes were recorded first, then clustered into the mitigations below.

| Clustered failure cause | Observable early signal | Mitigation | Owner |
|:--|:--|:--|:--|
| P0 evidence was treated as if it existed, so frozen fields were invented | missing P0 path/hash, `baseline_pending` coerced to zero | hard terminal-P0 precondition in every P1 validator; missing/unknown refuses | P1.1–P1.5, aggregate owner P1.5 |
| Artifex duplicated `harness run`/Task lifecycle and the two paths drifted | same state/route/close fact has two owners | P1.1 reuse/gap crosswalk; contracts cite donor vocabularies and add only missing supervisor seams | P1.1/P1.2 |
| AUTO authority gradually widened through retries or worker confidence | an allow lacks controlling source, same finding identity or unchanged acceptance hash | total adversarial authority bank; unknown/equal-precedence conflict and budget exhaustion always OWNER | P1.3 |
| Provider-specific success/usage fields leaked into the neutral contract | one provider field has no neutral meaning or absent value becomes zero | closed neutral envelope; `supported`/`unsupported`/`unknown` with reason; provider adapters stay P3 | P1.4/P1.5 |
| Crash replay duplicated a public side effect or accepted a third state | intent has no terminal observation, postimage matches neither preimage nor approved result | durable intent before boundary, stable idempotency key, whole-slice rollback only, otherwise incident/OWNER | P1.1/P1.3 |
| Five contracts passed individually but disagreed as a set | duplicated enum, unresolved reference, cycle or formula with no evidence producer | manifest plus aggregate cross-contract validator on P1.5; P2 cannot start on a red aggregate | P1.5 |
| Privacy/economy evidence became a success-story metric rather than proof | prompts/secrets/raw tool payloads persist, unmatched runs are pooled, unknown cost disappears | excluded-class scanner, matched acceptance hashes, full-run totals and unknown-dependent branch refusal | P1.5 |

## Stop condition

P1 design is ready when all five items have finite ordered reads, explicit P0 and donor gates,
independent case banks, exact validation commands and manual frontier/high routing. P1 execution is
ready only after P0 is terminal. P2 remains closed until P1.5's aggregate validation is green and
all five item commits are terminal.

## Проверка (verification status)

- RAG: existing same-day first-party findings cover provider isolation/accounting boundaries,
  durable-workflow principles and reference-product behaviour; this pass added repo/donor
  reconciliation and made no new time-sensitive external claim.
- Непроверено → ПОВТОРНЫЙ ПРОХОД: exact installed provider event/exit/accounting envelopes remain
  deliberately assigned to P0.3; P1.4 must consume that empirical matrix rather than memory.
- Обходки/[POSSIBLE-DEFECT]: no workaround introduced; the stale-source Codex lifecycle projection
  remains an environment defect outside this phase.
