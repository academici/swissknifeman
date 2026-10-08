# ADR 0012: Planner budgets, thresholds and behaviour are configurable

## Status

Accepted

## Context

Limits such as the context pack size, the heavy-text threshold, the number of listed sources and the reference
chain depth are constants in code, and new-plan defaults are not tunable.

## Decision

Precedence: planner defaults, machine, project, plan settings, flags. Configurable: check budgets and thresholds;
defaults of new plans; cycle policies (review rounds, corrections, retries) within bounds that checks do not let
reach zero; view templates; instruction overlays (ADR 0006); external plan checks. The planner stage starts with an
inventory of hard-coded constants and policies; each one stays in code, becomes configuration or becomes a plan
setting, with a reason.

## Alternatives considered

- Keep constants in code: rejected, plans must be tunable per owner and per project.

## Consequences

- The mechanism is `aicore.config` (ADR 0005, ADR 0011), so planner adds no loader of its own.
- Safety bounds are part of the schema, so configuration cannot disable a check.

## Supersedes

None.
