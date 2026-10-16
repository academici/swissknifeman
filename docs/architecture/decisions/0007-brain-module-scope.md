# ADR 0007: brain is a hub module; only its foundation is in scope

## Status

Accepted

## Context

The Obsidian vault tooling lives partly in `skiller`, partly in `maind` and partly outside the repository.

## Decision

`packages/brain` is created with a module skeleton. It takes over `brain_sync` from `skiller`, the `brain-locator`
skill and the vault parts of `maind`, defines its events contract and gets one first subscriber: a closed plan
produces a note in the vault. Moving the external vault code is out of scope.

## Alternatives considered

- Move the external vault code now: rejected as too large for this change.

## Consequences

- The vault gets a home and an event-driven integration without enlarging `skiller` or `maind`.
- The remaining external code is a later, separate move.

## Supersedes

None.
