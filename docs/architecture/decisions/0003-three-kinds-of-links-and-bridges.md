# ADR 0003: Three kinds of links; bridges connect planner and orch

## Status

Accepted

## Context

`planner` and `orch` found each other by guessing sibling paths. Other module pairs need controlled links too.

## Decision

Modules are linked in exactly three ways:

- *dependency*: an import of `aicore`;
- *bridge*: a synchronous request-response contract over CLI and JSON, kept in `bridges/` of the hub
  (`planner-orch`, `orch-skiller`);
- *event*: an asynchronous notification; the source does not know its subscribers.

`orch` runs its loop through a work-source port (`next`, `brief`, `run`, `register`). Discovering the neighbour by
path is replaced by a command taken from configuration.

## Alternatives considered

- Direct imports between modules: rejected by ADR 0002.

## Consequences

- Planner and orch can be developed and moved independently; the bridge is the tested seam.
- Events need the extension layer (ADR 0006) before the first subscriber exists.

## Supersedes

Supersedes, from the orchestration stage on, the earlier decision that located the planner bridge by sibling path.
