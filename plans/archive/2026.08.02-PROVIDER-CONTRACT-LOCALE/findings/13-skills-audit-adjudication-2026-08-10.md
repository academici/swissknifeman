# Skills-audit adjudication — 2026-08-10

## Scope and method

This finding adjudicates every claim class in `audits/2026.08.10-skills-audit.md` against the
current repository and current primary provider sources. It is design evidence only: no skill,
package, provider projection, consumer project or generated artifact was changed.

External retrieval followed the repository ladder. Perplexity Web was invoked first. Its daemon
initially failed because the already-running MCP process referenced an obsolete Mutter XAuthority
cookie (`Daemon connection closed before result`; Chromium reported invalid
`MIT-MAGIC-COOKIE-1`). The transient XAuthority carrier was repaired, `perplexity-web.login`
returned `Login successful`, and all earlier ordinary-web queries were repeated from scratch as
14 source-controlled Perplexity Web queries. One Perplexity synthesis initially missed the newly
published Anthropic article; a second query pinned the exact official URL and confirmed it. This
is why Perplexity output is treated as retrieval/synthesis, while the cited primary page remains
the evidence.

Repository observations were repeated from the worktree-local CLI:

```text
packages/skiller/bin/skiller bucket-audit --since 90 --json
packages/skiller/bin/skiller budget --profiles --json
```

Observed snapshot: 231 skills, 49 buckets, 44 projects with transcript data, 206 resident skills,
21 `dead`, 203 `keep`, 5 `merge`, 2 `thin`, and only 3 reported overlap pairs. The `frontend-vue`
bucket contains 11 skills, but none of the three alleged Vue/Pinia/Vitest overlap groups was
reported; `vueuse-functions` alone is `thin` at 10,838 estimated tier-1 tokens. There are 18—not
10—singleton buckets. Codex listing fallback is exceeded by 9 of 10 shipped profiles; Claude's
10,000-token listing budget is exceeded only by `standalone`. The profiles command also repeats
the real dependency diagnostic `session-observer requires shared-memory, but it is excluded`.

## Primary-source verification

