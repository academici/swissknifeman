# Provider task commands

Generated from the validated provider-command parity report. Do not edit manually.

Contract: `1.0.0` · Catalog: `1.0.0`

## Command matrix

| Semantic ID | Canonical source / SHA-256 | Neutral route | Capabilities | Claude Code | Codex |
|:--|:--|:--|:--|:--|:--|
| `task:design` | `packages/task/commands/design.md`<br>`sha256:2375c5d8d953aa704f9b96aac97bcc3800e6c97f198a0ec86c67fda61b3318ac` | `fixed · frontier/high` | `skills.repository`<br>`command.filesystem-read`<br>`command.filesystem-write`<br>`command.external-research`<br>`command.subagents` | `/task:design <arguments>`<br>`opus/high` | `$ task:design <arguments>`<br>`gpt-5.6-sol/high` |
| `task:dev` | `packages/task/commands/dev.md`<br>`sha256:4b3a0743fabdf7e472128c11c0b5c7d713d2416055e5810b79aa778554deaee5` | `fixed · implementation/high` | `skills.repository`<br>`command.filesystem-read`<br>`command.filesystem-write`<br>`command.git-read`<br>`command.git-write`<br>`command.external-research`<br>`command.subagents` | `/task:dev <arguments>`<br>`sonnet/high` | `$ task:dev <arguments>`<br>`gpt-5.6-terra/high` |
| `task:fix` | `packages/task/commands/fix.md`<br>`sha256:a7ff7beab7f0f485f8caefeda1d4cf774d9bd310bd20f2407fea1f3dbcff4973` | `fixed · implementation/medium` | `skills.repository`<br>`command.filesystem-read`<br>`command.filesystem-write`<br>`command.git-read`<br>`command.git-write` | `/task:fix <arguments>`<br>`sonnet/medium` | `$ task:fix <arguments>`<br>`gpt-5.6-terra/medium` |
| `task:make-workflow` | `packages/task/commands/make-workflow.md`<br>`sha256:de0cb9534e602a48e13fc01c64a62d031f60d1e9a7245b4fbe1566d485090170` | `fixed · implementation/high` | `skills.repository`<br>`command.filesystem-read`<br>`command.filesystem-write`<br>`command.subagents`<br>`command.workflow-carrier` | `/task:make-workflow <arguments>`<br>`sonnet/high` | `$ task:make-workflow <arguments>`<br>`gpt-5.6-terra/high` |
| `task:research` | `packages/task/commands/research.md`<br>`sha256:14cbac2b918121ebaeefd88c00cf6bd5137ac9d2e4ac39415eeca2d7377c38c5` | `fixed · frontier/high` | `skills.repository`<br>`command.filesystem-read`<br>`command.filesystem-write`<br>`command.external-research`<br>`command.subagents` | `/task:research <arguments>`<br>`opus/high` | `$ task:research <arguments>`<br>`gpt-5.6-sol/high` |
| `task:review` | `packages/task/commands/review.md`<br>`sha256:79f984c396e74cc0d1b866d6258d768217d92e6b64945240273d70855c1968c0` | `fixed · frontier/xhigh` | `skills.repository`<br>`command.filesystem-read`<br>`command.git-read`<br>`command.external-research`<br>`command.subagents` | `/task:review <arguments>`<br>`opus/xhigh` | `$ task:review <arguments>`<br>`gpt-5.6-sol/xhigh` |
| `task:plan-design` | `packages/task/commands/plan-design.md`<br>`sha256:bf844e475b3cf55ec4ac4ce715a15692ac53b21f315c585ff9696f30aa3cddf2` | `fixed · frontier/high` | `skills.repository`<br>`command.filesystem-read`<br>`command.filesystem-write`<br>`command.git-read`<br>`command.external-research` | `/task:plan-design <arguments>`<br>`opus/high` | `$ task:plan-design <arguments>`<br>`gpt-5.6-sol/high` |
| `task:plan-exec` | `packages/task/commands/plan-exec.md`<br>`sha256:d0cfac3ae35083579c5a19536c8e8eeec287f4381b1f9bac2483112fc404c1bf` | `fixed · implementation/medium` | `skills.repository`<br>`command.filesystem-read`<br>`command.filesystem-write`<br>`command.git-read`<br>`command.git-write` | `/task:plan-exec <arguments>`<br>`sonnet/medium` | `$ task:plan-exec <arguments>`<br>`gpt-5.6-terra/medium` |
| `task:plan-run` | `packages/task/commands/plan-run.md`<br>`sha256:835d6e3abe3d784d05b236a53c0d1c7bdf50676403d98ea7dff7b4cc0f06668f` | `inherited-plan · routing-required/routing-required` | `skills.repository`<br>`command.filesystem-read`<br>`command.filesystem-write`<br>`command.git-read`<br>`command.git-write` | `/task:plan-run <arguments>`<br>`routing-required/routing-required` | `$ task:plan-run <arguments>`<br>`routing-required/routing-required` |
| `task:plan-close` | `packages/task/commands/plan-close.md`<br>`sha256:7697b4063eac02cef54529eab5e0022e02d61e4241658cdf9f0d5b74b3228236` | `fixed · implementation/low` | `skills.repository`<br>`command.filesystem-read`<br>`command.filesystem-write`<br>`command.git-read`<br>`command.git-write` | `/task:plan-close <arguments>`<br>`sonnet/low` | `$ task:plan-close <arguments>`<br>`gpt-5.6-terra/low` |
| `task:plan-audit` | `packages/task/commands/plan-audit.md`<br>`sha256:7d7d987630ab91b064f5979ed8fc8493cb6a20730ec8e098687748b3746d2afa` | `fixed · frontier/xhigh` | `skills.repository`<br>`command.filesystem-read`<br>`command.filesystem-write`<br>`command.git-read` | `/task:plan-audit <arguments>`<br>`opus/xhigh` | `$ task:plan-audit <arguments>`<br>`gpt-5.6-sol/xhigh` |

