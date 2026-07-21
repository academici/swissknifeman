---
name: task-plan-exec
description: Execute one or more specified master-plan items through the complete implementation, validation, journal, status, and handoff cycle. Use only with explicit PLAN-ID and Pn.m items.
---

# Task Plan Exec

Read `packages/task/commands/plan-exec.md` completely and execute it with the invocation
payload as `$ARGUMENTS`. Preserve every lifecycle gate. Map `Sonnet/medium` to the Codex
worker tier: `gpt-5.6/medium` unless the plan routing requires a stronger tier.
