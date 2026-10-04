---
name: task-plan-audit
description: "Only when explicitly invoked. Read-only Task design or phase audit; phase audit needs owner-bound consent."
---

# Task plan-audit

Generated Codex adapter for semantic command `task:plan-audit`.

- Invocation: `$ task:plan-audit <arguments>`
- Routing: `frontier/xhigh -> gpt-6-astra/xhigh`
- Canonical source: `packages/task/commands/plan-audit.md`
- Canonical SHA-256: `sha256:2b036b03f36c450e7a119d39cf284efe4247cc31a6089344a5b3d694954679ac`
- Runtime projection: `command.md` (generated and provenance-locked; never edit it as source)

Activate only when the owner explicitly invokes this Task command or skill. Task is not an
automatic workflow for development, fixes, design, or a repository containing plans.

Read `command.md` completely and execute it with the invocation payload as `$ARGUMENTS`.
Preserve the semantic command ID, gates, status literals, scope, and validation behavior.
