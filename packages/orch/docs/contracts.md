# exec/v1 contracts

Engine-neutral documents exchanged between plan bridges, roles and engine bindings. The schemas in
`schemas/exec/v1/` are the source of truth; this page is a short map.
Engine operations and run states are described in [engine-port.md](engine-port.md).

## Conventions

- JSON Schema draft 2020-12 in the closed keyword profile of the aicore validator (`orch.schema` re-exports `aicore.util.schema`; orch keeps no profile of its own).
  Numeric bounds and cross-field rules are semantic checks in `orch.contracts.semantic_checks`.
- Every document carries `$schema` (`urn:swissknifeman:orch:exec:<kind>:v1`) and
  `contract_version: "exec/v1"`. An unknown version is refused with `CONTRACT_VERSION`.
- Objects are closed (`additionalProperties: false`) except `extensions`, run-event `data`,
  effect-receipt `expected_prior`/`result` and launch-plan `env`.
- `canonical_digest(doc)` is sha256 of sorted compact JSON without `digest`, with the `@digest`
  suffix removed from `input_id`; it is computed with the canonical JSON of aicore (`digest/v1`), and the
  `exec/v1` form stays the bare lowercase hex without the `sha256:` tag. A document with a float is not canonical JSON:
  `validate` reports `DIGEST_MISMATCH` next to the schema issue.
- Shared definitions (`id`, `sha256`, `ts`, `path`, `provider`, `modelClass`, `effort`, `route`,
  `check`, `support`, `binding`, `roleId`, `commitRole`) live in [`defs.schema.json`](../schemas/exec/v1/defs.schema.json).

Validate a document: `python3 packages/orch/scripts/orch.py validate <kind> <file.json>`.
Diagnostics include `path`, `code`, `message` and `level`. Warning-only documents return exit 0;
errors return exit 1. `--quiet` suppresses stdout while preserving diagnostics and the exit status.

## Documents

| Kind | Written by | Read by | Purpose |
| --- | --- | --- | --- |
| [`execution-input`](../schemas/exec/v1/execution-input.schema.json) | plan bridge `brief`, ad-hoc/review input | engine, prompt render, role | What to do: goal, scope, acceptance, minimum route, result contract |
| [`run-policy`](../schemas/exec/v1/run-policy.schema.json) | owner/config, outside plan JSON | engine | Stage pipeline, review limits, retries, git and finalize actions |
| [`role-manifest`](../schemas/exec/v1/role-manifest.schema.json) | orch `roles/` | binding, skill resolver | Instruction references, skills, tool permissions, write authority |
| [`capability-record`](../schemas/exec/v1/capability-record.schema.json) | binding seeds, probes | `prepare` | What one binding × provider × CLI version supports |
| [`launch-plan`](../schemas/exec/v1/launch-plan.schema.json) | `EnginePort.prepare` | `run`, reviewer | Resolved stages with argv/profile/prompt and refusals |
| [`run-event`](../schemas/exec/v1/run-event.schema.json) | binding `watch` | `RunState` | Normalized event of a running stage |
| [`stage-result`](../schemas/exec/v1/stage-result.schema.json) | `RunState.stage_result`, binding | coordinator, registrar | Outcome of one stage attempt |
| [`effect-receipt`](../schemas/exec/v1/effect-receipt.schema.json) | engine | engine, reconcile | Idempotent record of an external effect |
| [`check-evidence`](../schemas/exec/v1/check-evidence.schema.json) | engine, executor, human | plan store `finish`, reviewer | Proof that an acceptance check ran on a candidate tree |

### execution-input

