---
name: task-plan-run
description: "Execute manual plan item(s) using the owner session route and shared lifecycle."
---

# Task plan-run

Generated Codex adapter for semantic command `task:plan-run`.

- Invocation: `$ task:plan-run <arguments>`
- Routing: `inherited-plan -> validate the current session against the selected plan item`
- Canonical source: `packages/task/commands/plan-run.md`
- Canonical SHA-256: `sha256:a5e403c8afd89b75360c31ec3705267c2df5a4824c70b280c0596dcc44b417da`
- Runtime projection: `command.md` (generated and provenance-locked; never edit it as source)

Read `references/intent-routing.md` from the configured Task marketplace runtime before selecting
the workflow. Skill relevance alone is not workflow authority; the latest explicit owner
request determines the work product. Direct development and fixes require no plan lifecycle.

Read `command.md` completely and execute it with the invocation payload as `$ARGUMENTS`.
Preserve the semantic command ID, gates, status literals, scope, and validation behavior.
