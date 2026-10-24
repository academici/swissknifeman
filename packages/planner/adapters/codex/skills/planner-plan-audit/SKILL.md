---
name: planner-plan-audit
description: "Only when explicitly invoked. Audit plan executability, execution economy and phase readiness on explicit owner request."
---

# Planner plan-audit

Generated Codex adapter for semantic command `planner:plan-audit`.

- Invocation: `$ planner:plan-audit <arguments>`
- Routing: `frontier/xhigh -> gpt-6-astra/xhigh`
- Canonical source: `packages/planner/commands/plan-audit.md`
- Canonical SHA-256: `sha256:00787d0d0207672b8669544ece39360c45d2ea73b87b1e6bd601c6d6682a440b`
- Runtime projection: `command.md` (generated and provenance-locked; never edit it as source)

Activate only when the owner explicitly invokes this planner command or skill. Planner is not an
automatic workflow for development, fixes, design, or a repository containing plans.

Read `command.md` completely and execute it with the invocation payload as `$ARGUMENTS`.
Preserve the semantic command ID, gates, status literals, scope, and validation behavior.