## Semantic Next forms

| Kind | Semantic carrier | Claude Code | Codex | Diagnostics |
|:--|:--|:--|:--|:--|
| `exec-items` | `{"arguments": ["PLAN", "P4.5"], "cold_start_scope": [], "command_id": "task:plan-exec", "context_kind": "same-session", "item_ids": [], "kind": "exec-items", "plan_id": "PLAN"}` | `/task:plan-exec PLAN P4.5` | `$ task:plan-exec PLAN P4.5` | `—` |
| `run-items` | `{"arguments": ["PLAN", "P4.5"], "cold_start_scope": [], "command_id": "task:plan-run", "context_kind": "same-session", "item_ids": [], "kind": "run-items", "plan_id": "PLAN"}` | `/task:plan-run PLAN P4.5` | `$ task:plan-run PLAN P4.5` | `—` |
| `audit-design` | `{"arguments": ["PLAN", "design"], "cold_start_scope": [], "command_id": "task:plan-audit", "context_kind": "same-session", "item_ids": [], "kind": "audit-design", "plan_id": "PLAN"}` | `/task:plan-audit PLAN design` | `$ task:plan-audit PLAN design` | `—` |
| `design-phase` | `{"arguments": ["PLAN", "P5"], "cold_start_scope": [], "command_id": "task:plan-design", "context_kind": "same-session", "item_ids": [], "kind": "design-phase", "plan_id": "PLAN"}` | `/task:plan-design PLAN P5` | `$ task:plan-design PLAN P5` | `—` |
| `design-item` | `{"arguments": ["PLAN", "P4.5"], "cold_start_scope": [], "command_id": "task:plan-design", "context_kind": "same-session", "item_ids": [], "kind": "design-item", "plan_id": "PLAN"}` | `/task:plan-design PLAN P4.5` | `$ task:plan-design PLAN P4.5` | `—` |
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
