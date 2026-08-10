# Worker Envelope Contract v1

## Status, authority, and version

`worker-envelope-v1` is frozen at `1.0.0`. It owns the provider-neutral worker request,
normalized event and terminal result shapes, the closed exit taxonomy, evidence caps,
provider-mapping boundary, and minimized trace linkage. It does not own slice compilation,
authority or retry decisions, provider argv/parser implementations, supervisor recovery,
independent acceptance, or economy formulas.

Normative inputs are `supervisor-run-v1/1.0.0`, `slice-manifest-v1/1.0.0`,
`authority-policy-v1/1.0.0`, the terminal P0.3 provider matrix and probes, the Artifex
acceptance rubric, and unified-agent-trace-v1 identity/privacy boundaries. Provider-specific
fields are additive adapter evidence: they never alter a neutral field or exit meaning.
Consumers pin both contract version and content hash.

A major change adds, removes, or renames a required key, event, exit, support state, or reason,
or changes an existing classification. A minor change adds optional bounded evidence without
changing an old outcome. A patch changes diagnostics only. Unknown versions and keys fail
closed.

## Closed envelope and request

<!-- declared-set: envelope_keys -->
```text
schema_version
contract_version
request
events
result
```

`schema_version` is `worker-envelope-v1`; `contract_version` is `1.0.0`. `request` is
immutable after dispatch intent, `events` are ordered observations, and `result` is exactly one
terminal worker observation. The envelope is evidence, never an acceptance decision.

<!-- declared-set: request_keys -->
```text
schema_version
request_id
run_id
slice_id
attempt
idempotency_key
trace_id
provider
route
permissions
bundle
budgets
child_policy
redaction_policy_hash
created_at
```

All IDs are non-empty stable strings; `attempt` is positive. `idempotency_key`, `trace_id`,
every content/policy hash, and every pinned contract hash are lowercase SHA-256. The request
links the same `run_id`, `slice_id`, `attempt`, `idempotency_key`, and `trace_id` carried by every
event and by the result. No provider session ID replaces these identities.

`provider` is closed to `id`, `cli_version`, `mapping_id`, `mapping_version`,
`mapping_state`, and `degraded_route_grant_hash`. Provider IDs are `codex` and
`claude-code`. The mapping state uses the declared support vocabulary below. A degraded mapping
or required degraded capability needs a non-null Owner-authorized hash fixed before dispatch.
Unsupported or unknown required capability cannot be hidden behind a fallback.

`route` is closed to `model_class`, `model`, `effort`, and `capabilities`. Each capability row is
closed to `id`, `state`, `required`, `source`, and `unknown_reason`. State must preserve the P0.3
observation for that provider. `unknown_reason` is non-empty exactly for `unknown`; it is null for
the other states. A provider adapter may add native details outside this neutral envelope, but it
must project the exact neutral row without changing it.

<!-- declared-set: support_states -->
```text
supported
degraded
unsupported
unknown
```

`permissions` is closed to `authority_profile`, `approval_mode`, `sandbox_mode`,
`network_mode`, `filesystem_scope_hash`, and `source`. Approval, sandbox, network, trust, and
authority remain separate axes. Provider labels are mapped into these neutral values by P3; an
unknown axis stays `unknown` and never widens authority.

`bundle` is closed to `slice_manifest_hash`, `task_contract_hash`, `authority_policy_hash`,
`output_schema_hash`, `validation_hash`, and ordered `content_refs`. A content reference is a
repo-relative identifier plus its SHA-256; request content itself is not stored in the envelope.

`budgets` is closed to `timeout_ms`, `max_envelope_bytes`, `max_event_count`, `max_turns`,
`max_output_bytes`, `token_limit`, `token_limit_unknown_reason`, `cost_limit_microunits`, and
`cost_limit_unknown_reason`. Numeric caps are positive. A null token or cost limit requires a
non-empty reason and means unknown, not zero or unlimited. Caps are checked before storage; an
over-cap observation retains counts and hashes only and returns `budget_exhausted`.

`child_policy` is closed to `mode`, `max_children`, and `allowed_capabilities`. Mode is
`forbidden` or `bounded_read_only`. `forbidden` requires zero and an empty list. The bounded mode
requires a positive finite ceiling and may name only capabilities already supported by the
request. Child output crosses the same schema, privacy, byte, event, turn, and accounting gates.

## Normalized events

Every event is a closed object with exactly:

<!-- declared-set: event_keys -->
```text
schema_version
sequence
event_type
occurred_at
request_id
run_id
slice_id
attempt
idempotency_key
trace_id
provider_id
provider_event_type
provider_event_type_unknown_reason
turn_index
usage
usage_unknown_reason
diagnostic_code
diagnostic_hash
```

`schema_version` is `worker-event-v1`; `sequence` starts at 1 without gaps; timestamps are UTC
ISO-8601. Provider event type, usage, turn index, and diagnostics are bounded observations. A null
provider event or usage has a non-empty unknown reason; a present value has a null reason. Raw
provider events and diagnostic text are never stored. `diagnostic_hash` hashes only an approved
bounded diagnostic, never a secret or excluded raw payload.

<!-- declared-set: event_types -->
```text
worker_started
session_observed
turn_started
turn_finished
output_observed
usage_observed
permission_denied
capability_observed
provider_diagnostic
worker_finished
```

Unknown provider event types map to `provider_diagnostic` with a bounded stable code and
`provider_event_type_unknown_reason`; they never map to success. Event absence is not proof that
an action did not occur.

## Terminal result and closed exits

The result is closed to:

