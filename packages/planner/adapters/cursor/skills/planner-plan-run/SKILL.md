---
name: planner-plan-run
description: "Only when explicitly invoked. Execute ready planner plan items with plan.py under the current session route."
disable-model-invocation: true
---

# Planner plan-run

Generated Cursor adapter for semantic command `planner:plan-run`.

- Invocation: `planner:plan-run <arguments>`
- Routing: `inherited-plan -> validate the current session against the selected plan item`
- Canonical source: `packages/planner/commands/plan-run.md`
- Canonical SHA-256: `sha256:25c38dbf1756ca54689471460616823a0cbc33e6d3be2f68ec2b74d8052b048b`
- Runtime projection: `command.md` (generated and provenance-locked; never edit it as source)

Read `command.md` completely and execute it with the invocation payload as the user prompt.
Preserve the semantic command ID, gates, status literals, scope, and validation behavior.
