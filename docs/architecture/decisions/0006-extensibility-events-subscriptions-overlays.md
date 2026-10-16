# ADR 0006: Extensibility through events, subscriptions, overlays and external commands

## Status

Accepted

## Context

People need to adapt behaviour per computer and per project without forking a module.

## Decision

`aicore.ext` provides: events (an envelope, a per-project journal, best-effort delivery), subscriptions declared in
configuration or in `unit.json`, instruction overlays attached to named command slots, and external plugin commands
that read JSON on stdin and write JSON on stdout. Provider hooks (for example Claude Code `SessionStart`) stay with
`harness`, which may translate them into events.

## Alternatives considered

- In-process plugin APIs: rejected for now, see ADR 0016.

## Consequences

- A subscriber failure never breaks the source; delivery is idempotent by event `id`.
- Overlay slots and extension points are declared in `unit.json`, so they are discoverable and checkable.

## Supersedes

None.
