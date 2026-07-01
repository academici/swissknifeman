---
name: verify-claims
bucket: general
version: 0.2.0
description: "Before a decision/verdict that rests on an EXTERNAL fact (library version/API, 'still current', best practice, market, another service's/MCP's capabilities) — verify via RAG, don't assert from memory (knowledge cutoff goes stale). Ladder: context7 (docs) → Perplexity (native MCP if API key, else perplexity-web) → WebSearch → research for deep. Activate on audit/plan review, big planning, library/stack/dependency choice, claiming 'this is standard/modern'. Repo-grounded facts (read the code) and stable knowledge — no check."
risk: read
persona: oss-dev
tags: [verification, rag, research, planning, context, claude-code]
requires: []
produces_for: [architecture, tech-stack-selection]
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Verify Claims — don't decide on stale knowledge, verify the external fact

Model knowledge has a cutoff and may be incomplete/wrong on a specific topic. So **classify a claim before
building a decision/verdict on it** — and verify external, staleness-sensitive facts via RAG, not from memory.

## Claim classification (the core)

| Type | Source of truth | Verify? |
|---|---|---|
| **Repo/code-grounded** — present in THIS repo's code/config | read the code (authoritative for the repo) | NO |
| **Stable general knowledge** — language syntax, established algorithms, math | — | NO |
| **External + staleness-sensitive** — library versions/API, "still current/maintained", best practice, market, another service's/server's/MCP's capabilities, pricing, security | **RAG (ladder below) + cite + confidence** | **YES** |

## When verification is REQUIRED (concrete situations)

