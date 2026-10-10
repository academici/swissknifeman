# Engine Port

`orch.port` is the boundary between the engine-neutral [exec/v1 contracts](contracts.md) and the
engine bindings `native`, `cao` and `claude-only` (`BINDINGS`). It holds only the protocol, its errors
and the `RunState` reducer; bindings and `prepare_common` arrive in phase P5.3 of the orchestration-prep plan.

Invariant: one run has one workflow owner. A binding never calls another binding; the CAO adapter does
not start the native engine; Claude-only is a human or Claude session that receives a prompt and
returns a report.

## Operations

`EnginePort` is a `runtime_checkable` `typing.Protocol`:

| Operation | Returns | Plan 1 |
| --- | --- | --- |
| `binding` | `"native"`, `"cao"` or `"claude-only"` | attribute |
| `capabilities()` | capability-record list (`declared` or `probed`) | seeds |
| `prepare(input_doc, policy, roles, *, provider=None, dry_run=True)` | launch-plan | dry run only |
| `run(launch_plan)` | run id | `NOT_IMPLEMENTED` |
| `watch(run_id)` | iterator of run-events | `NOT_IMPLEMENTED` |
| `cancel(run_id)` | `{"run_id", "cancelled": [stage_id], "unknown": [stage_id]}` | `NOT_IMPLEMENTED` |
| `resume(run_id)` | run id, or `RESUME_REFUSED` | `NOT_IMPLEMENTED` |
| `results(run_id)` | `{"stage_results": [...], "effect_receipts": [...]}` | `NOT_IMPLEMENTED` |

`prepare` (phase P5.3) validates the input, policy and role manifests, orders stages by `depends_on`,
enforces the minimum route of the primary stage, matches each model stage against the
`(binding, provider)` capability record (a missing record counts as `unknown`), and resolves models only
through the model catalog of aicore (`--model-catalog`). An unmet requirement of a `required` stage raises
`CAPABILITY_UNSUPPORTED`; an optional stage becomes a refusal. Provider and model are never replaced
silently.

## Errors

`PortError(code, message, data=None)` exposes `code`, `message` and `data`; a code outside
`PORT_ERROR_CODES` is a programming error (`ValueError`). The table order is the tuple order.

| Code | When |
| --- | --- |
| `INPUT_INVALID` | execution-input or run-event fails the schema or semantic checks; a stage event is inconsistent |
| `POLICY_INVALID` | run-policy fails the schema or semantic checks |
| `ROLE_UNKNOWN` | a stage refers to a role without a manifest |
| `ROUTE_UNDERSHOOT` | the primary stage class is below `input.route.minimum.class` |
| `CAPABILITY_UNSUPPORTED` | a `required` stage needs an `unsupported` or `unknown` capability; `data.launch_plan` holds the report |
| `RESUME_REFUSED` | input, policy, instruction or route hashes drifted before resume |
| `RUN_UNKNOWN` | unknown run id, or an event of another run |
| `NOT_IMPLEMENTED` | an execution operation in Plan 1 (`run`, `watch`, `cancel`, `resume`, `results`, `prepare(dry_run=False)`) |
| `SEQ_ORDER` | reducer: `seq` repeated with other content, or lower than the last seen |
| `AFTER_TERMINAL` | reducer: an event of an attempt that already ended, or a retry after `completed`/`cancelled` |

## States

`RunState(run_id)` folds run-events without I/O or the system clock; every value comes from events.
An event is fully checked before any change, so a rejected event leaves the state untouched.
Retained event data is copied: modifying an event after `apply()` cannot change the reduced result.

- `apply(event)` validates the event against `run-event` (`INPUT_INVALID`), its `run_id`
  (`RUN_UNKNOWN`) and its `seq`. The key is `(run_id, seq)`: an identical replay is ignored, other
  content under a seen `seq` or a lower `seq` is `SEQ_ORDER`. Gaps are allowed.
- `close()` ends the stream: a `running` stage becomes `unknown_outcome` with error
  `{class: transport, message: "stream ended without terminal event"}`. End of stream is never success.
- `stages()` returns copies: `stage_id → {status, attempt, last_seq, last_ts, route_observed, errors}`.
- `stage_result(stage_id, *, role, requested_route, input_digest, instructions_digest)` builds a
  schema-valid skeleton stage-result of the latest attempt; a running or unknown stage is `INPUT_INVALID`.

