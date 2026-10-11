# ADR 0062: Engine conformance and the non-goals of `orch`

## Status

Accepted

## Context

More than one engine will implement the Engine Port. They must be compared by the same scenarios, and the module has
to say what it will not become.

## Decision

- **Catalogue.** `conformance/scenarios.json` lists scenarios as data: `id`, `title`, `kit` (`agent` or `runtime`), `how`
  (`trace` or `test`), `ref`, `expect`, and per binding a status `covered`, `declared` (with a reason, usually that an
  executing engine is needed) or `n/a`. Scenarios that need no engine run as traces through the run-state reducer,
  `retry.decide` and `effects.guard`; process scenarios stay `declared`.
- **Command.** `orch.py conformance [--binding B] [--json]` runs every `covered` scenario and prints the `declared` ones.
  A new engine adds its binding to every scenario (see `adding-an-engine` in the orch documentation).
- **Confinement.** `prepare` and the `orch` CLI write only under `--out` and the run directory; a test snapshots the
  file system of a temporary home.
- **Non-goals.** `orch` does not provide durable timers, signals, workflow replay, compensation or multi-day execution;
  those belong to specialised runtimes.
- **MCP.** MCP is a tool surface, not the event bus and not the source of truth about runs. `orch` and the
  `aicore` extension layer import no MCP code; a test checks it.

## Alternatives considered

- Conformance as prose: rejected, it cannot be run.
- Building a workflow runtime into `orch`: rejected, it duplicates specialised systems.

## Consequences

- The statuses make the gap to a full engine visible.
- Starting a run stays `NOT_IMPLEMENTED` until an engine exists.

## Supersedes

None.
