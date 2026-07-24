# Research 03 — metrics и эксперимент

## Fixed corpus

P0.3 формирует 20–50 cases из:

- forgotten latest owner requirement;
- redundant approval after approved plan;
- premature stop after clean close;
- stale phase/item in cold-start prompt;
- missing user-facing contour;
- audit of bookkeeping reopening product;
- same-finding regression loop;
- wrong provider path/command;
- duplicate skill trigger;
- missing runtime snippet;
- route mismatch and false self-attribution;
- hook command missing/stale/duplicate.

Каждый case содержит task input, environment fixture, critical constraints,
expected actions/forbidden actions, outcome grader и transcript assertions.

## Metrics

- `critical_requirement_retention`
- `first_pass_success`
- `owner_intervention_rate`
- `premature_stop_rate`
- `redundant_approval_rate`
- `audit_reopen_rate`
- `same_finding_loop_depth`
- `context_input_per_success`
- `session_reload_count`
- `routing_compliance`
- `trace_completeness`
- `provider_executability`
- `regression_escape`

## Experiment

1. Freeze corpus and grader version before implementation.
2. Run baseline on current main/runtime; archive traces and quality flags.
3. Apply P1/P2/P3 changes in self-host/fixtures.
4. Run paired candidate with same model route and corpus.
5. Inspect every failed transcript and a random sample of passing transcripts.
6. Canary 5–10 representative real self-host tasks.
7. P3.5 decides go/remediate/rollback by frozen floors.

## Proposed floors for P0.3 Owner freeze

- critical requirement retention 100%;
- premature stop and redundant approval 0 on critical bank;
- effective duplicate semantic identities 0;
- hook/runtime reference resolution 100%;
- required trace completeness ≥99%;
- overall pass@1 ≥95% and at least +30 percentage points to baseline;
- context input per success −50%;
- owner intervention −75%;
- median same-finding loop ≤1, p95 ≤2;
- critical regression escape 0.

If baseline is already above a relative target, absolute floor governs.
If a grader is wrong, fix grader/corpus under versioned exception and rerun
both baseline/candidate; candidate-only threshold changes are forbidden.
До explicit Owner Approval P0.3 эти значения являются предложением, а не
замороженным контрактом; P0.4 не начинается.
