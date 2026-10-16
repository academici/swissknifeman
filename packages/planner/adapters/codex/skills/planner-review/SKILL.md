---
name: planner-review
description: "Only when explicitly invoked. Risk-scaled read-only review of code, docs or specs."
---

# Planner review

Generated Codex adapter for semantic command `planner:review`.

- Invocation: `$ planner:review <arguments>`
- Routing: `implementation/high -> gpt-6-sol/high`
- Canonical source: `packages/planner/commands/review.md`
- Canonical SHA-256: `sha256:ccf60839f1e992e2cec149fe68f36c673824cdff8eb0e8ba8d46e8a14e2a435f`
- Runtime projection: `command.md` (generated and provenance-locked; never edit it as source)

Activate only when the owner explicitly invokes this planner command or skill. Planner is not an
automatic workflow for development, fixes, design, or a repository containing plans.

Read `command.md` completely and execute it with the invocation payload as `$ARGUMENTS`.
Preserve the semantic command ID, gates, status literals, scope, and validation behavior.
