# Economy Evidence Contract v1

## Status, authority, and version

`economy-evidence-v1` is frozen at `1.0.0`. It owns normalized full-run economy,
intervention, retry, rollback, attention and privacy evidence; exact D14 branch
calculation; branch-local unknown handling; and the candidate-independent terminal
economy verdict input. It does not own run/slice/authority/provider enums, acceptance
floors, provider pricing, trial selection, package promotion, or the final P5 product
decision.

Normative inputs are:

- Artifex acceptance rubric v1, SHA-256
  `12d602038c54f5b9b07616e5a9f718be28c5192d29770a5862a21f79351577aa`;
- P0 baseline catalog, SHA-256
  `b0fadc83a8537cb786b9775d7393de6fd973f6d9f20a8dde815366c30fe3cac1`;
- P0 provider matrix, SHA-256
  `3d4c2eb4cdcc0deb7bc76abd84220a3e365ae786233ec44f46ce3491d9905c76`;
- `supervisor-run-v1/1.0.0`, `slice-manifest-v1/1.0.0`,
  `authority-policy-v1/1.0.0`, and `worker-envelope-v1/1.0.0` at the hashes
  pinned by `artifacts/P1/contract-manifest-v1.json`.

Consumers pin both version and content hash. A major change adds, removes, or
renames a required field, formula, verdict, reason class, privacy class, denominator,
threshold, or unknown rule. A minor change adds optional non-adjudicating evidence.
A patch changes diagnostics only.

## Closed evidence shape

<!-- declared-set: evidence_keys -->
```text
schema_version
contract_version
evidence
provider_scope
floor_results
waves
lanes
owner_decision_events
attention_events
dispatched_non_synthetic_slices
unknown_reasons
```

`schema_version` is `economy-evidence-input-v1`; `contract_version` is `1.0.0`.
Every nested object is closed. `evidence` contains exactly:

```text
run_id
repository_hash
plan_hash
scope_hash
acceptance_hash
validation_hash
contract_set_hash
provider_matrix_hash
baseline_catalog_hash
privacy_status
```

All hashes are lowercase SHA-256 observed before the first dependent effect.
`privacy_status` is `clean`; any other value is `PRIVACY_REFUSED`. `provider_scope`
contains exactly `mode`, `provider`, and `owner_grant_ref`. Mode is `parity` or
`single-provider`. Parity requires a null provider/grant. Single-provider requires
`codex|claude-code`; it is eligible only with a non-empty prior Owner D# reference and
never implies parity.

`floor_results` contains every common rubric floor exactly once with value
`pass|fail|unknown`. Missing, extra, or unknown common evidence is invalid or
`FLOOR_UNKNOWN:<rubric-id>`; economics never overrides a failed floor.

Each `waves` row is closed to `wave_id`, `predeclared`, `synthetic`, `terminal`, and
`accepted`. D14 branch 1 counts only unique rows that are predeclared, non-synthetic,
terminal and accepted. Exactly five are required; a synthetic, replaced, incomplete,
or post-hoc row never counts.

<!-- declared-set: lane_names -->
```text
candidate
baseline
workflow
```

Each lane contains exactly `match` and `attempts`. `match` pins repository, base,
scope, acceptance, validation, provider, model class, effort, capabilities and
accepted-slice-definition hashes. Candidate/baseline must match for branch 1;
candidate/workflow must match for branch 2. Unmatched lanes are reportable but
ineligible and are never pooled.

Each attempt contains exactly `attempt_id`, `slice_id`, `accepted`,
`exit_class_ref`, `rollback_event_ref`, `worker`, and `coordinator`. `exit_class_ref`
points to frozen worker/run evidence; `rollback_event_ref` is null or a non-empty
reference to the frozen `supervisor-run-v1` rollback event, so this contract does not
re-mint either enum. `accepted` is true only after independent acceptance and the
accepted-slice denominator is recomputed as the number of unique accepted `slice_id`
values. All attempts remain in numerators, including failed, rejected, retried,
rolled-back, timed-out and quota-blocked work.

<!-- declared-set: metric_fields -->
```text
input_tokens
cached_input_tokens
output_tokens
reasoning_tokens
cost_microunits
duration_ms
turns
```

Both `worker` and `coordinator` contain every metric field. A measured value is a
non-negative integer. An unavailable value is null and requires one non-empty,
source-specific entry in `unknown_reasons`, keyed by its exact JSON pointer. Unknown
is not zero. Token totals include all four token fields for worker and coordinator;
cost, time and turn totals likewise include both components.

`owner_decision_events`, `attention_events`, and
`dispatched_non_synthetic_slices` are non-negative journal-derived integers. The
denominator must be positive for branch 1. Retry count is recomputed as attempts minus
unique slice IDs per lane; rollback count is recomputed from non-null
`rollback_event_ref` identities. Duplicate rollback references are invalid. Attention
is reported independently from owner decisions because immediate security/destructive
attention need not become a decision packet. Candidate summaries are never accepted
as attempt, retry, rollback, token, cost, duration, or turn totals.

