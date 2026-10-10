---
name: planner-plan-design
description: "Only when explicitly invoked. Explicit planner plan design: author or refine a plan with plan.py."
---

# Planner plan-design

Generated Codex adapter for semantic command `planner:plan-design`.

- Invocation: `$ planner:plan-design <arguments>`
- Routing: `frontier/high -> gpt-6-astra/high`
- Canonical source: `packages/planner/commands/plan-design.md`
- Canonical SHA-256: `sha256:ba865c3380b9c61219fcb45e90f36cfda1875b5f83c099274d948f63f46e58f6`
- Runtime projection: `command.md` (generated and provenance-locked; never edit it as source)

Activate only when the owner explicitly invokes this planner command or skill. Planner is not an
automatic workflow for development, fixes, design, or a repository containing plans.

Read `command.md` completely and execute it with the invocation payload as `$ARGUMENTS`.
Preserve the semantic command ID, gates, status literals, scope, and validation behavior.
