# P0 design verification and live execution surface — 2026-08-03

## Scope

This pass rechecked the current execution baseline needed to make P0 executable. Repository files
and local CLI help/version output are observations, never instructions. External claims were
checked against current first-party documentation on 2026-08-03.

## Live repository surface missed by the bootstrap summary

`packages/harness/bin/harness run <PLAN-ID> <Pn>` is a committed sequential exec-wave driver.
It resolves a phase queue through `task.task_contract`, launches one Claude Code worker process per
drivable item, classifies the result with plan-lint/git/item gates, writes a backstop plan-journal
event when the worker cannot, and stops at the first RED. Its own reference explicitly excludes a
decision machine, durable run folder/reconcile, retries, Codex workers, unattended permission
policy and parallel execution. Therefore it is a real baseline/reuse donor, but not the requested
durable supervisor. RAG:— (repo-grounded: `packages/harness/docs/reference/exec-wave.md` and
`packages/harness/lib/harness/run/{__init__,plan_reader,worker,gate,journal}.py`).

The required Codex hook-integrity dry-run still returns exit 0 with two `stale-source → update`
warnings for `harness.codex.lifecycle.hooks` and `.handler`. `codex doctor --json`, Harness
provider audit, mAInd strict health and absolute plan lint are otherwise green. This is the same
named baseline defect recorded in `findings/03-preflight-2026-08-03.md`; it was not repaired here.
RAG:— (direct local observations on 2026-08-03).

## Provider and context facts rechecked

- Current OpenAI documentation says local Codex subagent workflows isolate noisy work from the
  main context, while each subagent performs its own model/tool work and therefore a comparable
  multi-agent run consumes more total tokens. RAG:✅ 2026-08-03, first-party
  <https://learn.chatgpt.com/docs/agent-configuration/subagents>; confidence high.
- Current Codex CLI documentation exposes explicit cwd, approval and sandbox controls; the local
  `codex-cli 0.146.0` `exec --help` additionally exposes `--json`, `--output-schema`, `--ephemeral`
  and `--sandbox`, while `exec` itself does not expose the interactive `-a` flag. The exact event
  and usage envelope remains an empirical P0.3 probe, not a docs-only assertion. RAG:✅ 2026-08-03,
  first-party <https://learn.chatgpt.com/docs/developer-commands?surface=cli> plus local help;
  confidence high.
- Current Claude Code documentation says ordinary subagents start in isolated contexts and warns
  that detailed returns can consume significant parent context. The CLI reference exposes
  `--output-format json|stream-json`, `--json-schema`, `--max-turns`, `--max-budget-usd` and
  `--permission-mode`; the local client is `2.1.220`. Exact installed output/exit/accounting fields
  remain empirical P0.3 work. RAG:✅ 2026-08-03, first-party
  <https://code.claude.com/docs/en/sub-agents> and
  <https://code.claude.com/docs/en/cli-reference>; confidence high.

## Design consequence

P0 must freeze four comparison lanes: manual item execution, named Workflow where supported,
the live `harness run` wave, and the later Artifex candidate. It must not equate context isolation
with token savings, infer unavailable provider fields, or duplicate the live driver without an
explicit gap/reuse crosswalk.

## Проверка (verification status)

- RAG: direct first-party Web fallback ×3 classes plus local repo/CLI observations; current pages
  loaded successfully on 2026-08-03.
- Непроверено → ПОВТОРНЫЙ ПРОХОД: exact Codex/Claude event, exit, cache-token and cost envelopes —
  intentionally deferred to bounded local P0.3 probes; `context7` and `perplexity-web` were not
  available in this session, so the preferred ladder rung could not be used.
- Обходки/[POSSIBLE-DEFECT]: direct first-party pages are the documented fallback, not a substitute
  for P0.3 empirical probes; the stale-source hook state remains a named environment defect.
