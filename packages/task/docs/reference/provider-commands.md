# Provider task commands

Generated from the validated provider-command parity report. Do not edit manually.

Contract: `1.0.0` · Catalog: `1.0.0`

## Command matrix

| Semantic ID | Canonical source / SHA-256 | Neutral route | Capabilities | Claude Code | Codex |
|:--|:--|:--|:--|:--|:--|
| `task:design` | `packages/task/commands/design.md`<br>`sha256:3e2215a33373d1403e46b7c083a0d8f9b1ce8f52b203f33db6b75c349e52c0a9` | `fixed · frontier/high` | `skills.repository`<br>`command.filesystem-read`<br>`command.filesystem-write`<br>`command.external-research`<br>`command.subagents` | `/task:design <arguments>`<br>`opus/high` | `$ task:design <arguments>`<br>`gpt-5.6-sol/high` |
| `task:dev` | `packages/task/commands/dev.md`<br>`sha256:80eca26ed89d46495b3a7487b28849d5f2728c41d7b19f305c6fc117a7433cef` | `fixed · implementation/high` | `skills.repository`<br>`command.filesystem-read`<br>`command.filesystem-write`<br>`command.git-read`<br>`command.git-write`<br>`command.external-research`<br>`command.subagents` | `/task:dev <arguments>`<br>`sonnet/high` | `$ task:dev <arguments>`<br>`gpt-5.6-terra/high` |
| `task:fix` | `packages/task/commands/fix.md`<br>`sha256:4d63fbb7b4b281671c9be62d149dd3c203400287b76e0fccff8b76e600866019` | `fixed · implementation/medium` | `skills.repository`<br>`command.filesystem-read`<br>`command.filesystem-write`<br>`command.git-read`<br>`command.git-write` | `/task:fix <arguments>`<br>`sonnet/medium` | `$ task:fix <arguments>`<br>`gpt-5.6-terra/medium` |
| `task:make-workflow` | `packages/task/commands/make-workflow.md`<br>`sha256:f0c032bd66f9f19cf4e1b52c9ffca5cce6d6cd3b4029b29e7b587d13d76ec472` | `fixed · implementation/high` | `skills.repository`<br>`command.filesystem-read`<br>`command.filesystem-write`<br>`command.subagents`<br>`command.workflow-carrier` | `/task:make-workflow <arguments>`<br>`sonnet/high` | `$ task:make-workflow <arguments>`<br>`gpt-5.6-terra/high` |
| `task:research` | `packages/task/commands/research.md`<br>`sha256:417b37dbca208f58ec3ca9373736dde751db43be02d2910180377649df631d9b` | `fixed · frontier/high` | `skills.repository`<br>`command.filesystem-read`<br>`command.filesystem-write`<br>`command.external-research`<br>`command.subagents` | `/task:research <arguments>`<br>`opus/high` | `$ task:research <arguments>`<br>`gpt-5.6-sol/high` |
| `task:review` | `packages/task/commands/review.md`<br>`sha256:2a027c9f5d627305927c3ec38525b15858ca2902df082b883ab95b5c367b5c66` | `fixed · frontier/xhigh` | `skills.repository`<br>`command.filesystem-read`<br>`command.git-read`<br>`command.external-research`<br>`command.subagents` | `/task:review <arguments>`<br>`opus/xhigh` | `$ task:review <arguments>`<br>`gpt-5.6-sol/xhigh` |
| `task:plan-design` | `packages/task/commands/plan-design.md`<br>`sha256:921a608b8763ac890a2d2b275be80ba270f75a0917cba7293eb3741db1d4c0d7` | `fixed · frontier/high` | `skills.repository`<br>`command.filesystem-read`<br>`command.filesystem-write`<br>`command.git-read`<br>`command.external-research` | `/task:plan-design <arguments>`<br>`opus/high` | `$ task:plan-design <arguments>`<br>`gpt-5.6-sol/high` |
| `task:plan-exec` | `packages/task/commands/plan-exec.md`<br>`sha256:80ada213734c93a6137406933d1c3cf319935978158c4ff7b9b3faef284bf784` | `fixed · implementation/medium` | `skills.repository`<br>`command.filesystem-read`<br>`command.filesystem-write`<br>`command.git-read`<br>`command.git-write` | `/task:plan-exec <arguments>`<br>`sonnet/medium` | `$ task:plan-exec <arguments>`<br>`gpt-5.6-terra/medium` |
| `task:plan-run` | `packages/task/commands/plan-run.md`<br>`sha256:4a598a6047c214d7151538bab9d8f6f0120a5430d0af9e28009b69a303c254be` | `inherited-plan · routing-required/routing-required` | `skills.repository`<br>`command.filesystem-read`<br>`command.filesystem-write`<br>`command.git-read`<br>`command.git-write` | `/task:plan-run <arguments>`<br>`routing-required/routing-required` | `$ task:plan-run <arguments>`<br>`routing-required/routing-required` |
| `task:plan-close` | `packages/task/commands/plan-close.md`<br>`sha256:fc87cc465062aecc166c7f9e7cff56fd85fdf3e45f69754f8a67abc4851e042b` | `fixed · implementation/low` | `skills.repository`<br>`command.filesystem-read`<br>`command.filesystem-write`<br>`command.git-read`<br>`command.git-write` | `/task:plan-close <arguments>`<br>`sonnet/low` | `$ task:plan-close <arguments>`<br>`gpt-5.6-terra/low` |
| `task:plan-audit` | `packages/task/commands/plan-audit.md`<br>`sha256:ea4be4ecaf32eb680bf62b20991d76b95d539f8a8c0647c7a38b51ad0a968fb4` | `fixed · frontier/xhigh` | `skills.repository`<br>`command.filesystem-read`<br>`command.filesystem-write`<br>`command.git-read` | `/task:plan-audit <arguments>`<br>`opus/xhigh` | `$ task:plan-audit <arguments>`<br>`gpt-5.6-sol/xhigh` |

