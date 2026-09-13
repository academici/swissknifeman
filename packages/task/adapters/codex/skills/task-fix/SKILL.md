---
name: task-fix
description: "Мелкая ПРАВКА: узкий single-agent, без fan-out, token-frugal. Пинит implementation/medium."
---

# Task fix

Generated Codex adapter for semantic command `task:fix`.

- Invocation: `$ task:fix <arguments>`
- Routing: `implementation/medium -> gpt-5.6-terra/medium`
- Canonical source: `packages/task/commands/fix.md`
- Canonical SHA-256: `sha256:25678f123188ada21e102329b854b7208b73c4b2cb3c126c2fd72d365426b1ab`
- Runtime projection: `command.md` (generated and provenance-locked; never edit it as source)

Read `references/intent-routing.md` from the configured Task marketplace runtime before selecting
the workflow. Skill relevance alone is not workflow authority; the latest explicit owner
request determines the work product. Direct development and fixes require no plan lifecycle.

Read `command.md` completely and execute it with the invocation payload as `$ARGUMENTS`.
Preserve the semantic command ID, gates, status literals, scope, and validation behavior.
