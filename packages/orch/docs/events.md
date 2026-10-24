# Events

orch journals twenty events of module `orch` through the `aicore` event journal. The data of each type is a closed
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
| `orch.run.warning` | `<run>/<item>` | `run_id`, `reason_code` (`RUN_SLOW`, `LIMIT_OVER`, `REVIEW_DEBT`, `STAGE_SLOW`, `STAGE_IDLE`, `CHECK_SLOW`, `CHECK_IDLE`, `DISK_LOW`, `STALL_SUSPECTED`) | `work_id`, `item`, `step` |
| `orch.run.waiting` | `<run>/<item>` | `run_id`, `work_id`, `reason_code` (`QUESTION`) | `item`, `step`, `question_ids` |
| `orch.work.blocked` | `<run>/<item>` | `run_id`, `work_id`, `code` (first escalation code of the report, `BLOCKED` without one) | `item`, `step` |
| `orch.review.added` | `<run>/<item>` | `run_id`, `work_id`, `score`, `threshold`, `features` (`name`, `weight`) | `item` |
| `orch.deviation.recorded` | `<run>/<item>` | `run_id`, `work_id`, `deviation_id` (`<item>/dev-<n>`), `class`, `outcome` | `item`, `auto_fixable` |
| `orch.deviation.resolved` | `<run>/<item>` | `run_id`, `work_id`, `deviation_id`, `corrects` (id of the `recorded` event) | `item`, `class`, `outcome` |
| `orch.provider.rate-limited` | `<run>/<item>` | `run_id`, `provider`, `reason_code` (`PROVIDER_WAIT`, `CAPACITY_GATED`) | `work_id`, `item`, `role`, `step`, `until`, `wait_s` |
| `orch.provider.quota-exhausted` | `<run>/<item>` | as `orch.provider.rate-limited` | as `orch.provider.rate-limited` |
| `orch.provider.fallback` | `<run>/<item>` | `run_id`, `role`, `from`, `to` (routes: `provider`, `model_class`, `model`, `effort`), `reason_codes` | `work_id`, `item`, `step` |
| `orch.input.rebuilt` | `<run>/<item>` | `run_id`, `work_id`, `digest` | `item`, `previous_digest` |
| `orch.conductor.lifecycle` | conductor run id | `conductor_run_id`, `phase` (`started`, `resumed`, `ended`) | `outcome` (`finished`, `stopped`, `waiting`, `interrupted`, `crashed`), `reason_code`, `launcher`, `items` (up to 50 references) |
| `orch.autopilot.stopped` | plan | `plan`, `code` (`AUTOPILOT_*`), `runs`, `items_closed` | `message` |
| `orch.conductor.health` | run id | `conductor_run_id`, `health` (`running`, `waiting_provider`, `waiting_tool`, `waiting_owner`, `waiting_budget_reset`, `suspected_stall`, `hung`, `orphaned`, `stopped`, `finished`, `unknown`) | `previous`, `reason_code`, `action` (`notify`, `snapshot`, `stop`, `reap`, `resume`, `given_up`, `identity_mismatch`, `busy`), `silent_s`, `item`, `step` |

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

`orch.autopilot.stopped` (subject: the plan; data `plan`, `code` (an `AUTOPILOT_*` stop code), `runs`, `items_closed`, and
`message`) is emitted once by `orch conduct autopilot start` when its session ends, whatever the code (see *Autopilot* in
`docs/conductor.md`); the same stop is in `autopilot.json` and on stderr.

`orch.conductor.health` is emitted by the supervisor (`orch conduct supervise`, `orch conduct reap`; see *Supervisor* in
`docs/conductor.md`) for every action it records in `<run>/supervisor.jsonl`, not by the conductor itself: `previous` is the
class it saw before, `action` what it did. `status` and `runs` emit nothing.

## Emission rules

- `orch.events.emit(type, data, *, subject, causationid=None, correlationid=None, settings=None)` is the only way to journal an event; it returns the id of the event, or `None` when nothing was journaled.
- An event is emitted after the run journal is written and outside any lock.
- Emission is best-effort. With `[orch.events] enabled = false` nothing is written. Any failure of the event journal
  prints one line `ORCH_EVENT_NOT_EMITTED: <type>: <reason>` on stderr; the exit code and the output of the command
  do not change.
- `data` is checked against `schemas/event-data/v1/<type>.schema.json` (the `dataschema` of the event) before it is journaled. Data that breaks it is not written: stderr gets `ORCH_EVENT_NOT_EMITTED: <type>: EVENT_DATA_INVALID: <first problem>`, and the exit code and the output of the command do not change. Under `SKM_CONTRACTS_STRICT=1` (set by every `scripts/test.sh`) the same case raises `ExtError('EVENT_DATA_INVALID')`, so a test sees it. The check runs on the redacted data, the form that would be written.
- Pure operations (`prepare --dry-run`, `policy test`) never emit.
- `data` passes `aicore.util.redact.redact_document` first: the values of environment variables named like api key, token, secret or password and the explicit token formats become `‹redacted›`. The same masking covers the progress lines, the `detail` of a failed role (the stderr tail) and the observer report; the raw streams under `streams/` stay as the role printed them and live in the ignored runtime folder (`orch doctor` warns when `.swissknifeman/state/` is not ignored).
- `data` never carries a secret: aicore refuses a `Secret` value (`EVENT_SECRET`) and the event is not journaled.

## Retention of the event journal

orch writes events into the aicore journal of the project (`events.jsonl`) and never rotates, compacts or removes it:
compaction changes the delivery offsets of the subscribers, and the journal is owned by aicore. Decision (PLAN9 P8.6):
the retention of the event journal is a task of aicore, recorded for the roadmap (P10.2); its trigger is an
`events.jsonl` larger than 50 MB. Until then `orch conduct prune` leaves the journal alone; what orch can shrink itself
are the raw role streams of old runs (`conduct prune --compress-older-than DAYS`, `docs/conductor.md`).

## Producer fixtures

`tests/fixtures/events/<type>/valid-*.json` and `invalid-*.json` hold full `event/v1` envelopes.
`scripts/test-event-contracts.py` checks every valid fixture against the schema of its producer; `tests/test_events.py`
also requires every invalid fixture to break it. The test runners set `SKM_AICORE_EVENTS__DELIVERY=off`, so no test
starts a subscriber.

The same script checks the emitters: every event type a module emits (a literal, a module constant or `gui.run.{verb}`
in its sources) must be in the `provides.events` of that module and have a data schema.

`orch.conductor.lifecycle` describes each conductor session: `run` publishes `started`, `resume` publishes `resumed`
beside `run.resume` after ownership, state loading and startup validation, and the loop publishes `ended` beside `run.end`, including interruption
and unexpected crashes. Waiting for an owner decision (exit 4) has outcome `waiting`. Launcher values are `terminal`,
`detached`, `gui`, `supervisor`, `autopilot`. These events follow `[orch.events] enabled`; journal failures never
change the run outcome. A warning event is published once per corresponding stage/check/disk/stall beacon line.

Analyst subscribes explicitly to `orch.run.finished` and `orch.run.refused`; warning and conductor lifecycle events
are valid envelopes that its ingest skips. Expanding the warning reason enum does not change its recorded outcomes.
