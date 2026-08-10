# Finish verification — 2026-08-03

## Scope and evidence boundary

The finish pass rechecked every external fact class supporting the P0–P6 design and reconciled the
complete plan against current repository evidence. It did not execute an item, call a provider,
repair hooks, create a package, or mutate product/fleet/release state. Planned outputs remain future
producer deliverables, not files claimed to exist today.

## External fact-class recheck

| Fact class | Primary evidence rechecked | Retained design consequence |
|:--|:--|:--|
| Codex non-interactive workers and isolation/cost boundary | [Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode.md), [Codex subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents) | Keep fresh bounded workers and measure total usage; do not infer economy from context isolation. |
| Claude headless workers and isolated subagent context | [Claude CLI reference](https://code.claude.com/docs/en/cli-reference), [Claude subagents](https://code.claude.com/docs/en/sub-agents) | Keep capability/version probes and a provider-neutral capped envelope. |
| Deterministic orchestration and retryable side effects | [Temporal workflow definition](https://docs.temporal.io/workflow-definition), [Temporal activities](https://docs.temporal.io/activities) | Scheduler decisions stay deterministic; LLM/process calls remain idempotency-keyed activities. |
| WAL/checkpoint boundary | [SQLite WAL](https://sqlite.org/wal.html) | Adapt durability principles without adding SQLite as runtime SSOT. |
| Worktree isolation and lifecycle | [`git-worktree`](https://git-scm.com/docs/git-worktree) | Preserve one writer per linked worktree and serialize integration/removal. |
| Python 3.12 lock/replace/fsync primitives | [Python 3.12 `fcntl`](https://docs.python.org/3.12/library/fcntl.html), [`os.replace`](https://docs.python.org/3.12/library/os.html#os.replace), [`os.fsync`](https://docs.python.org/3.12/library/os.html#os.fsync) | The stdlib prototype remains feasible; power-loss claims still require P4 fault evidence. |
| Reference-product behavior and licensing boundary | [Maestro repository](https://github.com/RunMaestro/Maestro), [Superset automations](https://docs.superset.sh/automations) | Continue pattern-only adaptation; at-least-once dispatch requires idempotent reconciliation. |

The facts above were accepted only from current first-party/official sources. Context7 corroborated
Git worktree and Python primitive semantics. The sequential Perplexity official-only query returned
secondary-source synthesis, so it was rejected as verdict authority and the direct primary pages
above were used instead. RAG:✅ 2026-08-03 primary-source recheck.

## Repository and environment recheck

- `codex doctor --json` and `packages/maind/bin/maind health --cwd` were green; the mAInd
  round-trip was treated only as health evidence, not as plan truth. RAG:— (observed preflight).
- `packages/harness/bin/harness doctor --target <repo>` was green. The trusted observer hook
  dry-run exited 0 but remained non-green with two `stale-source → update (source-changed)` Codex
  lifecycle rows. No finish decision waives that warning. RAG:— (observed preflight).
- The plan directory remains untracked within a foreign dirty worktree, so HEAD delta attribution is
  unavailable; absolute plan validation is still meaningful. RAG:— (observed repository state).

## Verification status

- **RAG:** Context7 → sequential Perplexity → direct primary-web fallback completed for all external
  fact classes on which the design verdict stands; degraded Perplexity output was not promoted to
  evidence.
- **Unverified → repeat pass:** installed provider capability envelopes, provider accounting,
  filesystem power-loss behavior, fault recovery and pilot economics are intentionally empirical
  P0.3/P4/P5 outputs and must be remeasured at execution time.
- **Workarounds/[POSSIBLE-DEFECT]:** the persistent hook `stale-source` warning and untracked-plan
  baseline limit remain disclosed. Neither is reported as green or repaired by finish.
