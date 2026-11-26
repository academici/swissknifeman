# ADR 0064: Run analytics live in analyst, and analyst subscribes to ecosystem events

## Status

Accepted

## Context

Analytics of agent runs (run reports, pathologies, code graph usage) lived in the foundation package and was imported by
`maind`, `analyst` and `harness`. The foundation must stay free of consumers, and analyst had no input from planner and
orch.

## Decision

- **Move.** `run_reports.py`, `pathology.py` and `codegraph.py` live in `packages/analyst/lib/analyst/`.
- **Command.** `analyst runs show --project DIR [--session ID] [--json]` prints `run-lookup/v1`;
  `analyst runs codegraph --project DIR [--limit N] [--json]` prints `run-codegraph/v1`. Both schemas belong to analyst
  (`unit.json` `provides.contracts`). `maind analyze` and the code graph usage report call them through `aicore.util.partners`
  and degrade without analyst: the source `run-report` is unavailable and the confidence is low.
- **Subscription.** `unit.json` `subscribes` declares `run-events` for `planner.item.finished`, `planner.phase.closed`,
  `planner.plan.closed`, `orch.run.finished` and `orch.run.refused`; it runs `analyst events ingest --event -`.
  The command checks the envelope and appends one line `{event_id, type, occurred_at, source, project, subject, outcome,
  data_digest}` to `ecosystem-events.jsonl` in the analyst state directory under a file lock. The write is idempotent by
  `event_id`; the values of `data` are not copied, only their digest. An event of another type exits 0 with `skip`;
  an invalid event exits 2 with `ANALYST_EVENT_INVALID`.
- **Reading.** `analyst events list [--type T] [--since ISO] [--json]` and the counters of `analyst status`.
- **Telemetry names.** `analyst.telemetry` maps the dispatch events of the trace to the spans of the foundation
  conventions and checks metric labels (`skm.event.type`, `skm.outcome`, `skm.provider`) with `metric_label_problems`.
  The closed formats of the trace and the reliability digest do not change; there is no OpenTelemetry export.

## Alternatives considered

- Keeping the analytics in the foundation: rejected, it has one domain and consumers that should not import it.
- Copying the `data` of events into the journal: rejected, the producers own it and it can hold paths.

## Consequences

- Registering the subscription in a project is a hub step (see the hub documentation).
- The reader of analyst and the writer of `maind` agree through contracts, not through imports.

## Supersedes

None.
