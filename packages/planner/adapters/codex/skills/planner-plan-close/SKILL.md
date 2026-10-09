---
name: planner-plan-close
description: "Only when explicitly invoked. Close or archive planner plan work with plan.py; ordinary execution already closes inline."
---

# Planner plan-close

Generated Codex adapter for semantic command `planner:plan-close`.

- Invocation: `$ planner:plan-close <arguments>`
- Routing: `implementation/low -> gpt-6-sol/low`
- Canonical source: `packages/planner/commands/plan-close.md`
- Canonical SHA-256: `sha256:f4637af69e4d3a46a993f2f0d7e131222f198791b8e0ca00e77bdef9a91365d5`
- Runtime projection: `command.md` (generated and provenance-locked; never edit it as source)

Activate only when the owner explicitly invokes this planner command or skill. Planner is not an
automatic workflow for development, fixes, design, or a repository containing plans.

Read `command.md` completely and execute it with the invocation payload as `$ARGUMENTS`.
Preserve the semantic command ID, gates, status literals, scope, and validation behavior.