| Field | Req. | Meaning |
| --- | --- | --- |
| `input_id`, `digest` | * | `<ref>@<digest[:12]>`; canonical digest of the document |
| `provenance` | * | one of `plan` (plan, item, unit, source digest, generator), `adhoc`, `review` |
| `goal`, `scope` | * | expected result; `include`, `exclude`, `write_set`, `read_only` |
| `acceptance` | * | `checks` (each has exactly one of `cmd`/`procedure`), `deliverables` |
| `route` | * | `minimum` route: class and effort, never bypassed |
| `result_contract` | * | report fields, `write_authority`, `commit_owner: coordinator`, `plan_mutation: forbidden` |
| `why`, `guidance`, `sections`, `constraints`, `decisions`, `reads`, `context_refs`, `upstream`, `lessons`, `hints`, `escalation` | | full item context, never truncated |

Semantic: digest and `input_id` suffix match; no lifecycle phrases (`LIFECYCLE_LEAK`) outside the
generator name and plan-rule constraints (warning there). `scope.read_only: true` requires
`result_contract.write_authority: "none"`; contradictory authority is refused with `INPUT_AUTHORITY`.

### run-policy

| Field | Req. | Meaning |
| --- | --- | --- |
| `policy_id`, `description` | * | profile identity (`solo`, `scout-solo`, `frontend-bounded`, `review-only`) |
| `stages` | * | `id`, `kind`, `role`, `required`, `on_unavailable`; optional class, effort, provider, `depends_on`, retries, timeouts |
| `review` | * | `enabled`, `independent_provider`, `max_rounds` ≤ 2, `max_corrections` ≤ 1 |
| `retries_budget`, `git_action`, `finalize` | * | retry total, `none`/`commit`, deterministic registration |
| `applies_to` | | reference patterns |
| `commit` | | `scope: item\|unit`, distinct non-empty `roles` (`executor`, `reviewer`, `fix`), `message_convention` identifier; all three fields required when present |
| `isolation` | | `mode: worktree\|shared`, `integration: sequential`, `recheck: item\|all\|none`; all three fields required when present |

Semantic: exactly one `primary`; required stages refuse when unavailable; acyclic known dependencies;
`review.enabled` matches a review stage; integers are non-negative. A `commit` policy with
`git_action: none` is refused with `COMMIT_POLICY_CONFLICT`; `git_action: commit` without the
optional policy remains valid.

`isolation.mode: worktree` means one branch and working tree per run; results are integrated one branch
at a time (`integration: sequential`), and `recheck` sets the acceptance scope re-run after each
integration. `shared` works in the common tree, and such runs must not execute in parallel. A
`worktree` isolation with `git_action: none` is refused with `ISOLATION_POLICY_CONFLICT` because there is
nothing to integrate; documents without `isolation` remain valid.

### role-manifest

| Field | Req. | Meaning |
| --- | --- | --- |
| `role_id`, `title`, `description` | * | identity |
| `instructions` | * | repository paths of canonical texts (no copied bodies) |
| `tools` | * | `filesystem`, `shell`, `network`, `plan_api` permissions |
| `write_authority`, `result_shape`, `model_class_min`, `forbidden_inputs` | * | authority and output shape |
| `skills`, `agent_pack_roles` | | required/optional skills; link to agent-pack roles |

Semantic: `plan` authority ⇔ `plan_api: write`; `none` authority forbids filesystem writes.

### capability-record

| Field | Req. | Meaning |
| --- | --- | --- |
| `binding`, `provider`, `cli`, `status`, `recorded_at` | * | what was described and how (`declared` or `probed`) |
| `transport`, `auth_route`, `terminal_signal` | * | how the binding talks to the provider |
| `model`, `effort` | * | `set` and `observe` support |
| `stream`, `attach`, `cancel`, `resume`, `usage`, `plan_write_prevention` | * | support values |
| `restrictions`, `skill_delivery` | * | tool/sandbox enforcement; skill delivery mode |
| `evidence` | * | at least one `doc`, `perplexity`, `probe` or `code` source |

Semantic: a `declared` record claims `supported` only with `doc` or `code` evidence.

### launch-plan

