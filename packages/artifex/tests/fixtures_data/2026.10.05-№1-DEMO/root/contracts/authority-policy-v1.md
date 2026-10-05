# Authority Policy Contract v1

## Status, authority, and version

`authority-policy-v1` is frozen at `1.0.0`. It owns the deterministic decision
between `AUTO`, `AUTO-FIX`, and `OWNER` for every operation declared by
`slice-manifest-v1`, the narrowing-only mandate rule, routine-choice ordering,
bounded repair identity, and owner-attention timing. It does not own plan status,
slice compilation, run recovery, provider argv/results, acceptance predicates, or
economic budgets.

Normative inputs are the terminal P0.2 authority bank and unsigned example mandate,
P0.4 threat bank, P0.5 acceptance rubric, `supervisor-run-v1/1.0.0`,
`slice-manifest-v1/1.0.0`, and the donor risk/review-loop contract. A worker result,
model confidence, vote, recommendation, sandbox success, provider success, or
frequent owner agreement is evidence only and never creates authority.

Consumers pin both version and content hash. A major change adds, removes, or
renames an operation, action class, protected boundary, reason code, precedence
level, or decision-record key, or changes any existing outcome. A minor change adds
optional evidence without changing an outcome. A patch changes diagnostics only.

## Closed declared sets

<!-- declared-set: operations -->
```text
compile_slice
supersede_pending
dispatch_worker
validate_result
integrate_owned_delta
project_plan_bookkeeping
```

<!-- declared-set: action_classes -->
```text
AUTO
AUTO-FIX
OWNER
```

<!-- declared-set: attention_classes -->
```text
none
batched
immediate
```

<!-- declared-set: common_predicates -->
```text
scope_exact
reversible
capability_known
acceptance_deterministic
source_set_current
preimage_exact
budget_available
```

<!-- declared-set: protected_predicates -->
```text
security
destructive
irreversible
external
public_contract
dependency_change
package_topology_change
third_state
unknown_capability
same_level_conflict
unresolved_routine_choice
```

<!-- declared-set: narrowing_dimensions -->
```text
files
tools
provider
model_class
effort
budget
validations
action_class
```

<!-- declared-set: operation_predicates -->
```text
compile_slice:item_runnable
compile_slice:dependency_ready
compile_slice:input_hashes_current
supersede_pending:prior_pending
supersede_pending:supersedes_hash_exact
dispatch_worker:intent_durable
dispatch_worker:route_frozen
validate_result:observation_durable
validate_result:validation_argv_frozen
integrate_owned_delta:owned_delta
integrate_owned_delta:backup_verified
integrate_owned_delta:serialized_writer
project_plan_bookkeeping:acceptance_durable
project_plan_bookkeeping:projection_exact
```

<!-- declared-set: reason_codes -->
```text
AUTO_LEGAL
ROUTINE_CHOICE_SELECTED
AUTO_FIX_BOUNDED
OWNER_REQUIRED_BY_MANDATE
PROTECTED_SECURITY
PROTECTED_DESTRUCTIVE
PROTECTED_IRREVERSIBLE
PROTECTED_EXTERNAL
PROTECTED_PUBLIC_CONTRACT
PROTECTED_DEPENDENCY
PROTECTED_PACKAGE_TOPOLOGY
THIRD_STATE
UNKNOWN_CAPABILITY
SAME_LEVEL_CONFLICT
HIGHER_PRECEDENCE_OWNER
ROUTINE_CHOICE_UNRESOLVED
FINDING_IDENTITY_CHANGED
ACCEPTANCE_CHANGED
RETRY_BUDGET_EXHAUSTED
MANDATE_WIDENS_FILES
MANDATE_WIDENS_TOOLS
MANDATE_WIDENS_PROVIDER
MANDATE_WIDENS_MODEL
MANDATE_WIDENS_EFFORT
MANDATE_WIDENS_BUDGET
MANDATE_WEAKENS_VALIDATION
MANDATE_WIDENS_ACTION_CLASS
SCOPE_NOT_EXACT
ACCEPTANCE_NOT_DETERMINISTIC
SOURCE_DRIFT
PREIMAGE_MISMATCH
BUDGET_EXHAUSTED
OPERATION_CLASS_FORBIDDEN
OPERATION_PRECONDITION_FAILED
UNKNOWN_OPERATION
```

