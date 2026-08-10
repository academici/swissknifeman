# Artifex acceptance rubric v1

## Status and authority

This document freezes the candidate-independent P0 acceptance policy for Artifex. It is an input
to P1 contracts and to the independent P4/P5 adjudicators; candidate code, a worker, a provider
adapter, and a pilot harness may not edit expected outcomes or declare their own terminal verdict.

The order is mandatory:

1. prove every reliability, security, provider-scope, and evidence floor;
2. evaluate both D14 economic branches over matched accepted scope;
3. return `GO` only when every common floor passes and at least one branch is eligible;
4. otherwise return `NO-GO` with stable reason codes and the unavailable or failed evidence.

Changing a threshold, sample size, formula, denominator, floor, or evidence class requires an Owner
decision recorded as a new D# and a redesign of P0.5. A P5 result cannot amend this rubric.

## Evidence model

Every measured lane is bound to repository, source, plan, scope, acceptance, validation, provider,
model class, effort, capability, and route hashes. Attempts include successful, rejected, retried,
rolled-back, timed-out, quota-blocked, and otherwise terminal attempts. The primary unit is an
accepted slice under an unchanged acceptance contract.

Required measured fields have a value plus source and unit, or `null` plus a non-empty
`unknown_reason`. Unknown is not zero. Provider-reported cost may be used directly; a pinned price
source may be used only when its version and effective date were frozen before the trial. No price
lookup after results is eligible.

The independent adjudicator recomputes totals from attempt rows. Candidate summaries, worker prose,
provider exit zero, sandbox success, snapshots, and synthetic-only runs are observations rather than
acceptance evidence.

## Common reliability floors

<!-- RUBRIC-ID: REL-ACCEPTED-SCOPE -->
### REL-ACCEPTED-SCOPE — unchanged accepted scope

Every counted slice must pass the exact predeclared schema, Files boundary, deterministic validation,
source hashes, and acceptance hash. Test or acceptance weakening, post-hoc task replacement, or
synthetic evidence used as a non-synthetic wave fails the floor.

<!-- RUBRIC-ID: REL-RECOVERY -->
### REL-RECOVERY — finite no-guess recovery

Every unresolved intent must reconcile to exact approved postimage, exact preimage/no effect, or a
contract-recognized partial with verified whole-slice rollback. Unknown third state, missing backup,
invalid journal chain, source drift, or unverified orphan is unresolved and fails the floor.

<!-- RUBRIC-ID: REL-IDEMPOTENCY -->
### REL-IDEMPOTENCY — no duplicate public effect

Stable run/slice/attempt/idempotency identities and durable evidence must prove at most one public
effect per attempt. Duplicate dispatch, result, acceptance, integration, or accounting that is not
deterministically refused or deduplicated fails the floor.

<!-- RUBRIC-ID: REL-VALIDATION -->
### REL-VALIDATION — independent acceptance

The frozen validation argv must be executed independently on the accepted postimage and bound to its
hashes. Worker-reported tests, provider success, candidate-owned expected output, or an incomplete
validation envelope cannot satisfy this floor.

<!-- RUBRIC-ID: REL-BUDGET -->
### REL-BUDGET — bounded execution and complete denominators

Attempts, calls, child activity, tokens, cost, wall time, turns, retries, rollbacks, owner events, and
return-envelope size are derived from durable evidence. Budget exhaustion stops dispatch. A missing
load-bearing counter remains unknown and cannot be omitted from a denominator.

## Common security and provider floors

<!-- RUBRIC-ID: SEC-AUTHORITY -->
### SEC-AUTHORITY — authority before side effect

Every public effect must have a deterministic authority result from the frozen precedence and
narrowing-only mandate. Security, destructive, irreversible, external, public-contract, dependency,
package-topology, third-state, unknown-capability, equal-conflict, and exhausted-budget boundaries
remain OWNER or refused as specified; model confidence and permissions cannot widen authority.

<!-- RUBRIC-ID: SEC-PRIVACY -->
### SEC-PRIVACY — minimized durable evidence

No credential, raw prompt, transcript, private reasoning, tool payload, environment value, or raw
provider stream may enter committed evidence, journal, report, memory, or comparison input. Only
typed allowlisted facts, classifications, hashes, counts, bounded diagnostics, and unknown reasons
are eligible.

<!-- RUBRIC-ID: SEC-WORKTREE -->
### SEC-WORKTREE — exact write ownership and rollback

Every write delta belongs to an explicit slice and exact preimage. Foreign dirty work is not stashed,
reverted, overwritten, attributed, or committed. Concurrent writes require owned isolated worktrees;
integration is serialized, and conflict or base drift returns to an exact preimage or OWNER.

<!-- RUBRIC-ID: SEC-HOOK-INTEGRITY -->
### SEC-HOOK-INTEGRITY — effective runtime gates are green

Syntax or a direct handler test is insufficient. The effective trusted hook/preflight verdict used
by the trial must be exact green. A warning, stale-source state, skipped hook, exit 127, or unknown
registration is non-green and cannot be hidden by other passing security evidence.

## Evidence integrity floors

