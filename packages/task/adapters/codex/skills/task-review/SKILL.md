---
name: task-review
description: "Only when explicitly invoked. Read-only review of code, docs or specs; rank findings by demonstrated impact."
---

# Task review

Generated Codex adapter for semantic command `task:review`.

- Invocation: `$ task:review <arguments>`
- Routing: `frontier/xhigh -> gpt-5.6-sol/xhigh`
- Canonical source: `packages/task/commands/review.md`
- Canonical SHA-256: `sha256:541d71ed58c765e34d50dcde3ca6ccc62d60e677fb1423fcfd0f1e172b2fa9ab`
- Runtime projection: `command.md` (generated and provenance-locked; never edit it as source)

Activate only when the owner explicitly invokes this Task command or skill. Task is not an
automatic workflow for development, fixes, design, or a repository containing plans.

Read `command.md` completely and execute it with the invocation payload as `$ARGUMENTS`.
Preserve the semantic command ID, gates, status literals, scope, and validation behavior.