Unknown action classes are mandate widening and return
`MANDATE_WIDENS_ACTION_CLASS`; unknown operations return `UNKNOWN_OPERATION`.
Unknown states and missing load-bearing values are not defaults: they resolve to the
nearest explicit unknown/protected/precondition reason and `OWNER` before side effect.

## Precedence and narrowing

Authority is evaluated in this exact order:

1. system, security, and provider hard limits;
2. root and applicable Task/Harness instructions;
3. frozen contracts and append-only D# decisions;
4. an authenticated run mandate, which may only subtract rights from levels 1–3;
5. supervisor defaults selecting among already legal alternatives.

The lowest numeric level is strongest. At one strongest level, contradictory
directives return `SAME_LEVEL_CONFLICT` and preserve every conflicting source. A
strongest `OWNER` directive returns `HIGHER_PRECEDENCE_OWNER`; a lower `ALLOW` cannot
override it. Authenticity is not authority: even a signed mandate cannot add files,
tools, provider, model class, effort, budget, validation omissions, or action classes.

Files and tools must be subsets of the frozen envelope. Provider, model class, effort,
and action class must be members. Attempts and parallel ceilings may not exceed the
envelope. Required validations must be preserved as a superset. The first failing
dimension in the order `files`, `tools`, `provider`, `model_class`, `effort`,
`budget`, `validations`, `action_class` wins.

## Total operation decision table

All six operations may resolve to `AUTO` only after every common predicate and the
operation-specific predicates are true. `AUTO-FIX` is permitted only for
`integrate_owned_delta`; every other operation returns
`OPERATION_CLASS_FORBIDDEN`. A requested `OWNER` remains `OWNER`. The operation name
alone never bypasses a protected boundary.

| Operation | Required operation predicates | Legal autonomous result |
|:--|:--|:--|
| `compile_slice` | Task Contract allows; dependencies ready; input hashes current | `AUTO` |
| `supersede_pending` | prior manifest pending; exact supersedes hash | `AUTO` |
| `dispatch_worker` | durable intent; frozen route | `AUTO` |
| `validate_result` | durable observation; frozen validation argv | `AUTO` |
| `integrate_owned_delta` | exact owned delta; verified backup; serialized writer | `AUTO` or bounded `AUTO-FIX` |
| `project_plan_bookkeeping` | accepted result durable; exact projection | `AUTO` |

The executable bank tests every operation against every action class, every common,
protected, narrowing, and operation predicate, plus precedence multi-fault cases.
This is exhaustive single-fault cartesian coverage; multi-fault cases prove the fixed
first-refusal order. Positive cases exist for every operation, so a block-all
implementation cannot pass.

## Protected boundaries and attention

The first applicable row wins before an allow or requested-OWNER fallback.

| Predicate | Reason | Attention |
|:--|:--|:--|
| security | `PROTECTED_SECURITY` | immediate |
| destructive | `PROTECTED_DESTRUCTIVE` | immediate |
| irreversible, including `reversible == false` | `PROTECTED_IRREVERSIBLE` | immediate |
| external visibility or external-state mutation | `PROTECTED_EXTERNAL` | batched |
| public contract or SemVer | `PROTECTED_PUBLIC_CONTRACT` | batched |
| dependency change | `PROTECTED_DEPENDENCY` | batched |
| package topology | `PROTECTED_PACKAGE_TOPOLOGY` | batched |
| unknown third state | `THIRD_STATE` | batched |
| unknown capability | `UNKNOWN_CAPABILITY` | batched |
| same-level conflict | `SAME_LEVEL_CONFLICT` | batched |
| unresolved routine tie | `ROUTINE_CHOICE_UNRESOLVED` | batched |

