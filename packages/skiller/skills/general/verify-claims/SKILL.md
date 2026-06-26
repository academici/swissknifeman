---
name: verify-claims
bucket: general
version: 0.1.0
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
- **Big planning/design:** stack choice, architecture, choosing a library/service/integration — verify current
  versions/API/SLA/pricing/"is it maintained" BEFORE committing.
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
2. **Fact not in library docs** (best practice, "still recommended/maintained", market, comparison, recent
   change, security advisory, "which package/command now") → **Perplexity**:
   - `PERPLEXITY_API_KEY` present → **native Perplexity MCP** (more precise/faster; tools `perplexity_ask`/`perplexity_research`);
   - no key → **`perplexity-web`** (keyless bridge: `mcp__perplexity-web__search` / `search_advanced` / `search_deep`).
3. **Simple/quick lookup** (one known page/URL, trivial check) → **WebFetch/WebSearch** (Claude-native).
4. **Deep/high-stakes** (needs synthesis + cross-checking sources) → escalate to skill `research/research`
   (deep-research, source-tiers, faithfulness-check).

Economy: don't fire heavy search where context7 or a single `WebFetch` of a known URL suffices.

## Citation and confidence

- State **source + date** of the fact in output.
- Tag **confidence**: `high` (primary/official docs, cross-checked ≥2 sources) · `medium` (one primary source) ·
  `low` (secondary/forums only). A single low-tier source → provisional.
- An external decision at `low` confidence — **do not finalize without an explicit flag** "needs confirmation".
- Sources conflict → don't pick silently: surface the discrepancy and ask/escalate.

## Audit review — special clause

Reviewing someone's audit/plan, for EACH item decide: is the verdict repo-grounded or external?
- repo-grounded ("already in file Y", "the module does this") → confirm by reading code, no RAG.
- external ("library/server/market already does this", "this is outdated") → **verify via the ladder BEFORE
  finalizing**, even if confident and even if the audit is "complete". Better to double-check than reject on stale knowledge.

## Quality checklist

- [ ] Every decision-bearing claim classified (repo-grounded / stable / external-staleness).
- [ ] External facts checked via the ladder (context7 → perplexity native/web → websearch → research), not from memory.
- [ ] Cheapest sufficient engine chosen (context7 for docs; didn't fire deep-research for nothing).
- [ ] Source + date + confidence stated; `low` facts flagged "needs confirmation".
- [ ] In audit review, external-world verdicts double-checked; repo-grounded confirmed by code.

## Related skills

- `mcp-advisor` (general) — complementary: that one is about **what to connect** to a project
  (context7/perplexity/web as servers), this one about **when and how to fetch a fact**. Before verifying, make
  sure the needed engine is connected.
- `research/research` — deep RAG: source-tiers, faithfulness-check, multi-step deep-research; ladder step 4 escalates here.
- `general/grill-with-docs` — a heavy special case: grilling REQUIREMENTS against code + external specs (API/RFC/bank) with glossary+ADR.
- `general/anti-drift` — iteration discipline; this skill is knowledge discipline (don't assert stale facts).
- `general/context-economy` — each RAG engine costs context/permissions; don't keep unused ones connected.

<!-- ru-source-sha256: PENDING -->

<!-- ru-source-sha256: 6209747735d8d71d56ca4316547010ad1b06839d55ccc3fc0ee6794afdb24fba -->