## Semantic Next forms

| Kind | Semantic carrier | Claude Code | Codex | Diagnostics |
|:--|:--|:--|:--|:--|
| `exec-items` | `{"arguments": ["PLAN", "P4.5"], "cold_start_scope": [], "command_id": "task:plan-exec", "context_kind": "same-session", "item_ids": [], "kind": "exec-items", "plan_id": "PLAN"}` | `/task:plan-exec PLAN P4.5` | `$ task:plan-exec PLAN P4.5` | `—` |
| `run-items` | `{"arguments": ["PLAN", "P4.5"], "cold_start_scope": [], "command_id": "task:plan-run", "context_kind": "same-session", "item_ids": [], "kind": "run-items", "plan_id": "PLAN"}` | `/task:plan-run PLAN P4.5` | `$ task:plan-run PLAN P4.5` | `—` |
| `audit-design` | `{"arguments": ["PLAN", "design"], "cold_start_scope": [], "command_id": "task:plan-audit", "context_kind": "same-session", "item_ids": [], "kind": "audit-design", "plan_id": "PLAN"}` | `/task:plan-audit PLAN design` | `$ task:plan-audit PLAN design` | `—` |
| `design-phase` | `{"arguments": ["PLAN", "P5"], "cold_start_scope": [], "command_id": "task:plan-design", "context_kind": "same-session", "item_ids": [], "kind": "design-phase", "plan_id": "PLAN"}` | `/task:plan-design PLAN P5` | `$ task:plan-design PLAN P5` | `—` |
| `design-item` | `{"arguments": ["PLAN", "P4.5"], "cold_start_scope": [], "command_id": "task:plan-design", "context_kind": "same-session", "item_ids": [], "kind": "design-item", "plan_id": "PLAN"}` | `/task:plan-design PLAN P4.5` | `$ task:plan-design PLAN P4.5` | `—` |
| `design-finish` | `{"arguments": ["PLAN", "finish"], "cold_start_scope": [], "command_id": "task:plan-design", "context_kind": "same-session", "item_ids": [], "kind": "design-finish", "plan_id": "PLAN"}` | `/task:plan-design PLAN finish` | `$ task:plan-design PLAN finish` | `—` |
| `design-roadmap` | `{"arguments": ["PLAN", "roadmap"], "cold_start_scope": [], "command_id": "task:plan-design", "context_kind": "same-session", "item_ids": [], "kind": "design-roadmap", "plan_id": "PLAN"}` | `/task:plan-design PLAN roadmap` | `$ task:plan-design PLAN roadmap` | `—` |
| `audit-phase` | `{"arguments": ["PLAN", "P4"], "cold_start_scope": [], "command_id": "task:plan-audit", "context_kind": "same-session", "item_ids": [], "kind": "audit-phase", "plan_id": "PLAN"}` | `/task:plan-audit PLAN P4` | `$ task:plan-audit PLAN P4` | `—` |
| `close` | `{"arguments": ["PLAN", "P4"], "cold_start_scope": [], "command_id": "task:plan-close", "context_kind": "same-session", "item_ids": [], "kind": "close", "plan_id": "PLAN"}` | `/task:plan-close PLAN P4` | `$ task:plan-close PLAN P4` | `—` |
| `archive` | `{"arguments": ["archive", "PLAN"], "cold_start_scope": [], "command_id": "task:plan-close", "context_kind": "same-session", "item_ids": [], "kind": "archive", "plan_id": "PLAN"}` | `/task:plan-close archive PLAN` | `$ task:plan-close archive PLAN` | `—` |
| `terminal` | `{"arguments": ["план", "закрыт"], "cold_start_scope": [], "command_id": null, "context_kind": "same-session", "item_ids": [], "kind": "terminal", "plan_id": null}` | `—` | `—` | `—` |
| `manual` | `{"arguments": ["frontier/xhigh"], "cold_start_scope": [], "command_id": null, "context_kind": "same-session", "item_ids": [], "kind": "manual", "plan_id": null}` | `—` | `—` | `—` |
| `waiting` | `{"arguments": ["gate", "P4", "terminal", "→", "audit-phase:", "task:plan-audit", "PLAN", "P4"], "cold_start_scope": [], "command_id": null, "context_kind": "same-session", "item_ids": [], "kind": "waiting", "plan_id": null}` | `—` | `—` | `—` |

## Conformance result

- Semantic inventory: `missing=[]`, `extra=[]`, `duplicates=[]`.
- Claude Code projection: `missing=[]`, `extra=[]`, `duplicates=[]`.
- Codex projection: `missing=[]`, `extra=[]`, `duplicates=[]`.
- Unknown, ambiguous, unsupported, undershoot, invalid invocation and source drift are fail-closed before write.