| Field | Req. | Meaning |
| --- | --- | --- |
| `binding`, `run_id`, `input_digest`, `policy_id`, `dry_run`, `created_at` | * | identity of the prepared run |
| `stages` | * | stage, role, kind, transport; optional provider, model, effort, argv, env (strings), prompt/profile/capability refs, delivery |
| `refusals` | * | excluded stages with capability and reason (may be empty) |

A refusal of a `required` stage turns the plan into a report: `prepare` raises `CAPABILITY_UNSUPPORTED`.

### run-event

| Field | Req. | Meaning |
| --- | --- | --- |
| `run_id`, `stage_id`, `attempt` (≥ 1), `seq` (≥ 0), `ts`, `kind` | * | ordered event identity |
| `summary`, `data`, `raw_ref`, `route_observed` | | details, raw transport reference, observed route |

`quota_block`, `auth_block` and `provider_error` are not task failures. A raw event that cannot be
parsed becomes `unknown_outcome`, never `completed`.

### stage-result

| Field | Req. | Meaning |
| --- | --- | --- |
| `run_id`, `stage_id`, `attempt`, `role`, `status` | * | which attempt ended how |
| `route` | * | `requested`; optional `resolved` and `observed` with its `source` |
| `hashes` | * | `input` (= execution-input digest), `instructions`, optional `policy` |
| `usage` | * | `reported` with numbers, or `unknown` without numbers (unknown ≠ 0) |
| `commits` | | optional array of `{sha, role, ref, paths_digest}`; all four fields required per entry; roles are `executor`, `reviewer`, `fix` |
| `session`, `changed_paths`, `artifacts`, `checks`, `errors`, `report`, `started_at`, `finished_at` | | evidence of the attempt |

Semantic: `completed` has no `parse` error; `cost_usd` is a decimal string. Commit hashes must
be unique (`COMMIT_SHA_DUPLICATE`). `paths_digest` is lowercase SHA-256 of the UTF-8 string
formed by sorting repository-relative POSIX paths and joining them with `\n`, without a trailing
newline. For `a.py` and `b.py`, hash the bytes `a.py\nb.py`.

### effect-receipt

| Field | Req. | Meaning |
| --- | --- | --- |
| `effect_key`, `kind`, `intent`, `precondition_checked` | * | `<run>:<stage>:<kind>:<target>` and the expected prior state |
| `outcome`, `reconcile`, `recorded_at` | * | `applied`, `already_applied`, `failed` or `unknown`; how to reconcile |
| `result` | | open result object |

Semantic: an `unknown` outcome needs a reconcile method other than `none`.

### check-evidence

| Field | Req. | Meaning |
| --- | --- | --- |
| `evidence_id`, `check_id`, `subject`, `procedure`, `candidate` | * | which check ran how on which tree |
| `started_at`, `finished_at`, `producer` | * | when and by whom |
| `exit` / `verdict` + `observation` | | command exit, or manual verdict |
| `environment`, `log` | | platform and log digest |

Semantic: a command has `exit` and no verdict; a manual procedure has a verdict and observation and no exit.

## Versioning

A minor change adds only optional fields inside `v1`; `$id` stays the same and the change is recorded
below. A breaking change creates `schemas/exec/v2/` with `contract_version: "exec/v2"`.

## Changelog контрактов

- exec/v1 — `launch-plan.stages[].argv` items may be empty strings (a launch catalog argument such as `--tools ""`); existing documents remain valid.
- exec/v1 — optional `run-policy.isolation` (`mode`, `integration`, `recheck`) and
  `ISOLATION_POLICY_CONFLICT`; existing documents remain valid.
- exec/v1 — optional `run-policy.commit` and `stage-result.commits`, shared `commitRole`,
  commit policy conflict and duplicate hash checks; existing documents remain valid.
- exec/v1 — initial (PLAN2): nine document kinds, shared definitions, closed schema profile and
  semantic checks.
