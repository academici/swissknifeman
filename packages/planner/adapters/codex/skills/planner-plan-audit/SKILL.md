---
name: planner-plan-audit
description: "Only when explicitly invoked. Read-only planner plan audit of a design or a phase on explicit owner request."
---

# Planner plan-audit

Generated Codex adapter for semantic command `planner:plan-audit`.

- Invocation: `$ planner:plan-audit <arguments>`
- Routing: `frontier/xhigh -> gpt-6-astra/xhigh`
- Canonical source: `packages/planner/commands/plan-audit.md`
- Canonical SHA-256: `sha256:4c208ed87d16686c3965ffcbb33f942fc99eaf295cea0f13619c9443c75a21ec`
- Runtime projection: `command.md` (generated and provenance-locked; never edit it as source)

Activate only when the owner explicitly invokes this planner command or skill. Planner is not an
automatic workflow for development, fixes, design, or a repository containing plans.

Read `command.md` completely and execute it with the invocation payload as `$ARGUMENTS`.
Preserve the semantic command ID, gates, status literals, scope, and validation behavior.