<!-- declared-set: result_keys -->
```text
schema_version
request_id
run_id
slice_id
attempt
idempotency_key
trace_id
provider_id
worker_succeeded
acceptance_state
exit_class
reason_code
output
usage
event_count
turn_count
duration_ms
diagnostic_codes
redaction
```

`schema_version` is `worker-result-v1`. `worker_succeeded` is true only for `success`; it says the
worker envelope ended successfully, not that the slice is accepted. `acceptance_state` is always
`not_evaluated`; only the independent validator/arbiter may append acceptance under
`supervisor-run-v1`.

<!-- declared-set: exit_classes -->
```text
success
schema_failure
permission_denied
timeout
quota_exhausted
budget_exhausted
capability_unsupported
provider_failure
internal_failure
orphaned
```

<!-- declared-set: reason_codes -->
```text
OK
OUTPUT_SCHEMA_INVALID
PERMISSION_REFUSED
WALL_TIMEOUT
PROVIDER_QUOTA
BUDGET_TIMEOUT
BUDGET_ENVELOPE_BYTES
BUDGET_OUTPUT_BYTES
BUDGET_EVENT_COUNT
BUDGET_TURN_COUNT
BUDGET_TOKEN_LIMIT
BUDGET_COST_LIMIT
CAPABILITY_UNSUPPORTED
CAPABILITY_UNKNOWN
DEGRADED_ROUTE_NOT_AUTHORIZED
PROVIDER_UNAVAILABLE
PROVIDER_NONZERO
PROVIDER_PROTOCOL_UNKNOWN
MAPPING_UNKNOWN
INTERNAL_VALIDATOR
PRIVACY_REFUSED
UNKNOWN_SCHEMA_VERSION
UNKNOWN_FIELD
LINKAGE_MISMATCH
PROVIDER_EVIDENCE_MISMATCH
ORPHAN_CONFIRMED
ORPHAN_IDENTITY_UNKNOWN
```

The exit-to-reason mapping is total: `success→OK`; `schema_failure→OUTPUT_SCHEMA_INVALID`;
`permission_denied→PERMISSION_REFUSED`; `timeout→WALL_TIMEOUT`;
`quota_exhausted→PROVIDER_QUOTA`; `budget_exhausted→BUDGET_*`;
`capability_unsupported→CAPABILITY_*|DEGRADED_ROUTE_NOT_AUTHORIZED`;
`provider_failure→PROVIDER_*|MAPPING_UNKNOWN`;
`internal_failure→INTERNAL_VALIDATOR|PRIVACY_REFUSED|UNKNOWN_SCHEMA_VERSION|UNKNOWN_FIELD|
LINKAGE_MISMATCH|PROVIDER_EVIDENCE_MISMATCH`; and
`orphaned→ORPHAN_CONFIRMED|ORPHAN_IDENTITY_UNKNOWN`. Unknown source combinations use
`provider_failure/PROVIDER_PROTOCOL_UNKNOWN`, never a guessed success.

`output` is closed to `status`, `schema_hash`, `content_hash`, `bytes`, and `stored_ref`.
Status is `valid`, `invalid`, or `absent`. Valid output requires the frozen schema hash, a content
hash, a non-negative byte count within cap, and a minimized stored reference. Invalid or absent
output carries no raw bytes. `usage` is closed to `input_tokens`, `cached_input_tokens`,
`output_tokens`, `reasoning_tokens`, and `cost_microunits`; each observation is closed to `value`,
`unit`, `source`, and `unknown_reason`. A value is a non-negative integer with null reason; null
requires a non-empty source-specific reason. Missing accounting never becomes zero.

`redaction` is closed to `status`, `excluded_classes`, `excluded_count`, and
`refused_key_count`. Excluded classes are the fixed set `raw_provider_stream`, `request_content`,
`private_reasoning`, `tool_input_output`, `credential`, and `environment_value`. Only a clean
result may be stored. A detected excluded key or value returns
`internal_failure/PRIVACY_REFUSED` before persistence; hashes of credentials are also forbidden.

## Mapping and refusal order

Adapters first verify request linkage and caps, then map provider observations, then emit the
neutral result. Mapping rows are versioned, provider-qualified, and exhaustive over observed
source combinations. The first refusal order is: privacy; schema/version/closed fields; identity
linkage; evidence-state preservation; degraded-route authorization; envelope/output/event/turn
caps; exit/reason consistency. Provider zero exit, non-empty output, permission success, or
sandbox success never implies neutral success or acceptance.

Current P0.3 facts remain exact: Codex child control, cache and cost are unknown; Claude Code
structured output is degraded, ephemeral session is unsupported, cache is unknown, and its
bounded local run observed an authentication/access failure. The contract records these facts; it
does not claim parity or infer future adapter behavior.

## Executable conformance carrier and consumers

`artifacts/P1/worker-envelope-cases-v1.json` is synthetic contract evidence, not a live provider
capture. It contains one neutral base envelope and generic JSON-pointer mutations with independent
expected outcomes. `artifacts/P1/validate-worker-envelope.py` applies mutations without branching
on case names, checks this contract's declared sets against its own closed schema, verifies both
P0.3 provider rows, and proves privacy, linkage, cap, unknown-preservation, degraded-route, mapping,
and every exit-class boundary.

P1.5 consumes only bounded usage/unknown facts. P2 compiles and stores the neutral shapes. P3
owns exact provider argv, parsers, mapping tables, process lifecycle, and version probes. P4 proves
timeouts, orphans, privacy, effective permissions, and unknown combinations. P5 measures accepted
results only after independent validation. No consumer may persist excluded data or reinterpret an
exit as acceptance.
