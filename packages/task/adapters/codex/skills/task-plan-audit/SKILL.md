---
name: task-plan-audit
description: "Only when explicitly invoked. Read-only Task plan audit of a design or a phase on explicit owner request."
---

# Task plan-audit

Generated Codex adapter for semantic command `task:plan-audit`.

- Invocation: `$ task:plan-audit <arguments>`
- Routing: `frontier/xhigh -> gpt-6-astra/xhigh`
- Canonical source: `packages/task/commands/plan-audit.md`
- Canonical SHA-256: `sha256:c56c955b46a6a907b46f5306de2bee25daa30ce809a91efd99a84846989b2de8`
- Runtime projection: `command.md` (generated and provenance-locked; never edit it as source)

Activate only when the owner explicitly invokes this Task command or skill. Task is not an
automatic workflow for development, fixes, design, or a repository containing plans.

Read `command.md` completely and execute it with the invocation payload as `$ARGUMENTS`.
Preserve the semantic command ID, gates, status literals, scope, and validation behavior.