## Formulas and exact arithmetic

All comparisons use integer sums and rational cross-multiplication; binary floating
point and rounded percentages are forbidden.

```text
total_tokens(L) = sum(worker + coordinator input + cached-input + output + reasoning tokens over every attempt)
total_cost(L) = sum(worker + coordinator cost over every attempt)
total_duration(L) = sum(worker + coordinator duration_ms over every attempt)
total_turns(L) = sum(worker + coordinator turns over every attempt)
tokens_per_accepted_slice(L) = total_tokens(L) / unique accepted slice IDs
cost_per_accepted_slice(L) = total_cost(L) / unique accepted slice IDs
retry_attempts(L) = attempt count - unique slice IDs
rollback_attempts(L) = count(unique non-null rollback_event_ref)
owner_intervention_ratio = owner_decision_events / dispatched_non_synthetic_slices
workflow_token_gain = tokens_per_accepted_slice(workflow) / tokens_per_accepted_slice(candidate)
workflow_cost_gain = cost_per_accepted_slice(workflow) / cost_per_accepted_slice(candidate)
```

The independent adjudicator recomputes every value from attempts. It rejects a zero
accepted denominator, duplicate attempt identity, missing lane, trusted precomputed
total, non-integer measurement, unmatched source set, or unexplained null.

## D14 eligibility and terminal output

Reliability, security and evidence floors are evaluated before economics.

- Branch 1 requires exactly five eligible waves, intervention ratio strictly below
  `1/4`, matched candidate/baseline lanes, and candidate token and cost units no worse
  than baseline. Exactly 25% fails.
- Branch 2 requires matched candidate/workflow lanes and both Workflow/candidate token
  and cost gains at least `2/1`. Exactly 2x passes; 1.999x fails.
- A missing token/cost input disables only the dependent branch. Unknown common-floor,
  source, privacy, provider-scope or denominator evidence remains NO-GO.

<!-- declared-set: terminal_verdicts -->
```text
GO
NO-GO
```

<!-- declared-set: reason_code_bases -->
```text
FLOOR_FAILED
FLOOR_UNKNOWN
PROVIDER_SCOPE_INELIGIBLE
UNMATCHED_SCOPE
BRANCH1_WAVES_NOT_5
BRANCH1_INTERVENTION_NOT_LT_25_PERCENT
BRANCH1_UNKNOWN
BRANCH1_WORSE_THAN_BASELINE
BRANCH2_UNKNOWN
BRANCH2_GAIN_LT_2X
EVIDENCE_INVALID
PRIVACY_REFUSED
GO_BRANCH_1
GO_BRANCH_2
```

The result is closed to `verdict`, `eligible_branches`, `reason_codes`, and
`metrics`. Floor reasons append the exact rubric ID after `:`. GO requires every
common floor and provider/evidence gate green plus at least one eligible branch.
`eligible_branches` may still show the economic calculation when a common floor
fails, but the terminal verdict remains NO-GO and the failed floor is the terminal
reason. GO authorizes only P6.1 product-home adjudication, not implementation,
package/CLI creation, release, or rollout.

## Privacy and evidence caps

<!-- declared-set: privacy_classes -->
```text
raw_provider_stream
request_content
private_reasoning
tool_input_output
credential
environment_value
```

No credential, environment value, raw request, response, transcript, provider stream,
private reasoning, or tool payload may enter evidence, cases, journal, report, memory,
or comparison input. A synthetic `private_material` fixture key exercises this gate
without containing real sensitive material. Hashes of credentials are also forbidden.
Only typed counts, units, source references, hashes, stable IDs, exit-class references,
and unknown reasons are durable.

Worker envelope byte/event/turn/output caps, slice attempt/time/token ceilings and
authority retry limits remain owned by their four contracts and are referenced by
hash. P0 provides thresholds and eligibility rules, not fabricated runtime caps.
A load-bearing missing cap or accounting observation stays unknown and blocks its
dependent branch.

## Independent carriers and consumers

`artifacts/P1/economy-evidence-cases-v1.json` freezes near-boundary and adversarial
inputs before implementation. `artifacts/P1/validate-economy-evidence.py` applies
generic JSON-pointer mutations, recomputes denominators/formulas, rejects private or
closed-shape drift, and never branches on fixture IDs.

`artifacts/P1/contract-manifest-v1.json` pins the five contract hashes, versions,
owners, consumers, dependencies, references and logical enum ownership.
`artifacts/P1/validate-contract-set.py` independently proves exactly five contracts,
acyclic dependencies, resolved references, exact hashes and one owner per logical
enum. P2 is closed while either validator is red. P4 produces candidate-independent
assurance aggregates; P5 freezes trials and computes the final GO/NO-GO; P6 consumes
the verdict without weakening it.
