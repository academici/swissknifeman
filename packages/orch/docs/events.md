# Events

orch journals four events of module `orch` through the `aicore` event journal. The data of each type is a closed
JSON Schema under `schemas/event-data/v1/<type>.schema.json` (contract `urn:swissknifeman:orch:event-data`, `v1`,
alpha). A consumer ignores fields it does not know; a new optional field is a minor change.

| Type | Subject | Required data | Optional data |
| --- | --- | --- | --- |
| `orch.run.started` | run id | `run_id`, `submission_id`, `attempt_id`, `source` (`plugin`, `ref`), `scenario` | — |
| `orch.run.stage.finished` | run id | `run_id`, `stage_id`, `attempt`, `status` | `attempt_id`, `error_class`, `input_digest` |
| `orch.run.finished` | run id | `run_id`, `submission_id`, `ref`, `attempt_id`, `outcome` (`done`, `done_with_deviations`, `blocked`, `refused`), `gate` (`pass`, `missing`, `red`, `stale`, `none`) | — |
| `orch.run.refused` | submission id | `submission_id`, `step` (`claim`, `prepare`, `register`), `reason_codes` | `run_id`, `ref`, `policy_id`, `binding` |

## Emission rules

- `orch.events.emit(type, data, *, subject, causationid=None, settings=None)` is the only way to journal an event.
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
