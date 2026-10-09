# ADR 0045: Telemetry naming conventions

## Status

Accepted

## Context

Runs, stages, tools and deliveries will be traced and counted by several modules. Names and labels chosen separately
would not line up, and a label with unbounded values breaks a metric backend.

## Decision

- **Contract `telemetry-conventions/v1`** with the data `packages/aicore/configs/telemetry-conventions.json`.
- **Namespace `skm.*`.** Every attribute has a cardinality, `low` or `high`.
- **Spans.** `skm.run` > `skm.plan.compile` > `skm.stage` > `skm.agent.execute` (GenAI `invoke_agent`) >
  `skm.tool.execute` (`execute_tool`), plus `skm.effect.apply`, and the roots `skm.event.deliver` and
  `skm.plugin.invoke`.
- **Metric labels** may only be `low` attributes and the allowed `gen_ai.*` ones (`operation.name`, `provider.name`,
  `request.model`); `aicore.util.telemetry.metric_label_problems` reports violations.
- **No exporter.** OpenTelemetry export and trace backends are deferred; analyst moves in P11.

## Alternatives considered

- Adopt the OpenTelemetry names without a namespace: rejected, our own concepts would have no place.
- Write an exporter now: rejected, no consumer needs one.

## Consequences

- Modules can name spans and label metrics the same way today and add an exporter later without renaming.

## Supersedes

None.
