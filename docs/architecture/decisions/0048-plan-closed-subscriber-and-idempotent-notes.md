# ADR 0048: The plan-closed subscriber and idempotent notes

## Status

Accepted

## Context

`aicore` delivers events at least once, by a cursor, and can replay them. The first subscriber of `brain` writes
a note into a vault that belongs to a person, who may move, rename or edit files at any time. The emitting module
does not exist yet.

## Decision

- **Subscription.** `brain:plan-notes` in `unit.json`: on `planner.plan.closed`, run `bin/brain note --event -`,
  timeout 30 seconds. After a new note the module emits `brain.note.created`, caused by the closing event.
- **Consumer contract first.** The expected data of the event (`plan_id` and `title` required, the rest optional,
  unknown fields ignored) is recorded as fixtures in `tests/fixtures/events/`. The emitter's schema is made with the
  emitter and checked against the fixtures.
- **Placement.** The project folder of the vault in `notes.folder`, else `notes.fallback_folder`. The name is a pure
  function of the event.
- **Idempotency.** A ledger `notes.jsonl` in the state folder under a lock; a note is created through a hard link
  from a temporary file, so an existing file is never overwritten; a clash gets a ` (2)` suffix; a lost ledger is
  rebuilt from the `event_id` of the frontmatter.
- **Answers.** No vault: skipped. Wrong data: exit 65 (dead letter). Temporary failure: exit 75 (retry).

## Alternatives considered

- Idempotency by the existence of the file only: rejected, a note that a person moved or renamed would be created
  again on every replay.

## Consequences

- A repeated delivery and a replay never produce a duplicate.
- A note moved by a person *and* a deleted ledger can produce a second note on replay; this is documented.

## Supersedes

None.
