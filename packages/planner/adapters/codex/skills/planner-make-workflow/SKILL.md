---
name: planner-make-workflow
description: "Only when explicitly invoked. Explicit workflow authoring: fill a canonical template and validate its stages."
---

# Planner make-workflow

Generated Codex adapter for semantic command `planner:make-workflow`.

- Invocation: `$ planner:make-workflow <arguments>`
- Routing: `implementation/high -> gpt-6-sol/high`
- Canonical source: `packages/planner/commands/make-workflow.md`
- Canonical SHA-256: `sha256:9086b1ae53826a71b9e422a7fcf71025dc5c932cb7364a5f48ac84ee75dd90dd`
- Runtime projection: `command.md` (generated and provenance-locked; never edit it as source)

Activate only when the owner explicitly invokes this planner command or skill. Planner is not an
automatic workflow for development, fixes, design, or a repository containing plans.

Read `command.md` completely and execute it with the invocation payload as `$ARGUMENTS`.
Preserve the semantic command ID, gates, status literals, scope, and validation behavior.
