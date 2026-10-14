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
  effect-receipt `expected_prior`/`result`/`precondition.observed_prior`, launch-plan `env` and `config.values`
  (the open map of configuration values; its digest, not its schema, pins the content).
- `canonical_digest(doc)` is sha256 of sorted compact JSON without `digest`, with the `@digest`
  suffix removed from `input_id`; it is computed with the canonical JSON of aicore (`digest/v1`), and the
  `exec/v1` form stays the bare lowercase hex without the `sha256:` tag. A document with a float or a lone surrogate is not canonical JSON:
  `validate` reports `DIGEST_MISMATCH` next to the schema issue.
- Shared definitions (`id`, `sha256`, `ts`, `path`, `provider`, `modelClass`, `effort`, `route`,
  `check`, `support`, `binding`, `roleId`, `commitRole`, `submissionId`, `attemptId`, `callId`, `eventId`,
  `moduleVersion`, `reasonCode`, `skillRef`) live in [`defs.schema.json`](../schemas/exec/v1/defs.schema.json).

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
| `provenance.commit` | | commit that the references of a `plan` input are pinned to |
| `condensed` | | `{produced_by (route), required_digest, parts: [{kind: research\|rationale\|rejected\|other, source: {path, sha256?, section?}, summary}]}`: the optional part condensed by a stage, with references to the originals |

Semantic: digest and `input_id` suffix match; no lifecycle phrases (`LIFECYCLE_LEAK`) outside the
generator name and plan-rule constraints (warning there). `condensed.required_digest` must equal the sha256
of the canonical JSON of the required part (`goal`, `scope`, `acceptance`, `constraints`, `decisions`,
`route`, `result_contract`, `escalation`; absent keys are left out), otherwise `CONDENSED_REQUIRED_DRIFT`. `scope.read_only: true` requires
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
| `version` | | policy version (`MAJOR.MINOR.PATCH`) |
| `sandbox` | | permissions of the stages (`permissions/v1` of aicore: `filesystem`, `network`, `shell`, `env`, `profile`, …); `network` is intent that the provider sandbox enforces for the shell commands of a role, never a limit of the agent process (see `conductor.md`, Sandboxes) |
| `on_error` | | action by failure class: the 12 classes of `error/v1` and `unknown_outcome`, each `{action, max?}` with `action` one of `stop`, `retry`, `retry_after`, `fallback_route`, `replan`, `reconcile` |
| `fallback_routes` | | `{provider, model_class}` routes that `fallback_route` may switch to, in order |
| `budgets` | | `brief_max_bytes`, `packer_input_max_bytes`, `stage_tokens_max` (integers ≥ 0) |
| `stages[].limits` | | `input_tokens_max`, `output_tokens_max` of the stage; `stages[].kind` also accepts `condense` (a model stage that condenses the optional part of a brief) |

Semantic: exactly one `primary`; required stages refuse when unavailable; acyclic known dependencies;
`review.enabled` matches a review stage; integers are non-negative. A `commit` policy with
`git_action: none` is refused with `COMMIT_POLICY_CONFLICT`; `git_action: commit` without the
optional policy remains valid. An `on_error` action `fallback_route` without a non-empty
`fallback_routes` is refused with `FALLBACK_UNDECLARED`; a class that is not listed in `on_error` keeps
the default action of the engine.

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
| `tools` | * | `filesystem`, `shell`, `network`, `plan_api` permissions; `network` is the declared intent: the provider sandbox confines the shell commands of the role, `ro-run.py` restricts only the filesystem writes of the process |
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
| `source` | | how the record was obtained: `declared`, `probed` or `inferred` (`capability-support/v1` of aicore) |
| `observed_at`, `fresh_until` | | when the facts were observed and until when they can be trusted |
| `remediation`, `depends_on` | | what to do to obtain an unsupported capability; capabilities this record depends on |

Semantic: a `declared` record claims `supported` only with `doc` or `code` evidence. `fresh_until` must not
precede `observed_at`, and `source` must agree with `status` (`declared` and `probed` each match their own
status; `inferred` backs only a `declared` record); otherwise `CAPABILITY_FRESHNESS`.

### launch-plan

