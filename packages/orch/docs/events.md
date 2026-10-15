# Events

orch journals seventeen events of module `orch` through the `aicore` event journal. The data of each type is a closed
JSON Schema under `schemas/event-data/v1/<type>.schema.json` (contract `urn:swissknifeman:orch:event-data`, `v1`,
alpha). A consumer ignores fields it does not know; a new optional field is a minor change.

| Type | Subject | Required data | Optional data |
| --- | --- | --- | --- |
| `orch.run.started` | run id | `run_id`, `submission_id`, `attempt_id`, `source` (`plugin`, `ref`), `scenario` | — |
| `orch.run.stage.finished` | run id | `run_id`, `stage_id`, `attempt`, `status` | `attempt_id`, `error_class`, `input_digest`, `options_digest`, `work_id`, `item`, `config_digest` |
| `orch.run.finished` | run id | `run_id`, `submission_id`, `ref`, `attempt_id`, `outcome` (`done`, `done_with_deviations`, `blocked`, `refused`), `gate` (`pass`, `missing`, `red`, `stale`, `none`) | — |
| `orch.run.refused` | submission id | `submission_id`, `step` (`claim`, `prepare`, `register`), `reason_codes` | `run_id`, `ref`, `policy_id`, `binding` |
| `orch.agent.started` | `<run>/<item>/<agent run id>` | `run_id`, `work_id`, `agent_run_id`, `role`, `route` (`provider`; `model_class`, `model`, `effort`) | `item`, `step`, `attempt`, `prompt_sha256`, `config_digest`, `options_digest` |
| `orch.agent.finished` | as above | as `orch.agent.started` | the optional data of `started`, `tokens` (`input`, `cached`, `output`), `duration_ms` |
| `orch.agent.failed` | as above | as `orch.agent.started`, `error` (`class`; `code`) | the optional data of `finished` |
| `orch.agent.questioned` | `<run>/<item>` | `run_id`, `work_id`, `step`, `question_id`, `blocking` | `item`, `revision` |
| `orch.run.warning` | `<run>/<item>` | `run_id`, `reason_code` (`RUN_SLOW`, `LIMIT_OVER`) | `work_id`, `item`, `step` |
| `orch.run.waiting` | `<run>/<item>` | `run_id`, `work_id`, `reason_code` (`QUESTION`) | `item`, `step`, `question_ids` |
| `orch.work.blocked` | `<run>/<item>` | `run_id`, `work_id`, `code` (first escalation code of the report, `BLOCKED` without one) | `item`, `step` |
| `orch.review.added` | `<run>/<item>` | `run_id`, `work_id`, `score`, `threshold`, `features` (`name`, `weight`) | `item` |
| `orch.deviation.recorded` | `<run>/<item>` | `run_id`, `work_id`, `deviation_id` (`<item>/dev-<n>`), `class`, `outcome` | `item`, `auto_fixable` |
| `orch.deviation.resolved` | `<run>/<item>` | `run_id`, `work_id`, `deviation_id`, `corrects` (id of the `recorded` event) | `item`, `class`, `outcome` |
| `orch.provider.rate-limited` | `<run>/<item>` | `run_id`, `provider`, `reason_code` (`PROVIDER_WAIT`, `CAPACITY_GATED`) | `work_id`, `item`, `role`, `step`, `until`, `wait_s` |
| `orch.provider.quota-exhausted` | `<run>/<item>` | as `orch.provider.rate-limited` | as `orch.provider.rate-limited` |
| `orch.provider.fallback` | `<run>/<item>` | `run_id`, `role`, `from`, `to` (routes: `provider`, `model_class`, `model`, `effort`), `reason_codes` | `work_id`, `item`, `step` |
| `orch.input.rebuilt` | `<run>/<item>` | `run_id`, `work_id`, `digest` | `item`, `previous_digest` |

The agent events are emitted by the conductor for every agent run (a role process, the report-fixer included):
`correlationid` is the run id, `causationid` of `finished`/`failed` is the id of the `started` event of the same agent run.
Durations are whole milliseconds because event data holds no floats. There is no `gen_ai.*` in the core (D14).

The events of the second table stand next to a beacon of the progress log and are emitted by the same code (table
"beacons → events" of the P12 design): `RUN_SLOW`/`LIMIT_OVER`, a blocking question, a blocked piece, `REVIEW_ADDED`,
a deviation of a report, `PROVIDER_WAIT`/`CAPACITY_GATED` of a rate limit or a quota, `ROUTE_FALLBACK`, `INPUT_REBUILT`.
The types `rate-limited` and `quota-exhausted` are written with a hyphen because the `event/v1` type pattern has no
underscore. A wait for a transient failure that is not a limit gives no provider event. `deviation.recorded` is emitted
when a correction round for an `auto_fixable` deviation starts, or when the final report is written; `deviation.resolved`
when the fixed deviation is carried as accepted.

## Emission rules

- `orch.events.emit(type, data, *, subject, causationid=None, correlationid=None, settings=None)` is the only way to journal an event; it returns the id of the event, or `None` when nothing was journaled.
- An event is emitted after the run journal is written and outside any lock.
- Emission is best-effort. With `[orch.events] enabled = false` nothing is written. Any failure of the event journal
  prints one line `ORCH_EVENT_NOT_EMITTED: <type>: <reason>` on stderr; the exit code and the output of the command
  do not change.
- Pure operations (`prepare --dry-run`, `policy test`) never emit.
- `data` never carries a secret: aicore refuses a `Secret` value (`EVENT_SECRET`) and the event is not journaled.

## Producer fixtures

`tests/fixtures/events/<type>/valid-*.json` and `invalid-*.json` hold full `event/v1` envelopes.
`scripts/test-event-contracts.py` checks every valid fixture against the schema of its producer; `tests/test_events.py`
also requires every invalid fixture to break it. The test runners set `SKM_AICORE_EVENTS__DELIVERY=off`, so no test
starts a subscriber.
