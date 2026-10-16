# ADR 0004: aicore is the foundation, with a strict generalisation boundary

## Status

Accepted

## Context

Modules need shared utilities, provider knowledge and content handling, but a foundation that absorbs everything
"just in case" becomes the next monolith.

## Decision

`aicore` holds these subsystems: `util`, `config`, `state`, `provider` (including the model catalog),
`artifacts`, `content`, `delivery`, `release`, `ext`, `unit` and `usage`. Code moves into `aicore` only when two or
more modules already use it or when every module needs it by contract (config, state, events, unit).
Everything else stays in its module. A new module is created from a template (`aicore unit new`).

## Alternatives considered

- A thin `aicore` with per-module copies of shared code: rejected, it duplicates provider and content logic.

## Consequences

- Every extension of `aicore` needs a real consumer today; otherwise it is a roadmap entry with a trigger.
- Module-to-subsystem assignment is a hypothesis until the owning stage reads the code; the ownership map records
  the confidence of each entry.

## Supersedes

None.
