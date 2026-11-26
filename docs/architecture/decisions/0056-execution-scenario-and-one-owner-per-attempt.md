# ADR 0056: Execution scenario and one owner per attempt, as minor changes of `plan/v1`

## Status

Accepted

## Context

Plans need a default execution scenario ([ADR 0013](0013-orchestration-scenarios-and-prepared-brief.md)) and an item
attempt must have one owner ([ADR 0018](0018-execution-protocol-identity-fencing-idempotency.md)). Until now `start`
on an item already in progress silently continued it under a new executor. The plan schema and its URNs must stay
compatible.

## Decision

- **Rule.** The URNs `urn:swissknifeman:task:plan:*` and the compatibility of `v1` do not change; the schema changes
  only by minor steps (optional fields), checked with `aicore schema compat`.
- **Scenario.** The optional field `orchestration.scenario` (`^[a-z][a-z0-9-]*$`) names a run-policy profile of an
  execution engine, or `solo` for the current session. It resolves in the order item, phase, plan,
  `orchestration.by_class.<route.class>`, `orchestration.default_scenario` (`solo`). The context pack carries
  `orchestration.scenario` and `orchestration.scenario_source`. Planner does not check the name against engine
  profiles; the orch bridge does.
- **Owner.** The owner of an attempt is `result.executor.session`. `start` of an item in progress from another session
  fails with `ITEM_OWNED`; `--take-over` hands the attempt over and the `start` event records the previous executor
  in `data.take_over`. `finish` does not check ownership, so an execution engine can register the result of its
  executor from another session. If either side has no session, the old behaviour applies, so old plans and calls
  keep working. The registrar of `finish` (`--registrar`) is never an owner. No `result` field was added.
- **Fixtures.** Old-plan fixtures and a hub test (`scripts/test-plan-compat.py`) read every plan of the repository
  with the new engine.

## Alternatives considered

- New `result.owner` and `epoch` fields: rejected, a session already identifies a session or an engine run.
- A scenario only in configuration by class: rejected, an item must be able to override it.

## Consequences

- Ownership is not enforced for calls without a session.
- Older readers ignore the new optional field.

## Supersedes

None.