- **Audit/plan review:** any verdict/**rejection** resting on an external fact ("library Y already does this",
  "this is deprecated", "the modern way is Z", "server X already returns this") — **even if the audit looked
  complete**. Repo-grounded verdicts (read the code — implemented or not) are exempt.
- **Big planning/design (forming a plan):** stack choice, architecture, choosing a library/service/integration —
  verify current versions/API/SLA/pricing/"is it maintained" BEFORE committing. **A plan stands 100% on fresh
  data**; close it with a "Verification" footer (below): what's checked, what stayed unverified → re-pass.
- **Claiming "current best practice" / "this is the standard" / "nobody does this anymore"** — verify it's still current.
- **Recommending/adopting a dependency, tool, MCP server** — verify it exists, is maintained, does what's claimed,
  and which package name/command is current.
- **Any post-cutoff / time-sensitive** (releases, pricing, deprecations after the knowledge cutoff).

Breadth rule: anything that is **not** pure implementation of an already-planned-and-verified spec — back it with
data. Cheaper to re-check than to ship a wrong verdict.

## When NOT required (narrow exceptions)

- Repo/code-grounded — verified by reading the code/config.
- Stable general knowledge (syntax, established patterns, math).
- Pure implementation of an already-planned-and-verified spec ("it's planned for you — implement").

## Engine ladder (cheapest/most reliable first)

1. **Library/framework/API fact** (does a method exist, current signature, config option, version behavior)?
   → **context7 first** — live versioned docs, cheapest and most authoritative for libraries:
   `resolve-library-id` → `query-docs`. If the project has connected docs, those first.
   **Library/API absent from context7** (not indexed / empty answer) → fall back to **`perplexity-web`** (step 2), NOT WebSearch.
2. **Fact not in library docs** (best practice, "still recommended/maintained", market, comparison, recent
   change, security advisory, "which package/command now") → **Perplexity — the aggressive default**:
   - `PERPLEXITY_API_KEY` present → **native Perplexity MCP** (more precise/faster; tools `perplexity_ask`/`perplexity_research`);
   - no key → **`perplexity-web`** (keyless bridge: `mcp__perplexity-web__search` / `search_advanced` / `search_deep`).
   **Why aggressive:** `perplexity-web` is keyless, runs through a browser profile on a **flat-rate subscription**
   (spends no API tokens) and returns a **compact synthesis** instead of raw pages. Offload retrieval+synthesis onto
   it **to the max** — cheaper in context tokens than pulling results through WebSearch/WebFetch (raw into context).
3. **One known page/URL, trivial check** → **WebFetch/WebSearch** (Claude-native) — **last-resort fallback**: they
   pull raw content into context (token-heavier). Use only for a concrete known-URL or when Perplexity is down.
4. **Deep/high-stakes** (needs synthesis + cross-checking sources) → escalate to skill `research/research`
   (deep-research, source-tiers, faithfulness-check).

Economy: context7 for exact library API; everything else aggressively via `perplexity-web` (flat-rate, compact
synthesis); WebSearch/WebFetch = narrow known-URL/fallback; don't fire deep-research for nothing.

## Delegation: don't drop a rung

The ladder is an obligation on the RESULT, not just engine order. Run the RAG rung where the priority engine is
AVAILABLE (usually the main context). **Before delegating "verify X" to a subagent — confirm its toolset has
`perplexity-web` (and `context7`).** A topically-matching agent (e.g. a Claude-Code one) is often WebSearch-only
→ delegating there SILENTLY downgrades the ladder to WebSearch. If the delegate lacks the priority engine:
(a) keep the check in the main context; (b) grant the subagent the `perplexity-web` tool; (c) have the subagent
return WHAT to verify and run the ladder yourself. Delegating verification is fine (e.g. `research/research` fans
out deliberately) — only silent rung-dropping is not. If the rung ran degraded anyway — that's an engine failure:
put it in the "Непроверено → ПОВТОРНЫЙ ПРОХОД" footer.

## Citation and confidence

- State **source + date** of the fact in output.
- Tag **confidence**: `high` (primary/official docs, cross-checked ≥2 sources) · `medium` (one primary source) ·
  `low` (secondary/forums only). A single low-tier source → provisional.
- An external decision at `low` confidence — **do not finalize without an explicit flag** "needs confirmation".
- Sources conflict → don't pick silently: surface the discrepancy and ask/escalate.

## "Verification" footer (bottom of a plan/design/verdict)

Any plan/design/verdict that touched external facts — close with a **"Verification"** block, so the owner sees
what the plan stands on and can order a **re-pass** if data didn't get through:

```
## Проверка (verification status)
- RAG: <engines + N queries + ok/degraded> (e.g. "perplexity-web ×3 OK, context7 ×1 OK")
- Непроверено → ПОВТОРНЫЙ ПРОХОД: <fact> — <engine was down: lock/timeout/MCP down>
- Обходки/[POSSIBLE-DEFECT]: <what was patched with a workaround, no real fix — honestly>
```

- An engine was down/degraded (`perplexity-web` locked/`TIMEOUT`, MCP down, `context7` empty) and a fact stayed
  unverified → **don't mask it, don't finalize silently**: put it under "Непроверено → ПОВТОРНЫЙ ПРОХОД".
- Write empty sections explicitly ("nothing unverified", "no workarounds") — silence ≠ "all verified".

## Honesty: no edits for the sake of edits; call a kludge a kludge

- Verification showed the edit **isn't needed** (fact already correct, "the library already does this") → **drop it
  from the plan**, don't ship it for activity's sake.
- No real solution, only a workaround remains → tag it `[POSSIBLE-DEFECT]` / "workaround, no real fix" and surface
  it in the "Verification" footer. **Don't dress a kludge as a solution.**

## Audit review — special clause

Reviewing someone's audit/plan, for EACH item decide: is the verdict repo-grounded or external?
- repo-grounded ("already in file Y", "the module does this") → confirm by reading code, no RAG.
- external ("library/server/market already does this", "this is outdated") → **verify via the ladder BEFORE
  finalizing**, even if confident and even if the audit is "complete". Better to double-check than reject on stale knowledge.

## Quality checklist

- [ ] Every decision-bearing claim classified (repo-grounded / stable / external-staleness).
- [ ] External facts checked via the ladder (context7 for API → **aggressively `perplexity-web`** → websearch fallback → research), not from memory.
- [ ] Synthesis/beyond-docs offloaded to `perplexity-web` (flat-rate, token-cheap), not pulled raw via WebSearch/WebFetch.
- [ ] Source + date + confidence stated; `low` facts flagged "needs confirmation".
- [ ] A plan/design/verdict with external facts carries the "Verification" footer (RAG + unverified→re-pass + workarounds).
- [ ] In audit review, external-world verdicts double-checked; repo-grounded confirmed by code.

## Related skills

- `mcp-advisor` (general) — complementary: that one is about **what to connect** to a project
  (context7/perplexity/web as servers), this one about **when** to fetch a fact. Before verifying, make
  sure the needed engine is connected.
- `research/query-craft` — about **how to phrase** the query (detail: version/stack/mode search·advanced·deep/sources;
  reliability of the keyless `perplexity-web` bridge). Kicks in AFTER the "must verify" decision: this trio
  (mcp-advisor=what · verify-claims=when · query-craft=how) is one RAG discipline.
- `research/research` — deep RAG: source-tiers, faithfulness-check, multi-step deep-research; ladder step 4 escalates here.
- `general/grill-with-docs` — a heavy special case: grilling REQUIREMENTS against code + external specs (API/RFC/bank) with glossary+ADR.
- `general/anti-drift` — iteration discipline; this skill is knowledge discipline (don't assert stale facts).
- `general/context-economy` — each RAG engine costs context/permissions; don't keep unused ones connected.

<!-- ru-source-sha256: f34c7be9d9653fdc23dd109dd7fa9fdae11094f4a3cac8823d387d88ea17596e -->
