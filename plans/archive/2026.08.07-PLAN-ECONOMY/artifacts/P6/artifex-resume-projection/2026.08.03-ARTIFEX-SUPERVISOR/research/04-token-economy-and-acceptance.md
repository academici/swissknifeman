# Token economy and acceptance

## Baselines

P0 must identify matched work, not compare unrelated phases:

- **manual item loop:** owner/coordinator launches and interprets each item;
- **current Workflow:** same intended slice set where provider capability permits;
- **Artifex candidate:** same repository anchor, acceptance commands, provider/model class and scope.

Historical journals may seed the baseline but missing token/cost fields remain unknown. P5's battle
waves are non-synthetic repository tasks selected before candidate execution.

## Evidence schema minimum

Per run, slice, attempt and provider:

- input, cached-input, output and reasoning tokens where the provider reports them;
- coordinator-context payload bytes/tokens and worker return-envelope bytes;
- tool turns, provider calls, retries and model/effort route;
- wall time and cost only from provider-reported/pinned pricing evidence;
- accepted slices, rejected attempts, rollback count, owner interventions and attention latency;
- source/plan/acceptance hashes that make runs comparable;
- `unknown_reason` rather than imputed zero for unavailable fields.

No prompt, chain-of-thought, secret or raw environment content is required for economy evidence.

## Normalization

Primary unit is accepted slice under the same acceptance contract:

```text
tokens_per_accepted_slice = all candidate run tokens / accepted slices
owner_intervention_ratio = owner decision events / dispatched non-synthetic slices
retry_amplification = total attempts / accepted slices
```

Runs with different accepted scope, validation, model class or provider health are not silently pooled.

## GO / NO-GO

GO requires all reliability/recovery/security floors green and either:

1. `N=5` non-synthetic battle waves with owner intervention ratio `<25%` and normalized total
   token/cost no worse than the matched baseline; or
2. a measured `≥2×` normalized token/cost improvement over matched Workflow.

Additional guards:

- no unknown critical metric in the selected economic branch;
- no acceptance/test weakening;
- no unreconciled side effect, third state or unresolved severe security finding;
- provider parity tested or an explicit single-provider scope verdict, never masked;
- coordinator return envelope meets the P1.5 cap.

NO-GO returns the implementation to roadmap with the exact failing floor. It does not authorize
package promotion. A result can be reliable but uneconomic, or economical but unsafe; both are NO-GO.

## Why N=5 is a gate, not proof of universality

Five waves are enough to decide whether the owner-directed prototype earns productization work,
not enough to claim broad statistical generality. P6 rollout should retain ongoing telemetry and
stop/circuit-breakers for drift.

RAG:— (roadmap/owner criterion plus internal normalization; provider field availability remains P0.3 empirical work).
