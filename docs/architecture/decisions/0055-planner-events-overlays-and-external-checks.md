# ADR 0055: Planner events, command overlays and the `planner:check` extension point

## Status

Accepted

## Context

Other modules need to react to plan lifecycle changes (brain writes a note when a plan closes), people need to add
rules to a command without editing the module, and teams want checks the engine does not know. The foundation
provides the event journal ([ADR 0041](0041-event-envelope-journal-and-delivery.md)), external plugins
([ADR 0042](0042-external-plugin-protocol-and-process-discipline.md)) and overlays
([ADR 0044](0044-instruction-overlays-runtime-resolution.md)).

## Decision

- **Events.** `planner.plan.created`, `planner.plan.closed`, `planner.phase.closed`, `planner.item.started`,
  `planner.item.finished` and `planner.decision.accepted` are emitted after the change is written and after the plan
  lock is released, never inside it: a synchronous subscriber may call `plan.py`. Emission is best effort through
  `planner.integration.events`; a failure gives one warning and does not change the result. `events.enabled = false`
  turns it off. Repeating `finish` with the same attempt id emits nothing.
- **Event data.** The contract `schemas/event-data/v1` holds one closed schema per type
  (`urn:swissknifeman:planner:event-data:<type>:v1`). Data never carry notes, deviation texts or secrets. The hub
  test `scripts/test-event-contracts.py` validates every consumer fixture against the producer schema; a mismatch is
  fixed in the consumer fixture, the producer is the source of truth.
- **Overlays.** Each of the ten commands owns a slot `planner:<command>` declared in `unit.json`. The first line of
  the command runs `plan.py overlays planner:<command>` and follows the printed rules as additions; they never
  override the plan, its checks or safety rules. Without aicore the block is empty.
- **External checks.** The extension point `planner:check` takes the input and output contracts in
  `schemas/check-plugin/v1`. Only the verb `check` calls it (not the checks inside mutations). Plugin issues become
  errors and warnings of the check; a plugin that fails, times out or answers invalidly gives one
  `EXTERNAL_CHECK_FAILED` finding whose severity is `checks.external_failure` (`warn` by default). `--no-external`
  skips the point and `checks.external = false` disables it.

## Alternatives considered

- Emitting inside the lock right after the write: rejected, a synchronous subscriber that runs `plan.py` deadlocks.
- Baking overlays into the generated projections: rejected, shared projections and golden files must not depend on a
  person's rules ([ADR 0044](0044-instruction-overlays-runtime-resolution.md)).

## Consequences

- Consumers read `planner.*` events and ignore unknown fields; new fields are additive.
- Plugins never slow down a mutation, only an explicit `check`.

## Supersedes

None.
