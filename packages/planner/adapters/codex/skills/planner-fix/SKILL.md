---
name: planner-fix
description: "Only when explicitly invoked. Fix a scoped defect directly; preserve existing work and verify the change."
---

# Planner fix

Generated Codex adapter for semantic command `planner:fix`.

- Invocation: `$ planner:fix <arguments>`
- Routing: `implementation/medium -> gpt-6-sol/medium`
- Canonical source: `packages/planner/commands/fix.md`
- Canonical SHA-256: `sha256:14c2a0f7942755a6c949edc91a59431080ca8111d4d73f6bfcc5c736b047b716`
- Runtime projection: `command.md` (generated and provenance-locked; never edit it as source)

Activate only when the owner explicitly invokes this planner command or skill. Planner is not an
automatic workflow for development, fixes, design, or a repository containing plans.

Read `command.md` completely and execute it with the invocation payload as `$ARGUMENTS`.
Preserve the semantic command ID, gates, status literals, scope, and validation behavior.
