# Dispatch Admission Contract v1

## Status, authority, and version

`dispatch-admission-v1` is frozen at `1.0.0`. It owns the additive
`dispatch-task-manifest-v1` child-activity form, owner-bounded dispatch grants,
strict-replay usage projection, and the total pre-intent admission decision. It
does not replace `slice-manifest-v1`, change a plan item, launch a provider,
persist provider output, accept work, or create business authority.

Normative upstream owners are `supervisor-run-v1/1.0.0`,
`slice-manifest-v1/1.0.0`, `authority-policy-v1/1.0.0`, and
`worker-envelope-v1/1.0.0`. Consumers pin the contract version and content hash.
The frozen P3 readiness authority is owner decision `D74`; it is not reusable
for P5 or another provider.

## Closed child-task manifest

<!-- declared-set: task_keys -->
```text
schema_version
manifest_version
task_id
task_hash
purpose
provider
parent_plan_id
parent_item_id
parent_task_contract_hash
workspace
permissions
prompt
response_schema
outputs
budgets
source_hashes
```

`schema_version` is `dispatch-task-manifest-v1`; `manifest_version` is `1.0.0`.
`task_hash` is SHA-256 of canonical JSON for the complete row with `task_hash`
omitted: sorted keys, compact UTF-8, and no insignificant whitespace. A task is
a child activity, never a plan-item slice. `parent_item_id=P3.4` is linkage only;
the task hash must differ from the exact built P3.4 Task Contract hash, and a
P3.4 Task Contract or `slice-manifest-v1` value is refused as a dispatch task.

`purpose` is exactly `provider-readiness-smoke`. `provider` is exactly one of
`codex|claude-code`. `workspace` is closed to `kind`, `creation`, `preimage`, and
`postimage`: the values are respectively `temporary-empty-git`, `fresh-per-attempt`,
`empty-git-tree`, and `equals-preimage`. `permissions` is closed to ordered,
duplicate-free `reads`, `writes`, and `tools`; all three are empty for P3 smoke.

`prompt` is closed to `id` and `content_hash`; the prompt body is not stored.
`response_schema` is closed to `id` and `content_hash`. `outputs` is the exact
ordered minimized set `provider_id`, `binary_version_hash`, `exit_class`,
`reason_code`, `schema_valid`, `project_delta`, and `duration_ms`; raw streams,
prompts, transcripts, tool payloads, private reasoning, environment values, and
credentials are forbidden.

`budgets` is closed to `max_slices`, `timeout_ms`, `max_envelope_bytes`,
`max_event_count`, `max_turns`, `max_output_bytes`, `token_limit`, and
`cost_limit_microunits`. Every value is a positive finite integer and
`max_slices=1`; null, missing, boolean, zero, negative, or unknown hard limits
refuse. `source_hashes` is closed to `plan`, `p3_phase`, `provider_matrix`,
`worker_contract`, and `parity`; every value is lowercase SHA-256.

## Closed owner grant

<!-- declared-set: grant_keys -->
```text
schema_version
grant_version
grant_id
grant_hash
owner_decision
purpose
task_id
task_hash
provider
route
capabilities
workspace
permissions
budgets
max_slices
revoked
```

`schema_version` is `dispatch-grant-v1`; `grant_version` is `1.0.0`;
`grant_hash` uses the same canonical rule with itself omitted. The grant pins
`owner_decision=D74`, purpose, one exact task row/hash, one provider, exact route
and capabilities, identical workspace/permissions/budgets, `max_slices=1`, and
`revoked=false`. No grant is reusable across providers or task revisions.

## Replay-owned usage and admission

A runtime dispatch manifest adds exactly `run_id`, `slice_id`, `attempt`,
`idempotency_key`, current source hashes, and references to one frozen task and
grant. `attempt` is positive; the idempotency key and all hashes are lowercase
SHA-256. Strict replay is the only usage owner and returns exact prior
`dispatch_intent` identities and per-grant slice count. Caller-provided usage,
reset, summary, or inferred zero is refused.

An admission copies, without widening, task/provider/purpose/route/capabilities,
workspace, permissions, budgets, source hashes, run/slice/attempt/idempotency,
task/grant hashes, and replay-derived usage. The order is fixed:

1. validate the closed task and its hash;
2. validate the closed grant, D74, hash, purpose, provider, and exact task binding;
3. validate runtime identity and current source hashes;
4. replay the durable journal and derive usage;
5. require `used_slices < max_slices` and no duplicate idempotency identity;
6. emit the content-addressed admission before any intent or provider activity.

## Total pre-intent refusals

<!-- declared-set: refusal_reasons -->
```text
UNKNOWN_SCHEMA_VERSION
UNKNOWN_FIELD
TASK_HASH_MISMATCH
PARENT_ITEM_AS_TASK
PURPOSE_MISMATCH
PROVIDER_MISMATCH
WORKSPACE_NOT_TEMPORARY_EMPTY
SCOPE_NOT_EMPTY
PROMPT_MISMATCH
SCHEMA_MISMATCH
OUTPUTS_MISMATCH
CAP_INVALID
SOURCE_HASH_MISMATCH
GRANT_NOT_FOUND
GRANT_HASH_MISMATCH
GRANT_SCOPE_MISMATCH
GRANT_REVOKED
IDENTITY_MISMATCH
REPLAY_INVALID
USAGE_CALLER_SUPPLIED
USAGE_LIMIT_EXCEEDED
BUSINESS_AUTHORITY_REQUIRED
```

The first applicable refusal in task → grant → identity/source → replay/usage
order wins before `append_intent` or process launch. P3.4 item/task-contract hashes,
business purpose, P5 carriers, provider mismatch, non-empty scope, changed schema
or outputs, widened caps, unknown hard limits, caller usage, and grant reuse all
refuse. Failure produces a typed reason and no admission, intent, evidence row, or
provider activity.

## Frozen P3 smoke carriers and consumers

`artifacts/P1/p3-smoke-task-set-v1.json` contains exactly
`p3-smoke-codex-v1` and `p3-smoke-claude-code-v1`.
`artifacts/P1/p3-smoke-dispatch-grants-v1.json` contains exactly one D74 grant
per task/provider. `artifacts/P1/dispatch-admission-cases-v1.json` supplies one
neutral admission input plus independent mutations; its validator does not branch
on case IDs.

P2.6 is the only concrete manifest/replay/admission producer. P3.4 consumes only
the resulting provider-specific admission index and cannot construct or modify
authority, budget, usage, or grant data. P5 needs a separate business owner grant.
