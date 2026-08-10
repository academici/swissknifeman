# P0 acceptance freeze crosswalk

## Purpose

This is the exact P0.5 bridge from the candidate-independent rubric to the five P1 contracts and
the P4/P5 evidence producers. A later phase may strengthen evidence but may not delete a row,
change a threshold, replace a denominator, or move terminal adjudication into candidate code.

The `P1 consumer` column names the contract that must carry the clause as a versioned input. The
`Evidence producer` column names the first executable proof and the terminal pilot consumer. A row
with multiple owners requires all named contributions; it does not create duplicate enum ownership.

## Clause-to-contract and evidence map

| Rubric ID | P1 consumer | Evidence producer | P0 threat cases | Required terminal evidence |
|:--|:--|:--|:--|:--|
| REL-ACCEPTED-SCOPE | P1.2, P1.5 | P4.1, P4.5, P5.2, P5.4 | THR-007, THR-008, THR-018, THR-026 | Frozen Files/acceptance/validation hashes, exact accepted postimage, non-synthetic inclusion identity |
| REL-RECOVERY | P1.1 | P4.1, P4.2, P5.3 | THR-009, THR-010, THR-012, THR-016, THR-017, THR-018, THR-023 | Fresh-process reconcile result for every exact pre/post/partial/third-state class; invalid chain and absent backup remain incident |
| REL-IDEMPOTENCY | P1.1 | P4.2, P5.3 | THR-010, THR-011, THR-012 | Stable idempotency identity, duplicate evidence, external call counter at most one per attempt |
| REL-VALIDATION | P1.1, P1.2 | P4.1, P4.2, P5.2 | THR-007, THR-008 | Independent frozen argv result bound to accepted postimage and source hashes |
| REL-BUDGET | P1.3, P1.5 | P4.5, P5.2, P5.4 | THR-019 | Journal-derived attempts/calls/tokens/cost/time/turns/retries/rollbacks/owner events and breaker outcome |
| SEC-AUTHORITY | P1.3 | P4.4, P4.5, P5.3 | THR-001, THR-002, THR-005, THR-006, THR-015 | Total authority decision with controlling sources before every public effect; protected/unknown/conflict remains OWNER or refused |
| SEC-PRIVACY | P1.4, P1.5 | P4.4, P4.5, P5.4 | THR-002, THR-020, THR-025 | Independent byte scan and closed-schema proof over committed journal/results/reports; only minimized allowlisted fields remain |
| SEC-WORKTREE | P1.2, P1.3 | P4.3, P5.2, P5.3 | THR-003, THR-004, THR-021, THR-022, THR-024 | Exact owned delta, linked-worktree identity, clean pinned base, serialized integration, conflict rollback and zero foreign mutation |
| SEC-HOOK-INTEGRITY | P1.3, P1.5 | P4.4, P4.5, P5.4 | THR-007, THR-015 | Effective trusted hook/preflight verdict exact green; warning, stale-source, skip, exit 127, or unknown stays non-green |
| EVD-SOURCE-HASHES | P1.1, P1.2, P1.5 | P4.1, P4.5, P5.1, P5.4 | THR-017, THR-018, THR-026 | Pre-effect hashes for repository/source/plan/scope/acceptance/validation/contracts/provider/candidate/catalog/baseline and drift refusal |
| EVD-INDEPENDENT-ADJUDICATOR | P1.5 | P4.1, P4.5, P5.1, P5.4 | THR-008, THR-026 | Expected rows authored before candidate results; independent recomputation rejects candidate totals, self-hashes and omitted failures |
| EVD-UNKNOWN-PRESERVATION | P1.4, P1.5 | P4.5, P5.1, P5.4 | THR-014, THR-019, THR-020, THR-026 | Every unavailable field is null plus source-specific unknown_reason and disables only dependent branch |
| PRV-PARITY-SCOPE | P1.4, P1.5 | P4.4, P4.5, P5.4 | THR-013, THR-014, THR-015, THR-020 | Two-provider eligible mapping/evidence or exact prior Owner D# naming one provider and bounded single-provider scope |
| ECO-MATCHED-SCOPE | P1.2, P1.5 | P4.5, P5.1, P5.4 | THR-018, THR-026 | Same base/task/Files/acceptance/validation/provider/model/effort/capabilities and accepted-slice unit for both lanes |
| ECO-D14-BRANCH-1 | P1.5 | P4.5, P5.1, P5.4 | THR-019, THR-026 | Exactly five predeclared non-synthetic waves, owner decisions/dispatched slices below 1/4, candidate token and cost units no worse than baseline |
| ECO-D14-BRANCH-2 | P1.5 | P4.5, P5.1, P5.4 | THR-019, THR-026 | Workflow/candidate token and cost units both at least 2x, with all attempts and coordinator overhead included |

## P1 contract obligations

- **P1.1 `supervisor-run-v1`:** owns durable identities, chain/replay, public-boundary ordering,
  duplicate semantics, recovery evidence, and validation-event references. It consumes rubric floors
  but does not own economic formulas.
- **P1.2 `slice-manifest-v1`:** owns immutable scope, reads/files/validation, dependency, route,
  capability, acceptance, and source hashes. It references Task Contract and execution policy rather
  than copying their predicates.
- **P1.3 `authority-policy-v1`:** owns precedence, narrowing, AUTO/AUTO-FIX/OWNER outcomes, protected
  boundaries, stable finding identity, and budget/attention authority decisions.
- **P1.4 `worker-envelope-v1`:** owns provider-neutral request/result evidence, closed exit classes,
  supported/degraded/unsupported/unknown states, caps, and privacy exclusions.
- **P1.5 `economy-evidence-v1`:** owns attempt-complete normalized metrics, unknown reasons,
  provider-scope eligibility, D14 branch computation, evidence privacy, and the independent terminal
  verdict inputs. It references the four earlier contracts and cannot redefine their enums.

Every P1 contract must cite this rubric version and its content hash. P1.5's aggregate contract-set
validator must reject a missing P1.1–P1.5 contract, unresolved reference, duplicated enum owner, or
hash/version drift.

## P4 and P5 adjudication chain

1. P4.1 freezes candidate-independent fault rows before exercising the candidate.
2. P4.2 proves no-rerun recovery and idempotency; P4.3 proves write ownership; P4.4 proves
   authority/privacy/provider/hook boundaries; P4.5 independently aggregates all common floors.
3. P5.1 freezes archive mapping, live trials, matched lanes, order, providers, routes, and hashes
   before dispatch. Shadow evidence never counts as a non-synthetic battle wave.
4. P5.2 proves the exact live reversible path; P5.3 composes crash/reconcile/provider failures.
5. P5.4 recomputes all common floors first, then both economic branches from per-attempt evidence,
   emits exactly one `GO|NO-GO`, and names every failed or unavailable floor/branch.

P4/P5 candidate code may emit typed observations but cannot write expected outcomes, change this
crosswalk, or select its own trial/baseline. A missing producer, red validator, unresolved severe or
third state, or unknown common input keeps the terminal verdict `NO-GO`.

## Current P0 evidence limitations

`baseline-catalog.json` contains useful committed history but no row currently qualifies as a
non-synthetic battle wave, and several matched token/cost/intervention fields remain unknown.
`provider-matrix-v1.json` records local capabilities without pretending unknown cost/cache parity.
Therefore P0.5 freezes rules and test cases only; it does not certify Artifex or pre-judge P5.