| Field | Req. | Meaning |
| --- | --- | --- |
| `binding`, `run_id`, `input_digest`, `policy_id`, `dry_run`, `created_at` | * | identity of the prepared run |
| `stages` | * | stage, role, kind, transport; optional provider, model, effort, argv, env (strings), prompt/profile/capability refs, delivery |
| `refusals` | * | excluded stages with capability and reason (may be empty); optional `reason_code` and `chain` (`{capability, reason}` links from the requested capability to the root cause) |
| `submission_id`, `digest`, `modules`, `input_ref` | | submission key; sha256 of the canonical JSON of the plan without `digest`; `{id, version}` of `orch` and `aicore`; brief as `artifact-ref/v1` |
| `digests` | | sha256 of each input: `input`, `policy`, `roles`, `launch_catalog`, `model_catalog`, `capabilities`, `config` (all seven when present) |
| `config` | | `{digest, values}`: the configuration keys that influence preparation, read once |
| `decisions` | | `{stage_id (or *), kind: binding\|route\|policy, chosen, considered: [{candidate, accepted, reason_codes}], tie_break}` |
| `policy_decision` | | `{decision: allow\|refuse, reason_codes, policy_digest}` |
| `proof` | | dry run only: `capabilities` snapshot (`binding`, `provider`, `source`, `observed_at`, `fresh_until`, `stale`) and `warnings` (`{code, message}`) |
| `stages[].delivery.skills` | | `{name, digest}` of each skill delivered to the stage; `stages[].kind` also accepts `condense` |

A refusal of a `required` stage turns the plan into a report: `prepare` raises `CAPABILITY_UNSUPPORTED`.

### run-event

| Field | Req. | Meaning |
| --- | --- | --- |
| `run_id`, `stage_id`, `attempt` (≥ 1), `seq` (≥ 0), `ts`, `kind` | * | ordered event identity |
| `summary`, `data`, `raw_ref`, `route_observed` | | details, raw transport reference, observed route |
| `event_id`, `causation_id`, `correlation_id` | | event key (`evt-…`), key of the causing event, submission (`sub-…`) the event belongs to |
| `owner_epoch` (≥ 1), `attempt_id`, `call_id` | | owner epoch of the producer; attempt (`att-…`) and provider call (`call-…`) keys |
| `error`, `raw` | | failure record (`error/v1` of aicore) for `provider_error`, `quota_block`, `auth_block`, `timeout`, `failed`; raw transport fragment as `artifact-ref/v1` |

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
| `attempt_id`, `owner_epoch` (≥ 1), `submission_id` | | keys of the attempt and of its submission; owner epoch of the producer |
| `input_ref` | | brief given to the stage, as `artifact-ref/v1` |
| `skills`, `modules` | | `{name, digest}` of each skill that took part (tagged digest) and `{id, version}` of each module |
| `errors[].error` | | normalized failure record (`error/v1`); `errors[].class` is unchanged |

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
| `attempt_id`, `owner_epoch` (≥ 1) | | attempt that produced the effect; owner epoch of the producer |
| `precondition` | | `{checked_at, matched}` and optional `observed_prior`, `reason_code`: the re-check made immediately before the effect |

Semantic: an `unknown` outcome needs a reconcile method other than `none`; a precondition that did not match
(`matched: false`) requires outcome `failed`.

### check-evidence

| Field | Req. | Meaning |
| --- | --- | --- |
| `evidence_id`, `check_id`, `subject`, `procedure`, `candidate` | * | which check ran how on which tree |
| `started_at`, `finished_at`, `producer` | * | when and by whom |
| `exit` / `verdict` + `observation` | | command exit, or manual verdict |
| `environment`, `log` | | platform and log digest |

Semantic: a command has `exit` and no verdict; a manual procedure has a verdict and observation and no exit.

### Identity keys

Every level of the idempotency hierarchy has its own key format; the prefix tells the levels apart.

| Level | Field | Format | Repeating the key |
| --- | --- | --- | --- |
| submission | `submission_id` (`correlation_id` on events) | `sub-` + `[A-Za-z0-9._-]` (≤ 120) | `submission_id`: returns the existing run; `correlation_id` only names the submission |
| run | `run_id` | unchanged identifier (new runs of orch: `run-` + 24 hex) | — |
| attempt | `attempt_id` | `att-` + `[A-Za-z0-9._:/-]` (≤ 200) | registration is a no-op |
| call | `call_id` | `call-` + `[A-Za-z0-9._:-]` (≤ 200) | deduplicated in the journal |
| event | `event_id` (`causation_id` names the causing event) | `evt-` + `[A-Za-z0-9._:-]` (≤ 200) | `event_id`: an identical repeat is ignored, different content is a conflict |
| effect | `effect_key` | `<run>:<stage>:<kind>:<target>` | `already_applied` |

Shared definitions added to `defs.schema.json`: `submissionId`, `attemptId`, `callId`, `eventId`,
`moduleVersion`, `reasonCode`, `skillRef`. Fields that reference aicore contracts (`error/v1`,
`artifact-ref/v1`, digest) resolve through the registry of orch, which loads those contracts of aicore.

### Semantic checks of identity and protocol