| Event kind | Effect |
| --- | --- |
| `started` | `running`. Attempt 1 for a new stage; attempt `prev + 1` after `failed`, `timeout`, `quota_blocked`, `auth_blocked` or `unknown_outcome`; errors and usage start empty |
| `model_wait`, `output`, `tool`, `question`, `check` | status unchanged; `last_ts` moves (silence timeout) |
| `provider_error` | status unchanged; adds error class `provider` |
| `quota_block` | terminal `quota_blocked`, error class `quota` — not a task failure |
| `auth_block` | terminal `auth_blocked`, error class `auth` — not a task failure |
| `timeout` | terminal `timeout`, error class `timeout` |
| `cancelled`, `failed`, `unknown_outcome` | terminal status of the same name |
| `completed` | terminal `completed`; usage from its `data.usage` |

A stage accepts only `started` before its first attempt; an event for a later attempt that has not
started is `INPUT_INVALID`. Any new event for an ended attempt, including a delayed `started`, is
`AFTER_TERMINAL`; an identical replay is still ignored. `route_observed` from any event becomes
`route.observed` with `source: "event"`. Usage is `{"status": "reported"}` with integer `input_tokens`/`output_tokens` taken
from the last `completed.data.usage`, otherwise `{"status": "unknown"}` without numbers.

## Binding matrix

Data: [`bindings/matrix.json`](../bindings/matrix.json). Values: `supported`, `adapted`, `unsupported`,
`unknown`; `skill_delivery` uses capability-record `skill_delivery.mode` values. A native value refers to
the provider's main transport; `by_provider` overrides it per provider. Grok stays `unknown` until a
Plan 2 probe.

| Capability | native | cao | claude-only |
| --- | --- | --- | --- |
| `prepare` | supported | supported (profile dry-render) | supported (prompt render) |
| `run` | supported (Plan 2) | adapted (`cao launch`, tmux) | adapted (session executes the prompt) |
| `watch` | supported (JSONL/ACP events) | adapted (TUI status; parse failure → `unknown_outcome`) | unsupported |
| `cancel` | supported for every provider (process group SIGTERM → SIGKILL) | adapted (`cao shutdown`) | unsupported |
| `resume` | adapted (session resume + hash check); grok unknown | adapted (workflow replay) | unsupported |
| `results` | supported | adapted (CAO response normalization) | adapted (report → stage-result) |
| `model_set` | supported (claude, codex `--model`); grok unknown | supported (profile `model`) | unsupported (session model) |
| `model_observe` | supported (claude `system/init`); codex adapted; grok unknown | adapted | adapted (report) |
| `effort_set` | supported (claude `--effort`, codex `model_reasoning_effort`); grok unknown | adapted (claude, codex); grok unsupported | unsupported |
| `skill_delivery` | claude `native_plugin_dir`; codex `isolated_home` (auth copied); grok unknown | `profile_skills` (advertised, not an ACL) | `project_dir` / `prompt_inline` |
| `tool_restrictions` | supported (claude `--tools`, codex `--sandbox`); grok unknown | adapted (`allowedTools`/role) | unsupported (prompt-only) |
| `plan_write_prevention` | adapted (tools + sandbox; shell can still write) | adapted | unsupported |
| `usage` | supported (claude `result`, codex `turn.completed`); grok unknown | unknown | unknown |
| `effects` | supported (receipts written by orch) | adapted (outside CAO memoization) | unsupported (registrar records) |
| `stream_live` | supported | adapted | unsupported |

## Adding an engine

1. Add the value to `defs.binding` (a minor exec/v1 change) and record it in the contract changelog.
2. Add `orch/bindings/<name>.py` implementing `EnginePort`; `prepare` calls `prepare_common`.
3. Add capability seeds `bindings/capabilities/<name>--<provider>.json` (`declared`, with evidence).
4. Add a column to `bindings/matrix.json` and to the table above; the matrix test requires every cell.
5. Add the binding to `BINDINGS`; the conformance test is parameterized by it.
6. Do not change the plan store, the skill catalog or the input, policy and role schemas: needing that is a contract defect.
