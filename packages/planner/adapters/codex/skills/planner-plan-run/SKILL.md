---
name: planner-plan-run
description: "Only when explicitly invoked. Execute ready planner plan items with plan.py under the current session route."
---

# Planner plan-run

Generated Codex adapter for semantic command `planner:plan-run`.

- Invocation: `$ planner:plan-run <arguments>`
- Routing: `inherited-plan -> validate the current session against the selected plan item`
- Canonical source: `packages/planner/commands/plan-run.md`
- Canonical SHA-256: `sha256:8fd80e4e78697daa877d81b455746a3f94ce7d06a4d8074604074aa4f916ae2b`
- Runtime projection: `command.md` (generated and provenance-locked; never edit it as source)

Activate only when the owner explicitly invokes this planner command or skill. Planner is not an
automatic workflow for development, fixes, design, or a repository containing plans.

Read `command.md` completely and execute it with the invocation payload as `$ARGUMENTS`.
Preserve the semantic command ID, gates, status literals, scope, and validation behavior.
