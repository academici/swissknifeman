---
name: query-craft
bucket: research
version: 0.1.0
description: "How to FORMULATE a search/doc-engine query (Perplexity Web · WebSearch · context7): maximize detail (exact version/stack/'min Filament 4', timeframe, format, result limit), pick engine+mode (search/advanced/deep), set sources (web/academic/social). Activate BEFORE any external search, esp. a library/framework (Laravel/Filament/Vue): ban bare 'Laravel how to X?'. Not when-to-verify (verify-claims) nor what-to-connect (mcp-advisor) — only HOW to ask."
risk: read
persona: oss-dev
tags: [research, perplexity, search, query, rag, context7, claude-code]
requires: []
produces_for: [verify-claims]
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Query-craft — how to formulate a search-engine query

This is HOW to ask, not "when" and not "what to connect".
- **When** to search/verify a fact → `general/verify-claims` (claim classification, engine ladder, citation).
- **What** to connect to a project (context7/perplexity/web as servers) → `general/mcp-advisor`.
- **This** skill: the query is already decided — **phrase it to get a precise answer on the first try**, not generic fluff.

Closes: vague queries — "Laravel how to do X?", "Filament, we need min version 4". The engine knows neither
version nor stack nor context → answers by the median (often a stale major). Cost of vagueness = a wrong
answer later relied on.

## Iron rule: NEVER send a bare library query without version and context

Before a query about a framework/library/tool (Laravel, Filament, Vue, Nuxt, Livewire, Tailwind, …) the
query MUST carry: exact name + **version** (or "min X" range), **stack/environment**, **concrete task**,
**timeframe** when freshness matters.

| ❌ Anti-pattern (do NOT ask this) | ✅ Detailed query |
|:--|:--|
| `Laravel how to do queues?` | `Laravel 11: configuring Redis queues with horizontal scaling via Horizon — current config syntax as of 2025` |
| `Filament — minimum version 4` | `Filament v4 (min 4.x, not 3.x): declaring a custom form field — API changes vs v3` |
| `Vue composition api best practices` | `Vue 3.5 <script setup>: patterns for organizing composables in a large SPA, current recommendations` |
| `how to test` | `Laravel 11 + Pest 3: DB test isolation via RefreshDatabase vs transactions — current recommendation` |

> Version unknown → take the **latest stable** and **say so explicitly** ("current stable as of 2025",
> "latest major"), or first read the version from the project's `composer.json`/`package.json` (repo-grounded —
> read, not guessed). "Latest fresh" is the default when version isn't extractable from the project.

## Anatomy of a good query (5 slots)

Build from slots — a missing slot = lost precision. (Rules sourced from Perplexity's official prompt guide,
see provenance; same principles apply to WebSearch.)

1. **Verb instruction** — what to do: `compare` / `explain` / `list` / `show the syntax` / `find API changes`. The verb sets the answer shape.
2. **Subject + version** — exact name and **version/range**: `Filament v4`, `Laravel 11`, `Vue 3.5`, `min Filament 4 (not 3.x)`.
3. **Context/environment** — stack, goal, audience, constraints: `in a Laravel+Inertia+Vue project`, `for production`, `for a large SPA`, `compatible with PHP 8.3`.
4. **Specifics** — keywords, method/package/standard names, dates: `via Horizon`, `RefreshDatabase`, `Spatie Permission`, `as of 2025`.
5. **Format and limit** — how to present and how many: `as a table`, `top-5 list`, `with code examples`, `official docs only`. **A list with no limit → always give a number** (`top-5`).

Minimal template:
```
<verb> <subject vX.Y> for <context/stack>, <specifics/keywords>, <timeframe>.
Answer: <format>, <limit>.
```

## Engine selection (what goes where)

Engine first — phrasing adapts to it. (The "when" ladder is in `verify-claims`; here — how to phrase for the
already-chosen engine.)

| Fact about… | Engine | How to phrase |
|:--|:--|:--|
| API/method/option of a specific library | **context7** (`resolve-library-id` → `query-docs`) | resolve the library id **with version** first; query narrow — symbol/option name, not a general question |
| best practice / "still current" / comparison / recent change / market | **Perplexity** (`search` / `search_advanced` / `search_deep`) | full 5-slot query (above); version+context MANDATORY |
| one known page/URL, trivial check | **WebSearch / WebFetch** | exact keywords; for WebFetch — a concrete question against the page |

> **context7 — version lives in the id.** context7's bottleneck isn't prose phrasing but the **correct
> id+version** at `resolve-library-id`. Resolve → confirm the right major was picked → then ask a specific
> `query-docs` (method/option name), not a general question.

## Perplexity Web MCP modes (three tools)

Tools of the `perplexity-web` server (keyless bridge). Mode choice = depth/speed balance:

| Tool | When | Cost | How to phrase |
|:--|:--|:--|:--|
| `mcp__perplexity-web__search` | default: one verifiable fact, fast cited answer | fast | one focused 5-slot query |
| `mcp__perplexity-web__search_advanced` (`sources: web\|academic\|social`) | when **source control** matters: `academic` for papers/research, `social` (Reddit/forums) for lived experience/edge-cases, or a combo | as search | same query + **explicit `sources`** by fact type |
| `mcp__perplexity-web__search_deep` | deep: market, competitive landscape, topic overview across 20+ sources | **slow, up to ~5 min** | broad query with explicit goals and desired answer structure; NOT for one fact |

