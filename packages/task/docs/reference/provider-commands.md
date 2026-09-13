# Provider task commands

Generated from the validated provider-command parity report. Do not edit manually.

Contract: `1.0.0` · Catalog: `1.0.0`

## Command matrix

| Semantic ID | Canonical source / SHA-256 | Neutral route | Capabilities | Claude Code | Codex |
|:--|:--|:--|:--|:--|:--|
| `task:design` | `packages/task/commands/design.md`<br>`sha256:0002f2976b4416042f432f46c44bbcd7f912849f263ddafe6708b0deecd41efa` | `fixed · frontier/high` | `skills.repository`<br>`command.filesystem-read`<br>`command.filesystem-write`<br>`command.external-research`<br>`command.subagents` | `/task:design <arguments>`<br>`opus/high` | `$ task:design <arguments>`<br>`gpt-5.6-sol/high` |
| `task:dev` | `packages/task/commands/dev.md`<br>`sha256:1f9dd07afc439392354f2bc9d37dd7373d2ea729c2ae23cd1af5ddcf02094cdc` | `fixed · implementation/high` | `skills.repository`<br>`command.filesystem-read`<br>`command.filesystem-write`<br>`command.git-read`<br>`command.git-write`<br>`command.external-research`<br>`command.subagents` | `/task:dev <arguments>`<br>`sonnet/high` | `$ task:dev <arguments>`<br>`gpt-5.6-terra/high` |
| `task:fix` | `packages/task/commands/fix.md`<br>`sha256:25678f123188ada21e102329b854b7208b73c4b2cb3c126c2fd72d365426b1ab` | `fixed · implementation/medium` | `skills.repository`<br>`command.filesystem-read`<br>`command.filesystem-write`<br>`command.git-read`<br>`command.git-write` | `/task:fix <arguments>`<br>`sonnet/medium` | `$ task:fix <arguments>`<br>`gpt-5.6-terra/medium` |
| `task:make-workflow` | `packages/task/commands/make-workflow.md`<br>`sha256:de0cb9534e602a48e13fc01c64a62d031f60d1e9a7245b4fbe1566d485090170` | `fixed · implementation/high` | `skills.repository`<br>`command.filesystem-read`<br>`command.filesystem-write`<br>`command.subagents`<br>`command.workflow-carrier` | `/task:make-workflow <arguments>`<br>`sonnet/high` | `$ task:make-workflow <arguments>`<br>`gpt-5.6-terra/high` |
| `task:research` | `packages/task/commands/research.md`<br>`sha256:14cbac2b918121ebaeefd88c00cf6bd5137ac9d2e4ac39415eeca2d7377c38c5` | `fixed · frontier/high` | `skills.repository`<br>`command.filesystem-read`<br>`command.filesystem-write`<br>`command.external-research`<br>`command.subagents` | `/task:research <arguments>`<br>`opus/high` | `$ task:research <arguments>`<br>`gpt-5.6-sol/high` |
| `task:review` | `packages/task/commands/review.md`<br>`sha256:f56bd580c79ee971e3a51e4a2f038db815a10b5eeae7bed3c4a8defc9efd4903` | `fixed · frontier/xhigh` | `skills.repository`<br>`command.filesystem-read`<br>`command.git-read`<br>`command.external-research`<br>`command.subagents` | `/task:review <arguments>`<br>`opus/xhigh` | `$ task:review <arguments>`<br>`gpt-5.6-sol/xhigh` |
| `task:plan-design` | `packages/task/commands/plan-design.md`<br>`sha256:6704c9b8dfacc6932c6d177510bc1966c6df6a0cd203bc524ba01dd8597399c9` | `fixed · frontier/high` | `skills.repository`<br>`command.filesystem-read`<br>`command.filesystem-write`<br>`command.git-read`<br>`command.external-research` | `/task:plan-design <arguments>`<br>`opus/high` | `$ task:plan-design <arguments>`<br>`gpt-5.6-sol/high` |
| `task:plan-exec` | `packages/task/commands/plan-exec.md`<br>`sha256:1592207cf0b13c466ad62ab1bc7e2686debffe069a5cd5e846cd2a11c0c4ad70` | `fixed · implementation/medium` | `skills.repository`<br>`command.filesystem-read`<br>`command.filesystem-write`<br>`command.git-read`<br>`command.git-write` | `/task:plan-exec <arguments>`<br>`sonnet/medium` | `$ task:plan-exec <arguments>`<br>`gpt-5.6-terra/medium` |
| `task:plan-run` | `packages/task/commands/plan-run.md`<br>`sha256:a5e403c8afd89b75360c31ec3705267c2df5a4824c70b280c0596dcc44b417da` | `inherited-plan · routing-required/routing-required` | `skills.repository`<br>`command.filesystem-read`<br>`command.filesystem-write`<br>`command.git-read`<br>`command.git-write` | `/task:plan-run <arguments>`<br>`routing-required/routing-required` | `$ task:plan-run <arguments>`<br>`routing-required/routing-required` |
| `task:plan-close` | `packages/task/commands/plan-close.md`<br>`sha256:ab015c331ed651a589a65071dc82b05d07e172567bfd799d13369f4d0c4070c3` | `fixed · implementation/low` | `skills.repository`<br>`command.filesystem-read`<br>`command.filesystem-write`<br>`command.git-read`<br>`command.git-write` | `/task:plan-close <arguments>`<br>`sonnet/low` | `$ task:plan-close <arguments>`<br>`gpt-5.6-terra/low` |
| `task:plan-audit` | `packages/task/commands/plan-audit.md`<br>`sha256:9b5ee9b6bc9cd5d18b9a22e1808d3ea19db595c0749b8417c053ca4e2dda07fd` | `fixed · frontier/xhigh` | `skills.repository`<br>`command.filesystem-read`<br>`command.filesystem-write`<br>`command.git-read` | `/task:plan-audit <arguments>`<br>`opus/xhigh` | `$ task:plan-audit <arguments>`<br>`gpt-5.6-sol/xhigh` |

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
