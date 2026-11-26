# ADR 0084: GUI state: canonical files are the source of truth; SQLite is a rebuildable index

## Status

Accepted

## Context

The GUI keeps runs, their logs, preferences and caches of queries. Plans, configuration and manifests already have
canonical files owned by their modules. A second store of the same facts would drift from them, and a crash in the
middle of a run must not leave a state the GUI cannot explain.

## Decision

- **Truth.** Canonical SKM files (plans, configuration, manifests) are the only source of truth; the GUI never writes
  another module's file directly, only through the owner's command line or library.
- **Index.** SQLite (stdlib `sqlite3`, WAL) in `$SKM_HOME/state/gui` indexes runs, preferences and caches; it can be
  rebuilt from the canonical files and the run journals (`gui state rebuild`).
- **Logs.** One JSONL log per run, redacted before it is written.
- **Order.** A run state transition is stored before its event is published; runs left unfinished by a crash become
  `lost`, and a PID is never adopted after a restart.
- **Configuration writes.** preview → validate → diff → confirm → lock → revision CAS → temp + fsync + atomic replace →
  re-read and validate; a silent last write wins is forbidden.

## Alternatives considered

- JSON files only: rejected, run queries and indexes are slow and concurrent writes race.
- A database as the source of truth for plans or configuration: rejected, it would compete with the canonical files of
  the owning modules.

## Consequences

- The index has schema migrations; losing the database loses no canonical fact.
- State follows the standard locations of ADR 0005.

## Supersedes

None.
