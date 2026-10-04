---
name: task-plan-run
description: "Only when explicitly invoked. Execute authorized Task plan items under the current session route with inline closure."
disable-model-invocation: true
---

# Task plan-run

Generated Cursor adapter for semantic command `task:plan-run`.

- Invocation: `task:plan-run <arguments>`
- Routing: `inherited-plan -> validate the current session against the selected plan item`
- Canonical source: `packages/task/commands/plan-run.md`
- Canonical SHA-256: `sha256:9bd0d060cf01163a153a17f64b4438c6808d062dbbb209a7251a8a6d55cb71a6`
- Runtime projection: `command.md` (generated and provenance-locked; never edit it as source)

Read `command.md` completely and execute it with the invocation payload as the user prompt.
Preserve the semantic command ID, gates, status literals, scope, and validation behavior.
