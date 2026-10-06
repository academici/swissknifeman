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
- Canonical SHA-256: `sha256:95ea8d0683bd59985720b78123709c54a1a03a769f4cd0de4e94743ed05a2c32`
- Runtime projection: `command.md` (generated and provenance-locked; never edit it as source)

Read `command.md` completely and execute it with the invocation payload as the user prompt.
Preserve the semantic command ID, gates, status literals, scope, and validation behavior.
