# Reference products — Maestro and Superset — 2026-08-03

Only public first-party material was inspected. External code is a pattern source, not vendored
content or a proposed runtime dependency.

## Sources

- [RunMaestro/Maestro](https://github.com/RunMaestro/Maestro) — public orchestration command
  center with fresh task sessions, filesystem playbooks, headless JSONL, provider pass-through,
  message queue, worktree subagents and usage/cost views. License observed in repository: AGPL-3.0.
- [superset-sh/superset](https://github.com/superset-sh/superset) — terminal-first multi-agent
  workspace product. Its README and docs describe isolated worktrees, attention indicators,
  persistent sessions, provider/agent launch settings and scheduled runs. License: Elastic License 2.0.
- [Superset workspaces](https://docs.superset.sh/workspaces),
  [AI agents](https://docs.superset.sh/agent-integration), and
  [automations](https://docs.superset.sh/automations) — current first-party behavior details.

## Adopt / adapt / reject

| Product pattern | Verdict | Artifex interpretation |
|:--|:--|:--|
| Fresh session per task/slice | Adopt | One fresh provider process/context per compiled slice; no rolling transcript. |
| Filesystem playbook/checklist and run history | Adapt | Frozen slice manifest + append-only event journal; prose checklist never becomes execution SSOT. |
| Headless JSONL stream | Adopt | Adapter emits normalized events into `worker-envelope-v1`; raw streams remain redacted evidence inputs. |
| Message queue / needs-attention state | Adapt | Ordered owner queue with bounded batch and severity; no chat platform in v1. |
| Cost/usage dashboard | Adapt | Machine evidence first; terminal report before any UI. Unknown cost fields remain unknown. |
| Worktree per independent task | Adopt selectively | Required for parallel write slices; sequential/no-worktree stays cheaper for a single write lane. |
| Persistent session surviving restarts | Adapt | Persist run/slice identity and provider session reference, but replay from Artifex WAL rather than terminal state alone. |
| At-least-once scheduled dispatch | Adopt as failure assumption | Stable idempotency keys, duplicate detection and reconcile are mandatory; Superset explicitly warns automations may dispatch twice. |
| 10+ parallel agents / compare winners | Reject for v1 | Conflicts and token duplication oppose the owner's objective; cap at 2 only with independence proof. |
| Desktop command center, diff editor, remote hosts | Reject for v1 | Product/UI surface does not prove supervisor reliability or economy. |
| Product runtime/license stack | Reject | No AGPL/ELv2 code, Bun/Electron/Postgres/Temporal dependency or runtime coupling. |

## Important negative lesson

Superset's current automation docs state at-least-once delivery and no completion tracking in v1.
That is exactly the gap Artifex must close: `dispatched` is not `accepted`, and a durable supervisor
must independently reconcile completion, validation, duplicate delivery and side effects.

RAG:✅ first-party repository/docs read 2026-08-03.
