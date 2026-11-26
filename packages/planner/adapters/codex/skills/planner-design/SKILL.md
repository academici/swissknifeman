---
name: planner-design
description: "Only when explicitly invoked. Explicit design request: produce a plan or ADR; implementation is separate."
---

# Planner design

Generated Codex adapter for semantic command `planner:design`.

- Invocation: `$ planner:design <arguments>`
- Routing: `frontier/high -> gpt-6-astra/high`
- Canonical source: `packages/planner/commands/design.md`
- Canonical SHA-256: `sha256:1ea50aa97adbde27580b0c04913c0ed7afd0dba929a8188d3939abba3cac3b6d`
- Runtime projection: `command.md` (generated and provenance-locked; never edit it as source)

Activate only when the owner explicitly invokes this planner command or skill. Planner is not an
automatic workflow for development, fixes, design, or a repository containing plans.

Read `command.md` completely and execute it with the invocation payload as `$ARGUMENTS`.
Preserve the semantic command ID, gates, status literals, scope, and validation behavior.