| Code | Documents | Rule |
| --- | --- | --- |
| `KEY_REUSED` | any document with keys (also launch-plan: `submission_id` against `run_id`) | two keys of `submission_id`, `run_id`, `attempt_id`, `call_id`, `event_id` of one document have the same value |
| `EPOCH_INVALID` | run-event, stage-result, effect-receipt | `owner_epoch` is below 1 |
| `PRECONDITION_MISMATCH` | effect-receipt | `precondition.matched` is false and `outcome` is not `failed` |
| `CONDENSED_REQUIRED_DRIFT` | execution-input | `condensed.required_digest` differs from the digest of the required part |
| `CAPABILITY_FRESHNESS` | capability-record | `fresh_until` precedes `observed_at`, or `source` contradicts `status` |
| `FALLBACK_UNDECLARED` | run-policy | an `on_error` action is `fallback_route` and `fallback_routes` is missing or empty |

## Versioning

A minor change adds only optional fields inside `v1`; `$id` stays the same and the change is recorded
below. A breaking change creates `schemas/exec/v2/` with `contract_version: "exec/v2"`.

## Changelog контрактов

- conductor/v1 — new contract `urn:swissknifeman:orch:conductor` (`run-options`, `stage-report`, `review-findings`,
  `triage-result`, `progress-line`) of the [conductor](conductor.md); `orch.py validate <kind>` accepts these kinds.
- conductor/v1 — optional `issue` fields `class`, `severity`, `outcome`, `auto_fixable`, `evidence` in `stage-report` (a `deviation` needs `class`, `impact`, `outcome`) and the new kind `scout-write-set` (`paths`, `tests`: the optional hint block of the context-scout).
- exec/v1 — `role-manifest.result_shape` accepts `triage-result` (enum widened) and `run-policy.review` has an
  optional `triage` (`role`, `model_class?`); existing documents remain valid.
- work-source/v1 — optional `options` (run-option layers) of a claim, optional `artifacts_dir` of a brief, and the
  op `commit` (`paths`, `actor?` → `committed` \| `no-op` \| `refused`, `sha?`).

- work-source/v1 — new contract `urn:swissknifeman:orch:work-source` (`input`, `output`) of the extension point
  `orch:work-source`: `claim`, `brief` and `register`; exec/v1 does not change.
- exec/v1 — no schema change: preparation now fills the optional launch-plan fields (`digests`, `config`, `modules`, `decisions`, `policy_decision`, `proof`, refusal `reason_code` and `chain`, `delivery.skills`), `stage-result` can carry `skills`, `modules`, `attempt_id` and `owner_epoch`, and `condense` is a prepared model stage; existing documents remain valid.
- exec/v1 — optional `execution-input.provenance.commit` (plan provenance) and `execution-input.condensed`;
  semantic `CONDENSED_REQUIRED_DRIFT`; existing documents remain valid.
- exec/v1 — optional `capability-record.source`, `observed_at`, `fresh_until`, `remediation` and
  `depends_on`; semantic `CAPABILITY_FRESHNESS`; existing documents remain valid.
- exec/v1 — optional `run-policy.version`, `sandbox`, `on_error`, `fallback_routes`, `budgets` and
  `stages[].limits`; `stages[].kind` accepts `condense`; semantic `FALLBACK_UNDECLARED`; existing documents
  remain valid.
- exec/v1 — optional `launch-plan.submission_id`, `digest`, `digests`, `config`, `modules`, `input_ref`,
  `decisions`, `policy_decision`, `proof`, `refusals[].reason_code`, `refusals[].chain` and
  `stages[].delivery.skills`; `stages[].kind` accepts `condense`; `KEY_REUSED` covers the launch plan;
  existing documents remain valid.
- exec/v1 — optional `effect-receipt.attempt_id`, `owner_epoch` and `precondition`
  (`checked_at`, `matched`, `observed_prior`, `reason_code`); semantic `PRECONDITION_MISMATCH`;
  existing documents remain valid.
- exec/v1 — optional `stage-result.attempt_id`, `owner_epoch`, `submission_id`, `input_ref`, `skills`,
  `modules` and `errors[].error`; existing documents remain valid.
- exec/v1 — optional `run-event.event_id`, `causation_id`, `correlation_id`, `owner_epoch`, `attempt_id`,
  `call_id`, `error` and `raw`; semantic `EPOCH_INVALID`; existing documents remain valid.
- exec/v1 — new shared definitions `submissionId`, `attemptId`, `callId`, `eventId`, `moduleVersion`,
  `reasonCode`, `skillRef` and semantic `KEY_REUSED`; existing documents remain valid.
- exec/v1 — `launch-plan.stages[].argv` items may be empty strings (a launch catalog argument such as `--tools ""`); existing documents remain valid.
- exec/v1 — optional `run-policy.isolation` (`mode`, `integration`, `recheck`) and
  `ISOLATION_POLICY_CONFLICT`; existing documents remain valid.
- exec/v1 — optional `run-policy.commit` and `stage-result.commits`, shared `commitRole`,
  commit policy conflict and duplicate hash checks; existing documents remain valid.
- exec/v1 — initial (PLAN2): nine document kinds, shared definitions, closed schema profile and
  semantic checks.
