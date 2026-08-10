# P5 pilot and economy recon — 2026-08-03

## Scope and evidence boundary

This pass designs P5 only. P0–P4 remain unexecuted, so their baseline catalog, provider probes,
contracts, candidate and assurance manifest are terminal preconditions rather than present evidence.
No provider worker, pilot, fault campaign, baseline lane or repository task was executed. The only
live actions were read-only CLI/help, official-documentation and repository inspection.

## Current measurement surfaces

- The installed `codex-cli 0.146.0` exposes `exec --json`, `--ephemeral`, `--output-schema`, model,
  sandbox and explicit cwd controls. The current official non-interactive manual documents JSONL
  `turn.completed.usage` fields for input, cached-input, output and reasoning-output tokens. That
  establishes a documented measurement surface, not the exact installed-event contract: P0.3 must
  still probe the local version and P1.4 must preserve absent/unknown fields. RAG:✅ 2026-08-03,
  [OpenAI Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode.md),
  current manual fetched by the official Codex helper; confidence high.
- The installed Claude Code client is `2.1.220`; its help exposes structured JSON/stream-JSON,
  `--json-schema`, `--max-budget-usd`, `--no-session-persistence`, model/effort and permission/tool
  controls. Current first-party docs state that non-interactive JSON results carry session, usage and
  cost information. Exact fields and error combinations remain empirical P0.3/P3 evidence, not a
  docs-derived parity promise. RAG:✅ 2026-08-03, Context7 `/websites/code_claude` over
  [Claude Code sessions](https://code.claude.com/docs/en/sessions),
  [headless mode](https://code.claude.com/docs/en/headless) and
  [usage monitoring](https://code.claude.com/docs/en/monitoring-usage); confidence high.
- The live Harness Claude wave reader already carries `total_cost_usd`, `num_turns` and
  `duration_ms` when the provider emits them, and preserves `None` when absent. Its wave summary
  counts driver interventions and never manufactures a cost total without an observed value.
  It is a baseline/reuse donor, not an economy adjudicator and not a provider-neutral source.
  RAG:— (repo-grounded: `packages/harness/lib/harness/run/worker.py` and `journal.py`).

## Archive and pilot inputs

- FOREMAN is a historical design donor, not a runnable parser specification. P5 may replay its
  archived run-folder/policy decisions and terminal/skipped cases only through an explicit mapping;
  it may not import the obsolete `driver-plan-protocol.md` as current canon. RAG:— (repo-grounded:
  `roadmap/artifex-thin-wrapper.md` and `plans/archive/2026.07.18-FOREMAN/`).
- AGENT-RELIABILITY supplies machine-readable transition cases, a reliability bank, paired layer-2
  results and the key negative precedent: owner intervention remained `unknown` when the event map
  could not observe the channel. P5 must preserve that unknown instead of treating event absence as
  zero. RAG:— (repo-grounded: `plans/archive/2026.07.24-AGENT-RELIABILITY/artifacts/` and
  `findings/P3.10-layer2-paired.md`).
- P4.5's independent `assurance-manifest-v1.json` is the sole P5 readiness input. Its validator is
  non-green on unresolved severe/security/third-state/provider masking or the effective hook defect.
  P5 cannot substitute direct unit tests, a candidate `green` flag or an exit-zero hook dry-run.
  RAG:— (repo-grounded: `phases/P4.md` and `research/10-p4-assurance-design.md`).

## Trial-design consequence

P5 freezes all archive cases, repository slices, bases, acceptance hashes, providers and baseline
lanes before the first candidate pilot. Shadow replay is non-economic evidence. The reversible pilot
uses exactly three real repository slices in controlled disposable worktrees. Recovery evidence is
kept distinct from the five non-synthetic paired battle waves. The final adjudicator recomputes all
attempt/coordinator/worker totals from minimized evidence; a missing critical field makes only its
dependent GO branch ineligible and can never become zero.

## Preflight integrity observation

`codex doctor --json`, `packages/maind/bin/maind health --cwd --json`, hook-handler compilation and
memory-script syntax are green. The worktree-local absolute-target Harness hook dry-run still exits 0
with `Статус: warning` and both Codex lifecycle projections `stale-source → update`. This pass does
not repair the foreign dirty scope. P4/P5 readiness must keep the exact warning non-green.

## Проверка (verification status)

- RAG: official Codex manual helper ×1; Context7 `/websites/code_claude` ×1 focused accounting
  query; current local CLI/help and repository/archive reads.
- Непроверено → ПОВТОРНЫЙ ПРОХОД: exact terminal P0–P4 schemas, installed provider event/exit/
  quota/accounting records, matched live baselines, real pilot results and provider auth/readiness
  remain execution-time evidence.
- Обходки/[POSSIBLE-DEFECT]: none accepted. Documentation is not substituted for the planned local
  probes; the `stale-source` hook verdict remains a blocker rather than a waived warning.