**Choosing `sources` in `search_advanced`:**
- `web` — general default (docs, blogs, news).
- `academic` — scholarly articles, papers, citations, formal methods.
- `social` — Reddit and forums: lived experience, gotchas, "who else hit this".
- combine (`web+academic`) when you need both official docs and formal confirmation.

> **Don't fire `search_deep` needlessly.** Up to ~5 min/query. For one fact/version/comparison `search` or
> `search_advanced` suffices. `deep` — only for synthesis across many sources (see "cost" in
> `verify-claims`/`context-economy`).

## Reliability of the keyless bridge `perplexity-web` (lock / timeout on heavy queries)

`perplexity-web` is a **keyless bridge through a browser profile** (one shared profile). Hence two observed
failures, especially on complex/long queries:

- **`Profile is locked by another … instance`** — profile held by another/hung session. You cannot send two
  `perplexity-web` queries in parallel.
- **Browser closes on "thinking" → timeout**, though the answer was actually being generated. A heavy query
  (especially `search_deep`, up to ~5 min) outgrows the bridge timeout — result is lost.

**What to do (in order):**
1. **No parallel** to `perplexity-web` — one query at a time; don't batch it with another `perplexity-web`
   call. (Other engines — context7/WebSearch — can be parallelized.)
2. **Heavy query → split or switch engine.** Instead of one `search_deep` — several narrow `search` (see "one
   query = one fact"); or for deep synthesis escalate to `research/research` over WebSearch/WebFetch.
3. **Lock won't clear / repeated timeout → switch engine:** `WebSearch`+`WebFetch` (Claude-native, no browser
   profile) for the same fact; for library docs — `context7`. Don't get stuck on the locked bridge.
4. **Systemically (for heavy/frequent queries): move to the API-key variant** — native
   `@perplexity-ai/mcp-server` with `PERPLEXITY_API_KEY` (more precise/faster, no browser profile or its
   timeouts; catalog — `harness configs/claude-code/mcp/perplexity.json`). The keyless bridge is for light
   keyless queries; "complex queries timing out" is the signal it's time for the key.

> This is an **operational workaround**, not a server fix (the bridge is external, not in this repo). A
> recurring bridge failure → route via `field-feedback-loop` (candidate: default to the API-key variant in the
> harness catalog for research-heavy projects).

## Phrasing anti-patterns (fix before sending)

- **Bare subject, no version** — `Filament how to...` → add `v4`/range.
- **Multiple questions in one query** — engine answers fragmentarily; **split** into separate queries (one query — one fact/topic).
- **List with no limit** — `give me a list of packages` → `top-5 packages ...`.
- **Vague verb** — `tell me about X` → `compare X and Y by ...` / `show the syntax of ...`.
- **No timeframe on a fresh fact** — for versions/releases/"still current" add `as of 2025` / `current` / `latest major`.
- **Describing the tool inside the query** — don't tell the engine "search the web"; it does so itself.
- **Explaining "why I need it" instead of the subject** — context (slot 3) is stack/goal, not the task's backstory.

## Iteration (if the answer misses)

Phrasing is iterative. A miss → a **clarifying follow-up**, not a rewrite from scratch: `Only European
policies`, `Focus on v4, ignore v3`, `Give it as a table`, `Use primary sources only; if weak, list
limitations`.

Anti-hallucination (high-stakes): add a grounding rule to the query — `Cite every claim; if no data, say "I
don't know", don't guess`.

## Quality checklist (before sending the query)

- [ ] Subject carries a **version/range** (or explicit "current stable"); for a library — cross-checked with `composer.json`/`package.json` if available.
- [ ] Has **context/stack** and **specifics** (keywords/names), not a general question.
- [ ] One query = one fact/topic (multiple questions not glued together).
- [ ] List — **with a limit** (top-N); answer **format** specified.
- [ ] **Engine** chosen by fact type (context7 for API · Perplexity for practices/freshness · Web for a known URL) and **mode** (`search`/`advanced`/`deep`) by depth; `deep` not fired for one fact.
- [ ] In `search_advanced` `sources` chosen by fact type (academic/social/web).
- [ ] Fresh fact has a **timeframe**.
- [ ] On `perplexity-web` lock/timeout — not parallelized; heavy query split or switched to WebSearch/context7; persistent heavy use → API-key variant.

## Related skills

- `general/verify-claims` — **when** to search/verify (claim classification, engine ladder, citation+confidence). This skill kicks in AFTER its "must verify" decision — and answers "how to phrase". `produces_for: verify-claims`.
- `general/mcp-advisor` — **what** to connect to a project (perplexity/context7/web as servers). Here — how to use what's already connected.
- `research/research` — deep research playbook (source-tiers, synthesis, knowledge graph); escalate here when the query grows into multi-step research.
- `general/context-economy` — each engine costs context/permissions; don't keep unused ones. `deep` is time-expensive — don't fire it needlessly.

<!-- provenance: phrasing rules cross-checked with Perplexity's official prompt guide
     (docs.perplexity.ai/guides/prompt-guide) + help-center "getting better answers",
     verified 2026-06-29 (WebSearch+WebFetch; perplexity-web profile was locked).
     search/advanced/deep modes — from the perplexity-web server tool schemas. -->

<!-- ru-source-sha256: b953867ae9ba3040c3623fca30d6dda227a1e4d8ee3f29cb732be2b7df4535f1 -->
