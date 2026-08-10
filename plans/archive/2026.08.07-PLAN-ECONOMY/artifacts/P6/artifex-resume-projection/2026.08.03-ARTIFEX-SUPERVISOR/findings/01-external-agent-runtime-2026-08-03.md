# Current agent/runtime verification — 2026-08-03

## Verified facts

| Fact class | First-party source | Design consequence |
|:--|:--|:--|
| Codex subagents have independent context and can protect the parent from noisy work, but a multi-agent run can consume more total tokens than a comparable single-agent run. Parallel write-heavy work raises conflict/coordination risk. | [OpenAI subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents) | Fresh workers are an isolation tool, not an automatic economy claim; default to sequential writes and measure total tokens. |
| Long-horizon Codex work benefits from an explicit loop, externalized plan/status state, small verifiable milestones and continuous validation. | [OpenAI long-horizon tasks](https://developers.openai.com/blog/run-long-horizon-tasks-with-codex) | Keep the durable coordinator outside model context and make each slice independently acceptable. |
| Claude subagents have isolated context, configurable turn limits and current nested-spawn support; verbose returns can still consume the parent context. | [Claude Code subagents](https://code.claude.com/docs/en/sub-agents) | Disable or cap worker spawning by run policy; cap the return envelope rather than trusting summaries to stay small. |
| Claude headless CLI exposes structured output, JSON schema, max-turn and budget controls; approval/permission behavior remains an explicit runtime boundary. | [Claude Code CLI reference](https://code.claude.com/docs/en/cli-reference) | Adapter contract must pin observed version/capability and classify approval/budget/quota exits. |
| Deterministic workflow code must not directly perform nondeterministic/LLM calls; those calls belong behind an activity boundary. Activities should be idempotent and small enough to retry/recover. | [Temporal workflow definition](https://docs.temporal.io/workflow-definition), [Temporal activities](https://docs.temporal.io/activities) | Artifex scheduler and replay are deterministic; workers are side-effecting activities with stable attempt keys. |
| A WAL makes commit an append operation and requires explicit checkpoint/durability handling; WAL files are persistent state and concurrency has host/version constraints. | [SQLite WAL](https://sqlite.org/wal.html) | Use the principle, not SQLite as prototype SSOT: hash-chained JSONL plus atomic derived snapshots is simpler and stdlib-only. |

## Verification discipline

Three Perplexity retrieval attempts were used as flat-rate drafts. The OpenAI and Temporal answers
returned weak/non-first-party source lists, and one Anthropic synthesis carried an outdated nesting
claim. None was accepted as final authority. Every design-bearing class above was independently
verified on the directly linked first-party page.

## Still empirical

- Exact current Codex/Claude output/event schemas and exit mappings in the installed CLI versions.
- Provider token/cache/cost fields available without exposing prompts.
- Normalized economy against this repository's matched Workflow/manual baseline.

These are P0.3/P0.5 measurements; they remain `[UNVERIFIED]` until captured from the local runtimes.