| Claim class | Verdict | Evidence and consequence |
|:--|:--|:--|
| Claude Code removed >80% of its system prompt for advanced Claude 5 models with no measurable coding-eval loss | **Confirmed, scoped** | The exact [Anthropic context-engineering article](https://claude.com/blog/the-new-rules-of-context-engineering-for-claude-5-generation-models) says this for models such as Opus 5/Fable 5 and Anthropic's own coding evaluations. It recommends judgment over blanket rules, interfaces over constraining examples, progressive disclosure, removing repetition, lightweight skills and repository-specific gotchas. It is not a universal promise that deleting 80% from SKM preserves quality. |
| Anthropic skill shape | **Confirmed with corrected units** | [Anthropic skill best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices) recommend real workflows, at least three evaluations, a no-skill baseline, testing intended model tiers, concrete triggers and SKILL.md under 500 lines; the [skills overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview) describes progressive disclosure and an instruction body under about 5,000 tokens. The audit's “~5,000 words” comparison is wrong. |
| Codex skill shape and discovery | **Confirmed** | [OpenAI Build skills](https://developers.openai.com/codex/build-skills) defines metadata-first progressive disclosure, focused jobs, operational trigger descriptions, real positive/near-miss prompts and optional `agents/openai.yaml`; `policy.allow_implicit_invocation: false` is a Codex adapter control, not shared frontmatter. The initial listing budget is provider-specific (2% of model context or 8,000 characters when unknown), and descriptions may be shortened or entries omitted. |
| Small provider-neutral interchange | **Confirmed** | The [Agent Skills specification](https://agentskills.io/specification) defines the portable directory with `SKILL.md` plus optional `scripts/`, `references/` and `assets/`. Provider paths, prompt placement, invocation policy, upload/distribution and measurement are adapters beyond this core. |
| Token-count oracle is model/payload specific and still an estimate | **Confirmed** | Anthropic's [token-counting guide](https://platform.claude.com/docs/en/build-with-claude/token-counting) and [API reference](https://platform.claude.com/docs/en/api/messages/count_tokens) define `POST /v1/messages/count_tokens`, accept structured message/tool/image/document inputs and explicitly call the returned count an estimate. Counts must be repeated for the target model; character heuristics are not hard evidence near a threshold. |
| Universal `Gotchas` section is required in every skill | **Rejected** | Neither Anthropic nor OpenAI defines this as a universal skill requirement. Anthropic recommends spending always-loaded CLAUDE.md budget on non-obvious repository gotchas and keeping skills lightweight; OpenAI mentions gotchas in some operational guidance, not as a mandatory schema. Use observed failure modes when they add signal; never add filler to every skill. |

## Part I — supervisor reference claims

Part I belongs to `2026.08.03-ARTIFEX-SUPERVISOR`. It is retained here as a verified cross-plan
boundary, not duplicated as skill-package implementation.

| Audit statement | Verdict | Disposition |
|:--|:--|:--|
| Claude Squad/Claude Code worktrees isolate concurrent edits; `.worktreeinclude` carries selected ignored files | **Confirmed** | Official [Claude Code worktree documentation](https://code.claude.com/docs/en/worktrees) confirms native worktrees, subagent isolation and `.worktreeinclude`; the canonical [Claude Squad repository](https://github.com/smtg-ai/claude-squad) confirms separate workspaces. Supervisor plan may consume the mechanism. Treat copied secrets as an explicit security choice, not a default. |
| “Open Orchestrator” supplies the same exact mechanism and partial restart durability | **Unverified/ambiguous** | Perplexity could not uniquely identify a canonical project from the name. No requirement may depend on it until the supervisor plan pins a repository/version. |
| langgraph-supervisor requires handoff as one strict universal result schema | **Partially confirmed, conclusion rejected** | The canonical [langgraph-supervisor repository](https://github.com/langchain-ai/langgraph-supervisor-py) and [reference](https://reference.langchain.com/python/langgraph-supervisor) confirm tool-based handoff and direct worker-message forwarding, but explicitly allow custom handoff tools/arguments/state. The useful lesson is typed observable handoff at the SKM boundary, not copying one universal schema. |
| CrewAI hierarchical manager always delegates; its known failure is manager self-execution | **Not established as a guarantee** | Official behavior makes delegation configurable/model-dependent; the anecdotal failure is plausible but not a frozen fact. Keep it as a replay case in the supervisor plan, not architecture proof. |
| AutoGen GroupChat is selector/round-robin coordination with growing history and no built-in process durability | **Partially confirmed** | Official AutoGen material confirms configurable speaker selection over group messages and optional Docker for code execution; it does not itself provide durable crash replay. “Unpredictable on long dialogue” needs a pinned reproduction. |
| Temporal Workflow/Activity/Worker provides durable replay | **Confirmed, optional** | Official [Temporal workflows](https://docs.temporal.io/workflows), [workers](https://docs.temporal.io/workers) and [human-in-the-loop cookbook](https://docs.temporal.io/ai-cookbook/human-in-the-loop-python) confirm deterministic workflows, side-effect Activities, workers, retry/timeouts and durable waits. It is appropriate for durable distributed execution, not mandatory for a local supervisor. |
| MetaGPT is a role/SOP pipeline | **Confirmed; rigidity claim unsupported** | The canonical repository describes `Code = SOP(Team)` and specialized roles. Lack of built-in OS isolation/durable replay is observable; “poorly adapts” needs a task replay. |
| AutoGPT is universally the old unbounded planner/executor loop | **Stale/version-specific** | Current canonical AutoGPT is a broader workflow platform and distinguishes AutoGPT Classic. Any loop claim must pin Classic version/code. |
| Agency Swarm uses explicit communication flows | **Confirmed; production-failure claim unsupported** | Official docs describe directed flows and per-flow conversation context, not OS isolation or durable replay. “Limited production failure docs” is not an implementation contract. |

## Part II — six skill-corpus bottlenecks

| # | Audit claim | Current verdict | Plan consequence |
|:--|:--|:--|:--|
| II.1 | `frontend-vue` should automatically shrink 11→8 | **Count confirmed; merge prescription unproven** | Current detector reports no alleged pair. `vue`/`pinia` are upstream references while `*-best-practices` often carry project policy. P4.3 must run trigger/outcome replays and ablation per cluster, then merge, reclassify or retain. |
| II.2 | Every `*-super-skill` navigator is an anti-pattern | **Partially confirmed** | Broad navigators that admit “prefer granular” are candidates for removal; several business-domain entries are the only installed skill and may be valid thin entry points to on-demand references. Decide per job and real trigger behavior. |
| II.3 | descriptions are summaries rather than triggers | **Partially confirmed** | `codebase-design` front-loads a glossary and puts `Activate when` late. Current validation already requires a trigger phrase for new/local skills, so the remaining defect is discriminative ordering and boundary quality. `laravel-security-audit` and `security-design` are distinct audit/design jobs but need sharper negative boundaries. |
| II.4 | missing universal gotchas discipline | **Underlying observation confirmed; universal remedy rejected** | Templates do not ask for failure modes. Add an optional evidence-backed `Failure modes` block and require it only when a real failure justifies it. |
| II.5 | 6,000-token thin threshold is too soft | **Confirmed with corrected comparison** | `TIER1_MONOLITH_TOKENS = 6000`; Anthropic recommends under ~5,000 tokens and under 500 lines. Make thresholds advisory/provider-versioned, and never decide a rewrite near the boundary from the heuristic alone. |
| II.6 | write-risk invocation marking is not systematic | **Confirmed** | `risk` is enum-validated, but no cross-field rule maps it to provider invocation controls. Freeze provider-neutral invocation intent and render Claude/Codex-native controls separately. |

## Part III — fourteen tooling findings

| # | Verdict | Repository evidence and corrected action |
|:--|:--|:--|
| III.1 pairwise overlap | **Confirmed** | `find_overlaps()` is O(n²) and returns edges only. Preserve edges but derive connected components and keep every signal/explanation. |
| III.2 verdict precedence | **Confirmed** | `verdict()` returns `merge` before `thin`, then usage. Replace the single mutually exclusive diagnostic with multi-label signals; derive an action separately. |
| III.3 description Jaccard | **Confirmed** | `_words()` has no stopwords/lemmatization/language semantics. Current three overlaps are mostly generic navigator/bootstrap wording, while Vue is missed. Do not add an embedding runtime dependency; combine deterministic signals with real trigger replays and reviewer evidence. |
| III.4 token calibration | **Confirmed** | `CHARS_PER_TOKEN_*` cites secondary calculators while calling Anthropic count-tokens the oracle. Use provider counters/replays when available and label heuristic values with class/range/confidence. |
| III.5 mixed first-turn certainty | **Confirmed** | hooks are executed; MCP `auto` is an upper bound and `deferred` a lower bound, yet one scalar verdict is produced. Emit per-source typed evidence plus lower/upper/unknown totals. |
| III.6 resident masks dead | **Confirmed** | resident with zero direct calls is protected indefinitely. Add longitudinal `resident-only-unobserved` review evidence, but do not call it dead without real trigger traces. |
| III.7 no cross-provider listing gate | **Partially stale** | `validate.sh` already runs `budget --profiles --json`, but only warns on Codex overages and does not enforce both providers. Define provider-qualified outcomes and explicit accepted degradation; do not collapse units into one score. |
| III.8 excluded fields are observed only for Claude | **Confirmed** | `LISTING_EXCLUDED_BY_FIELDS` is version-bound live observation; Codex remains deliberately overestimated. Add capability probes with observation version/expiry and no cross-provider inference. |
| III.9 two templates | **Confirmed drift; “accidental double directory” unproven** | Two real files differ by `level`. The nested copy belongs to the distributed generator skill, but independent editing is unsafe. Generate/project it from one canonical template. |
| III.10 template lacks gotchas/provider invocation link | **Confirmed with remedy correction** | The template lacks failure-mode guidance and risk→invocation mapping. Provider fields do not belong in shared frontmatter; add shared invocation intent plus adapter generation, and optional observed failure modes. |
| III.11 one chars/token model for all content | **Confirmed** | The heuristic does not distinguish code, prose or structured metadata. Prefer authoritative counters/replay; content-class heuristics are fallback estimates only. |
| III.12 `resolve_active_set` uses `SystemExit` | **Confirmed** | Shared resolver calls `die()` for unknown buckets; batch callers catch process-level exceptions. Introduce a typed domain error at the library boundary and map it to CLI exit only at the entry point. |
| III.13 singleton bucket count/topology | **Counts stale; structural question valid** | Current state is 49 buckets/18 singletons, not 46/10. A bucket is also a distribution/provenance unit, so singleton is not automatically waste. Measure listing/distribution and ownership before consolidation; add a declared class for project/package-scoped exceptions. |
| III.14 repository-bootstrap drift | **Mechanism claim rejected; class-awareness defect confirmed** | `iter_registry_skills()` scans canonical `skills/**/SKILL.md`, not generated `.agents/.claude` projections, so it does not compare source to its projection. It still misclassifies private source-only canons with ordinary usage rules: current output marks `decision-verification` as merge with `general/verify-claims` and several bootstrap canons dead. Audit by publication/visibility class and keep generated projection drift under the owning registry check. |

## New observed defects not explicit in the audit

- `budget --profiles --json` emits the same excluded dependency warning many times. Batch output
  needs deduplication and a machine-readable dependency-status row.
- Nine of ten shipped profiles exceed Codex's fallback listing budget. This is a measured product
  issue, not an argument to delete arbitrary skills; profile selection, discovery metadata and
  accepted degradation must be redesigned and replayed on Codex.
- Current live overlap output contradicts the audit's confident Vue merge prescription. Audit tools
  need an `insufficient-evidence` outcome instead of converting weak lexical evidence into a
  content action.

## Verification footer

- **External verified:** 14 successful Perplexity Web source-controlled queries after MCP repair;
  official Anthropic, OpenAI, Agent Skills, Claude Code, Temporal, LangChain and canonical project
  sources cited above. Retrieval date: 2026-08-10.
- **Repository verified:** current `audit.py`, `budget.py`, `skillset.py`, `validate.sh`, both
  templates, selected skill bodies, `skills.json`, 90-day bucket audit and both-provider profile
  listing report.
- **Unverified:** uniquely identifying “Open Orchestrator”; anecdotal quality/failure claims for
  CrewAI, AutoGen, MetaGPT, AutoGPT and Agency Swarm without a pinned real replay.
- **Environment defect:** Perplexity MCP inherited stale XAuthority. The transient cookie carrier
  was repaired for this session; the owning MCP launcher still needs a durable fresh-session
  XAuthority fix outside this plan's product scope.
