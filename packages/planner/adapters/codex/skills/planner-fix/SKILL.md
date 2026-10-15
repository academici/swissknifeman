---
name: planner-fix
description: "Only when explicitly invoked. Fix a scoped defect directly; preserve existing work and verify the change."
---

# Planner fix

Generated Codex adapter for semantic command `planner:fix`.

- Invocation: `$ planner:fix <arguments>`
- Routing: `implementation/medium -> gpt-6-sol/medium`
- Canonical source: `packages/planner/commands/fix.md`
- Canonical SHA-256: `sha256:6e7574d4d67fa5861ca5051f9a97e21c3972d89aac82bd757a7c85cb429dbd5a`
- Runtime projection: `command.md` (generated and provenance-locked; never edit it as source)

Activate only when the owner explicitly invokes this planner command or skill. Planner is not an
automatic workflow for development, fixes, design, or a repository containing plans.

Read `command.md` completely and execute it with the invocation payload as `$ARGUMENTS`.
Preserve the semantic command ID, gates, status literals, scope, and validation behavior.
