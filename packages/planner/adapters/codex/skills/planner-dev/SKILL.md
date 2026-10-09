---
name: planner-dev
description: "Only when explicitly invoked. Implement an authorized feature directly, with checks proportionate to risk."
---

# Planner dev

Generated Codex adapter for semantic command `planner:dev`.

- Invocation: `$ planner:dev <arguments>`
- Routing: `implementation/high -> gpt-6-sol/high`
- Canonical source: `packages/planner/commands/dev.md`
- Canonical SHA-256: `sha256:4d4ed13a9dbb9320314fc7bc6538c409932ee583c67216a76be4be7de5ce4224`
- Runtime projection: `command.md` (generated and provenance-locked; never edit it as source)

Activate only when the owner explicitly invokes this planner command or skill. Planner is not an
automatic workflow for development, fixes, design, or a repository containing plans.

Read `command.md` completely and execute it with the invocation payload as `$ARGUMENTS`.
Preserve the semantic command ID, gates, status literals, scope, and validation behavior.
