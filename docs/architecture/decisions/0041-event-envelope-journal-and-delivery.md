# ADR 0041: Event envelope, journal-first delivery, cursors and dead letters

## Status

Accepted

## Context

ADR 0006 promised best-effort events. Consumers (brain, analyst, orch) need an envelope that other tools can read, a
journal that survives a crash, and a delivery that never breaks the source.

## Decision

- **Envelope `event/v1`:** a CloudEvents 1.0 JSON subset. `id` is a uuid4 hex, `source` is
  `urn:swissknifeman:module:<id>`, `type` is `<module>.<subject>.<verb>` (the first segment is the module). `data` is an
  object of at most 64 KiB of canonical JSON; larger data goes through `artifact-ref/v1` and `aicore.state.blobs`.
  Unknown extension attributes are ignored by readers. There is no `project` field; the subscriber gets the root from its
  environment.
- **Journal:** `<project>/.swissknifeman/state/events.jsonl`, append-only under `flock`, `fsync`, no rotation.
- **Delivery only from the journal.** One cursor per subscription in `ext/cursors.json` (offset and last `id`) under
  `ext/deliver.lock`; one deliverer per journal; at-least-once, so a subscriber is idempotent by `id`; one attempt per
  event and pass; after `max_attempts` (3) the event goes to `ext/dead-letter.jsonl`; `replay` delivers again.
- **Modes:** `background` (default), `sync`, `off`.
- **The source is never broken:** `emit` raises only for a wrong call (type, data, size, `Secret`); I/O and configuration
  failures are a warning and `None`.

## Alternatives considered

- Deliver at once and journal after: rejected, a crash loses the event.
- Exactly-once: rejected, it needs a transaction with every subscriber; a daemon deliverer: rejected, a one-shot process under a lock needs no service.

## Consequences

- Subscribers must be idempotent; a failed event waits for the next deliverer run (no timer retry, deferred).
- Locks need `flock`; network file systems without it are not supported; the journal has no rotation until it grows
  past about 50 MB.

## Supersedes

Refines ADR 0006.