No `OWNER` result authorizes a side effect. Immediate attention is restricted to
security, destructive, and irreversible cases. Other owner decisions are ordered by
blocking dependency and batched while independent legal work may continue within its
own frozen budget.

## Common predicates and routine ordering

An autonomous decision requires exact declared scope, reversibility, a known
capability, deterministic unchanged acceptance, current sources, an exact preimage,
and remaining durable budget. Failure returns respectively
`SCOPE_NOT_EXACT`, `PROTECTED_IRREVERSIBLE`, `UNKNOWN_CAPABILITY`,
`ACCEPTANCE_NOT_DETERMINISTIC`, `SOURCE_DRIFT`, `PREIMAGE_MISMATCH`, or
`BUDGET_EXHAUSTED`.

Legal alternatives are compared lexicographically by changed file/behaviour count,
existing primitive first, reversibility, sequential writes, dependency/provider
branch count, deterministic-validation strength descending, and measured token/cost.
The selected and rejected stable IDs are recorded. Equal best ranks return OWNER;
confidence, votes, prose quality, or an LLM tie-break are forbidden.

## Bounded AUTO-FIX

`AUTO-FIX` inherits every AUTO predicate and additionally requires the same stable
finding identity, the same acceptance hash, and durable `retry_count <
same_finding_max`. The frozen cap is `same_finding_max = 2`; the third occurrence or
a retry at or above 2 returns `RETRY_BUDGET_EXHAUSTED` with no inline repair.
Finding identity derives from file, rule/contract locus, and defect class; wording,
severity, report splitting, or reviewer identity cannot change it. A changed identity
returns `FINDING_IDENTITY_CHANGED`; changed acceptance returns `ACCEPTANCE_CHANGED`.
AUTO-FIX may tighten an implementation inside the exact slice, but may not broaden
scope, change permissions/provider/model, weaken tests or acceptance, switch finding
identity, or increase a budget.

## Closed decision record

Every evaluation returns exactly these keys before any side effect:

```text
decision_id
operation
requested_class
resolved_class
allowed
reason_code
attention
controlling_sources
source_set_hash
mandate_hash
selected_alternative
rejected_alternatives
intent_sequence
side_effect_authorized
blast_radius
rollback
affected_slices
no_decision_consequence
blocking_dependencies
```

`side_effect_authorized` equals `allowed` and is always false for OWNER. Hashes are
lowercase SHA-256 over canonical JSON (sorted keys, compact UTF-8). The record stores
typed facts and hashes, never raw prompts, provider streams, secrets, or worker prose.

## P0 compatibility and consumers

The P0.2 case bank predates the operation field. Its compatibility adapter supplies a
neutral operation only for evaluation (`validate_result` for `AUTO`,
`integrate_owned_delta` for `AUTO-FIX`, `project_plan_bookkeeping` for `OWNER`) and
supplies explicit-safe values for predicates absent from the legacy bank. It does not
change any P0 input or expected outcome. The validator loads the adjacent P0 mandate,
re-evaluates every P0 case, and compares the independent expected subset.

`blast_radius`, `rollback`, `affected_slices`, `no_decision_consequence`, and
`blocking_dependencies` are required
bounded packet fields. They are populated from the admitted slice context; an absent value uses
the closed safe default and never authorizes a side effect. P1.4 carries the decision and minimized attention fields; P2.3 implements the same
ordered evaluator; P2.4 schedules only allowed operations; P2.5 exposes decisions;
P3 adapters cannot reinterpret them; P4 proves authority and recovery failures; P5
counts owner attention; P6 may promote without weakening this contract. Executable
conformance is `artifacts/P1/validate-authority-policy.py`; independent expected data
is `artifacts/P1/authority-policy-cases-v1.json`.
