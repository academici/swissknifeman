---
name: task-plan-run
description: Execute explicit master-plan items with the current session model while enforcing the plan's routing floor. Use for manual item series where the session model is intentionally selected.
---

# Task Plan Run

Read `packages/task/commands/plan-run.md` and its referenced `plan-exec.md` completely.
Execute with the invocation payload as `$ARGUMENTS`. Report the actual Codex model and
effort; block execution when they are below the plan's provider-neutral routing tier.