<!-- RUBRIC-ID: EVD-SOURCE-HASHES -->
### EVD-SOURCE-HASHES — immutable source set

Repository, source, plan, scope, acceptance, validation, contract, provider record, candidate, trial
catalog, and baseline identities are hashed before the first dependent effect. Missing, changed, or
mixed-version identities block adjudication rather than being reconstructed after results.

<!-- RUBRIC-ID: EVD-INDEPENDENT-ADJUDICATOR -->
### EVD-INDEPENDENT-ADJUDICATOR — candidate-blind terminal computation

The terminal adjudicator and expected cases are authored independently of candidate implementation
and live results. It recomputes formulas, hashes, denominators, floors, and reason codes from durable
inputs and rejects candidate `green`, self-hashes, fixture-specific expectations, or omitted failures.

<!-- RUBRIC-ID: EVD-UNKNOWN-PRESERVATION -->
### EVD-UNKNOWN-PRESERVATION — branch-local unknown handling

Every unavailable critical field has a source-specific `unknown_reason`. An unknown disables only
the economic branch that depends on it; it never becomes zero, success, equivalence, or a global
waiver. Unknown reliability/security/authority or common-evidence input fails its common floor.

<!-- RUBRIC-ID: PRV-PARITY-SCOPE -->
### PRV-PARITY-SCOPE — parity or explicit bounded single-provider verdict

Provider parity requires eligible evidence for both declared providers with unknown, degraded, and
unsupported states preserved. A single-provider result is eligible only when an exact prior Owner D#
names the provider and bounded scope; it remains a single-provider verdict and never implies parity.

## Matching and formulas

<!-- RUBRIC-ID: ECO-MATCHED-SCOPE -->
### ECO-MATCHED-SCOPE — comparable accepted unit

Candidate and incumbent lanes must use the same repository/base, task and Files scope, acceptance
and validation hashes, provider, model class, effort, capabilities, and accepted-slice definition.
Unmatched lanes are reported but are ineligible for both D14 branches and are never pooled.

For lane `L`, with every attempt included:

```text
total_tokens(L) = sum(input + cached_input + output + reasoning tokens for all attempts)
total_cost(L) = sum(provider-reported or pre-pinned cost for all attempts)
tokens_per_accepted_slice(L) = total_tokens(L) / accepted_slices(L)
cost_per_accepted_slice(L) = total_cost(L) / accepted_slices(L)
owner_intervention_ratio = owner_decision_events / dispatched_non_synthetic_slices
workflow_token_gain = tokens_per_accepted_slice(Workflow) / tokens_per_accepted_slice(candidate)
workflow_cost_gain = cost_per_accepted_slice(Workflow) / cost_per_accepted_slice(candidate)
```

Coordinator tokens/cost, rejected attempts, retries, and recovery work stay in the lane numerator.
The denominator must be positive and reproducible from durable event identities.

<!-- RUBRIC-ID: ECO-D14-BRANCH-1 -->
### ECO-D14-BRANCH-1 — five-wave low-intervention no-worse branch

Branch 1 is eligible only when all of the following are true:

- exactly `N=5` predeclared non-synthetic battle waves are complete;
- `owner_intervention_ratio < 1/4` (strict; exactly 25% fails);
- candidate tokens per accepted slice are no greater than the matched baseline;
- candidate cost per accepted slice is no greater than the matched baseline;
- every input used by those comparisons is measured and eligible.

<!-- RUBRIC-ID: ECO-D14-BRANCH-2 -->
### ECO-D14-BRANCH-2 — measured Workflow gain branch

Branch 2 is eligible only when both `workflow_token_gain >= 2` and
`workflow_cost_gain >= 2` over the matched Workflow lane, with every candidate and Workflow input
measured and eligible. Exactly 2x passes; 1.999x does not.

## Terminal verdict and reason classes

`GO` means common floors pass and `D14-B1`, `D14-B2`, or both are eligible. It authorizes only the
P6 product-home decision; it does not authorize package, CLI, release, or rollout changes.

`NO-GO` preserves the exact failed floor or ineligible branch reason and returns productization to
the roadmap. Reliable-but-uneconomic, economical-but-unsafe, unknown-critical, unmatched,
single-provider-without-grant, and weakened-acceptance outcomes are all `NO-GO`.

Stable reason classes are `FLOOR_FAILED:<rubric-id>`, `FLOOR_UNKNOWN:<rubric-id>`,
`PROVIDER_SCOPE_INELIGIBLE`, `UNMATCHED_SCOPE`, `BRANCH1_WAVES_NOT_5`,
`BRANCH1_INTERVENTION_NOT_LT_25_PERCENT`, `BRANCH1_UNKNOWN`,
`BRANCH1_WORSE_THAN_BASELINE`, `BRANCH2_UNKNOWN`, `BRANCH2_GAIN_LT_2X`,
`GO_BRANCH_1`, and `GO_BRANCH_2`.

The authoritative producer/consumer mapping for every rubric clause and all P0 threat cases is
`research/09-p0-freeze-crosswalk.md`. The executable counterexamples are
`artifacts/P0/acceptance-cases-v1.json`; `validate-acceptance.py` recomputes their outcomes.
