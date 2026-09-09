# Finish external verification — 2026-09-09

RAG re-pass for the only external fact classes carrying design decisions in P4 and P6. Queries
were limited to current official OpenAI/Anthropic documentation and official source surfaces.

## Engines and queries

- Context7: `/openai/codex` ×2 for Stop hooks and instruction/skill/non-interactive contracts;
  `/websites/code_claude` ×1 for Stop hooks.
- Perplexity Web advanced (`sources=[web]`) ×3: Codex Stop, Codex instruction/skill loading and
  Claude Code Stop; each query required official sources, exact identifiers and unknown-on-miss.
- Direct official-page fallback ×3 resolved the only retrieval discrepancy: Claude Code documents
  both the eight-consecutive-block cap and the `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP` override.

## Verified facts and verdict

- OpenAI Codex Stop supplies turn/session/cwd context plus `stop_hook_active` and
  `last_assistant_message`; synchronous `decision: "block"` continues through a reason prompt,
  while async handlers cannot apply control effects. Confidence: high. Source:
  <https://developers.openai.com/codex/hooks>.
- Claude Code Stop supplies `stop_hook_active` and `last_assistant_message`; `decision: "block"`
  with a reason continues work, user interrupts do not fire Stop, API errors use StopFailure, and
  eight consecutive no-progress blocks are overridden unless the documented environment cap is
  raised. Confidence: high. Sources: <https://code.claude.com/docs/en/hooks> and
  <https://code.claude.com/docs/en/hooks-guide>.
- Codex loads AGENTS guidance root-to-cwd under the documented aggregate project byte limit; skills
  expose metadata first and bodies on selection, catalog pressure may shorten/omit descriptions,
  and explicit invocation remains available when implicit invocation is disabled. Confidence:
  high. Sources: <https://developers.openai.com/codex/agent-configuration/agents-md> and
  <https://developers.openai.com/codex/build-skills>.
- `codex exec --json` is the JSONL automation surface and `--ephemeral` suppresses persisted rollout
  state; neither proves which local sources were effectively loaded. Confidence: high. Source:
  <https://developers.openai.com/codex/non-interactive-mode>.

The evidence confirms D3, D5, D9 and D11 without changing their decisions. Provider documentation
does not prove local hook activation or actual source loading; P4.2 and P6.1 retain those as
execution-time measurements.

## Проверка

- RAG: Context7 ×3 OK · Perplexity Web advanced ×3 OK · direct official pages ×3 OK.
- Непроверено → ПОВТОРНЫЙ ПРОХОД: nothing required for design closure; local provider activation/source loading intentionally remains P4.2/P6.1 product evidence.
- Обходки/[POSSIBLE-DEFECT]: none.

## 2026-09-09 — ATTENTION remediation re-pass

- Context7 `/openai/codex` ×2 was degraded: it returned partial skill-policy material for the
  AGENTS/skills query and no match for the non-interactive query. This pass is not reported green.
- Perplexity Web advanced ×1, restricted to official OpenAI sources, re-confirmed the three P6 fact
  classes and returned the direct pages now catalogued in `docs/reference.md`: AGENTS discovery,
  Agent Skills, non-interactive JSONL and developer commands. Confidence: high for documented
  contracts.
- Official docs still do not prove the exact effective local instruction/skill/plugin source set or
  universal presence of every sample usage field. Those remain P6.1 measurements; no deletion or
  provider-delivery mutation is admitted from documentation alone.
- Непроверено → ПОВТОРНЫЙ ПРОХОД: local effective source loading, by design owned by P6.1.
- Обходки/[POSSIBLE-DEFECT]: Context7 miss is disclosed; Perplexity official-source retrieval is the
  canonical fallback, not a substitute claim of local behavior.
