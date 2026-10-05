---
name: task-plan-run
description: "Only when explicitly invoked. Execute ready Task plan items with plan.py under the current session route."
disable-model-invocation: true
---

# Task plan-run

Generated Cursor adapter for semantic command `task:plan-run`.

- Invocation: `task:plan-run <arguments>`
- Routing: `inherited-plan -> validate the current session against the selected plan item`
- Canonical source: `packages/task/commands/plan-run.md`
- Canonical SHA-256: `sha256:4d57b8f4c83a0ca04519023a8df00a5e88d439d55d214fe17428f4d2ba1e5c2e`
- Runtime projection: `command.md` (generated and provenance-locked; never edit it as source)

Read `command.md` completely and execute it with the invocation payload as the user prompt.
Preserve the semantic command ID, gates, status literals, scope, and validation behavior.
