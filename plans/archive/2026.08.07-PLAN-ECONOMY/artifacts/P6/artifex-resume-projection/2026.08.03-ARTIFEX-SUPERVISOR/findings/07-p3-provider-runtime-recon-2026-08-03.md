# P3 provider runtime reconciliation — 2026-08-03

## Scope and evidence boundary

This cold-start pass reconciles the current installed Codex/Claude Code CLIs, official provider
documentation and the repository-owned provider carriers needed to detail P3. It does not execute
a plan item or a live model probe. Exact installed event, exit, quota and accounting envelopes
remain outputs of P0.3; documentation and `--help` are not substituted for that empirical matrix.

## Current provider surfaces

### Codex

The installed client reports `codex-cli 0.146.0`. Its local `codex exec --help` exposes an
explicit working root, model selector, sandbox, config overrides, strict config checking,
`--ephemeral`, `--json`, `--output-schema`, `--ignore-user-config` and a stdin prompt sentinel.
The current official non-interactive guide documents JSONL events including thread/turn/item/error
records and a terminal usage object, while the CLI reference documents the same ephemeral,
schema, sandbox and config-override surfaces. `codex exec` has no direct `-a` option in the
installed help; a non-interactive adapter must therefore use an exact verified config override
for approval policy rather than copy the interactive launch form. RAG:✅ 2026-08-03,
[OpenAI Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode.md) and
[Codex CLI reference](https://learn.chatgpt.com/docs/developer-commands?surface=cli#cli-codex-exec),
confidence high; local version/help observed the same day.

Current Codex documentation and `codex features list` identify `features.multi_agent` as the
native subagent-tool gate, stable and enabled by default in this installation. P3 can therefore
test an explicit `--disable multi_agent` default, but must treat its live effect and any future
feature rename as version-gated capability evidence rather than permanent syntax. RAG:✅
2026-08-03, current Codex manual configuration/subagent sections; confidence high.

### Claude Code

The installed client reports `2.1.220 (Claude Code)`. The current official CLI reference exposes
headless `-p`, `--output-format text|json|stream-json`, `--json-schema`, `--max-turns`,
`--max-budget-usd`, `--no-session-persistence`, model/effort selectors, explicit setting sources,
strict MCP config and tool restriction. It explicitly warns that `claude --help` does not list
every supported flag, so absence from the installed help cannot be promoted to `unsupported`.
RAG:✅ 2026-08-03,
[Claude Code CLI reference](https://code.claude.com/docs/en/cli-usage), confidence high.

The official permission-mode reference says `dontAsk` auto-denies anything that would prompt and
allows only pre-approved tools plus recognized read-only commands. `--allowedTools` pre-approves;
`--tools` restricts availability. This gives P3 a fail-closed headless mode without
`bypassPermissions`, provided the exact allow/deny projection is frozen by P0/P1 and verified on
the installed client. RAG:✅ 2026-08-03,
[Claude Code permission modes](https://code.claude.com/docs/en/permission-modes) and
[permissions reference](https://code.claude.com/docs/en/permissions), confidence high.

Neither provider's public documentation supplies a complete version-stable mapping for quota,
approval denial, malformed structured output, timeout, orphan process and every non-zero exit.
Those classes remain `unknown` until P0.3 captures them or P3 observes them safely; text matching
alone cannot become a parity contract. RAG:✅ 2026-08-03 official references above, with the
absence bounded by local probe ownership; confidence medium on absence, high on the required
empirical fallback.

## Repository-owned donors and gaps

- `packages/task/configs/command-routing.json` is the committed SSOT for provider model-class,
  effort, capability and invocation mappings. An adapter may read and hash it; provider model names
  must not be duplicated in plan-local code. RAG:— (repo-grounded).
- `configs/provider-capabilities.json` and Harness's common profile catalog own semantic provider
  capability/security projections. They describe configuration/runtime support, not worker result
  acceptance. RAG:— (repo-grounded).
- `packages/harness/lib/harness/run/worker.py` is a live Claude-only process donor. It already uses
  `SKM_CLAUDE_BIN`, reads Task routing selectors, launches one worker and defensively distinguishes
  run outcome from item acceptance. It intentionally inherits permission policy, retains raw
  result text, has no Codex adapter and has no durable process-group/orphan boundary. P3 reuses the
  named binary override and routing carrier but cannot import this private Claude wave worker or
  treat its narrow exit heuristics as `worker-envelope-v1`. RAG:— (repo-grounded).
- `SKM_CODEX_BIN` already exists in `packages/skiller/lib/skiller/quality/eval.py`; P3 must reuse
  this test/probe override name instead of inventing another binary locator. RAG:— (repo-grounded).
- P2 deliberately ends at a typed no-provider activity port. P3 may add provider-specific files
  and bind that port, but it must not move argv/event semantics into scheduler state transitions.
  RAG:— (repo-grounded: D34 and `research/08-p2-prototype-design.md`).

## Freshness, context and child-policy consequence

A fresh worker attempt means a new OS process, no resume/continue/session reuse and the provider's
non-persistence flag. Repository instructions remain loaded; Claude `--bare` and Codex
`--ignore-rules` are therefore forbidden. Provider-native subagent tools are disabled by default:
Claude can exclude `Agent` through its tool set, and Codex exposes the `multi_agent` feature gate.
If a future frozen slice requests children, P3 v1 returns capability-unsupported/OWNER until the
provider matrix proves an enforceable child count, write scope and budget; a prompt asking the
model to "use at most one" is not a hard boundary. RAG:✅ provider controls above; RAG:— for the
internal fail-closed policy.

## Preflight integrity observation

`codex doctor --json` and `packages/maind/bin/maind health --cwd --json` are green/connected. The
required worktree-local hook integrity dry-run is not green:

1. `packages/harness/bin/harness hooks --target . ... --dry-run` exits with
   `ValueError: root must be explicit and absolute` before checking artifacts;
2. the same command with the absolute repository path completes with warning and reports both
   `harness.codex.lifecycle.hooks` and `.handler` as `stale-source → update`;
3. `python3 -m py_compile .codex/hooks/lifecycle.py` succeeds.
4. `plan_lint --baseline HEAD --gate new` cannot archive this plan path because the whole plan
   directory is still untracked; it degrades to the full `all` gate, whose independent final run
   reports 0 errors and 0 warnings.

The relative-target exception is an environment/CLI normalization defect in the current dirty
worktree; the absolute-target result confirms the previously recorded source drift remains. This
P3 design pass records but does not repair either foreign-scope defect. RAG:— (direct local
observation 2026-08-03).

## Проверка (verification status)

- RAG: fresh Codex manual helper → current official Codex manual; Context7
  `/websites/code_claude` ×2; direct official Anthropic search/fetch ×2 fact classes; local CLI,
  repository and preflight observations.
- Непроверено → ПОВТОРНЫЙ ПРОХОД: exact installed JSON/JSONL terminal records, exit codes,
  quota/approval/budget failure shapes, safe stdin/schema behavior and accounting fields remain
  intentionally assigned to P0.3 and P3's bounded adapter smoke.
- Обходки/[POSSIBLE-DEFECT]: one Perplexity draft cited a non-official secondary source despite an
  official-only query and was rejected; direct first-party sources are the accepted fallback. The
  relative-target Harness exception and absolute-target `stale-source` warning remain open
  environment defects, not green checks. Baseline-delta lint remains unavailable until the plan
  has a `HEAD` carrier; the full-tree lint is the accepted green gate for this untracked plan.
