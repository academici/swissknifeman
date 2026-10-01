# Execution Roadmap - <PLAN-ID>

<!-- execution-sheet/v1 -->

<!-- A live map of “what to launch next” is not a secondary plan. Roadmap groups only ready
     adjacent items with compatible scope/route; local order remains adaptive in sealed
     contract. It does not override Routing §3, owner gates or material-review trigger. -->

**Updated:** <YYYY-MM-DD> · **Corresponds to plan.md:** v<X.Y.Z>

## Grouping rule

- First look for a connected adjacent chain of one phase: common producer/consumer, files,
  Required Reads, setup or Validation. Merge when reuse reduces time and tokens.
- Don't atomize due to individual commits/Deliverables: per-item lifecycle is saved inside batch.
- `solo` is allowed only with a specific reason: incompatible Exec, owner/irreversible gate,
  separate capability/hard boundary or expected context overflow.
- Batch does not cross phase audit/close; launch uses maximum route/review and union capabilities.
- Phase design offers groups; design finish recalculates them throughout the dependency graph.
- Specific provider model selectors are prohibited in Routing; one semantic maximum
  gives the provider adapter one model for the entire admission.

## Execution sheet - the only source of launch commands

<!-- Finish validates exact row for each compiled batch. -->

| Command | Unified route | Review |
|:--|:--|:--|
| `task:plan-run <PLAN-ID> P0.1 P0.2` | `implementation/medium` | `light` |
| `task:plan-run <PLAN-ID> P1.1` | `frontier/high` | `full` |

## Execution card

| Item | Batch | Launch | Model class/Effort | Owner's Gate | Note |
|---|---|---|---|---|---|
| P0.1 | B1 | plan-run series | implementation/medium | — | ready adjacent scope |
| P0.2 | B1 | ↑ | implementation/medium | — | shared validation boundary |
| P1.1 | solo | plan-run | frontier/high | ✅ matrix approval | owner gate excludes secure chain |
| P2.1–P2.3 | W1 | orchestration | implementation/medium | — | independent scope and declared capability |
| … | | | | | |

## Ready launch-block groups

### B1 - <essence of the batch>

| Parameter | Meaning |
|:--|:--|
| Batch | B1 |
| Model class | <economy / implementation / frontier> |
| Effort | <low / medium / high / xhigh> - <reason> |
| Capabilities | <semantic capability IDs> |
| Context | continue-root |
| Essence | Series <Pn.a>–<Pn.b> in one session, gates between items - inside the session |

```
run-items: task:plan-run <PLAN-ID> <Pn.a> <Pn.b> <Pn.c>
```

<!-- Batch series go through plan-run (item list); it takes the minimum route from the
     plan's Routing row and runs under the verified session route. -->

### W1 - <essence of the workflow group>

```
kind: orchestration
orchestration_id: <PLAN-ID>:W1
inputs: [plan.md, roadmap.md, phases/<Pn>/<Pn>.md]
required_capabilities: [command.subagents, command.workflow-carrier]
provider_projection: <verified mapping reference>
```

## Owner gates (summary)

| Where | What does | Blocks |
|---|---|---|
| <Pn.m> | <artifact> | <what batches are waiting> |
