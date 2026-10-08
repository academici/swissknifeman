# References: external frameworks and agent directories Claude Code

Map of external sources studied during design swissknifeman (subagent layer/templates -
research-audit June 2026; skill-registry and eval — review skill-frameworks June 2026). For everyone -
what is this, maturity, **pros/cons**, verdict and what exactly was included in swissknifeman. The goal is to further
it was possible to return to them directly.

> **Rule:** used an external resource during design (repo, framework, someone else's skill, article,
> specification) — **tag it here** (row in table + with significance card: what, maturity,
> verdict: taken). This is a single provenance directory; per-skill passports live in `upstream.json`.

> Verdicts: **adopt** — taken; **reference** — pattern/landmark (not a dependency); **skip** — not
> is suitable. Repo Convention - stdlib-only Python, without JS/pip-runtime: we take any code from outside as
> **pattern** and rewrite it, rather than dragging it with a dependency.

## Pivot table

| Source | What | Maturity | Verdict | Taken from swissknifeman |
|:--|:--|:--|:--|:--|
| [AWS Labs CLI Agent Orchestrator](https://github.com/awslabs/cli-agent-orchestrator) | Local native-CLI orchestration, profiles and Python workflows | Source-reviewed 2026-10-05: main `c31dc281`, tag v2.5.1; PyPI latest 2.5.0 | **reference; pilot candidate** | Research in `orch/audit-amazon-cao.md`; no dependency or migration adopted. Replay boundaries, effect receipts, provider capability differences and terminal visibility inform the comparison. |
| [Vercel AI SDK Harnesses](https://ai-sdk.dev/docs/ai-sdk-harnesses/overview) + [Pydantic AI Harness](https://pydantic.dev/docs/ai/harness/) | Native harness adapters versus a programmable agent runtime | First-party docs, npm metadata and selected Vercel source reviewed 2026-10-05; Vercel harness API explicitly experimental | **reference** | Corrected API-only classification; sandbox/auth/session boundaries are recorded in `orch/alternatives.md`, not adopted as runtime dependencies. |
| [OpenHarness](https://github.com/autonomous-ai/openharness), [Agent Orchestrator](https://github.com/OrchestratorInc/agent-orchestrator), [Vibe Kanban](https://github.com/BloopAI/vibe-kanban), [AI-DLC](https://github.com/awslabs/aidlc-workflows), [Prime Agent](https://github.com/PrimeIntellect-ai/prime-agent), [Hermes](https://github.com/NousResearch/hermes-agent), [Dify](https://github.com/langgenius/dify), [Harness.io CLI](https://www.harness.io/products/platform/cli), [OpenCodex](https://github.com/lidge-jun/opencodex) | Alternative engines, command centers, methodologies and API/delivery tools | Primary README/docs and metadata reviewed 2026-10-05; no runtime benchmark | **reference / shortlist classification** | Full comparison and links in `orch/alternatives.md`; canonical Task/Skiller and a replaceable execution boundary are proposed. Prior measured code-review-graph skip remains in force. |
| [OpenAI — Build skills](https://learn.chatgpt.com/docs/build-skills) + [Model guidance](https://developers.openai.com/api/docs/guides/latest-model) | Initial skills-list budget, metadata/body disclosure, duplicate-name discovery and the sensitivity of the model to conflicting instructions | Primary pages opened and reviewed 2026-09-14; CLI 0.154.0 locally | **reference (audit and local implementation)** | 232 canonical skills, three consumer roots, five today roadmap incidents. Runtime inventory/character proxy are separated from provider usage; double delivery elimination recommended, short Codex hub and approval authority/continuity/final. |
| [OpenAI model guidance](https://developers.openai.com/api/docs/guides/latest-model), [Build skills](https://learn.chatgpt.com/docs/build-skills), [AGENTS.md discovery](https://learn.chatgpt.com/docs/agent-configuration/agents-md); [Gloaguen et al. v2](https://arxiv.org/abs/2602.11988), [Lulla et al. v2](https://arxiv.org/abs/2601.20404), [SkillsBench v4](https://arxiv.org/abs/2602.12670) | Impact of conflicting instructions, progressive disclosure and matched usefulness rating skills/context files | First-party + primary research; Perplexity discovery and direct reading of primary pages 2026-09-10 | **reference** | Simplification audit: remove confirmed process conflicts; maintain non-standard restrictions and tools; do not consider the length of the files as evidence token savings and do not delete skills by zero direct calls. Implementation ordered as a separate session without a new plan; internal report is stored locally according to directory policy audits. |
| Official spec Claude Code | subagents/skills/hooks/plugins, «steering» | first-party, active | **adopt** | canon frontmatter subagent (`name/description+<example>/tools/model/color`), hook contracts, progressive disclosure |
| [OpenAI — Config basics](https://learn.chatgpt.com/docs/config-file/config-basic) + [Configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference) | project-scoped `.codex/config.toml` in trusted projects | first-party; forward read 2026-09-14; plugin overrides checked by local codex-cli 0.154.0 | **adopt (project activation)** | `project-tooling-runbook`: Connect bundles and native activation are checked separately; choice native plugins is limited consumer config, cache digests and offline prompt-input are confirmed by local CLI. |
| [OpenAI Codex manual](https://developers.openai.com/codex/codex-manual.md) + [Developer commands](https://developers.openai.com/codex/cli/slash-commands) + [Codex App Server](https://developers.openai.com/codex/app-server) + [Unrolling the Codex agent loop](https://openai.com/index/unrolling-the-codex-agent-loop/) + [OpenAI model catalog](https://developers.openai.com/api/docs/models) + [Anthropic Claude Code docs](https://docs.anthropic.com/en/docs/claude-code/) | current provider surfaces and model roles: instructions/config/trust, skills/plugins, hooks, MCP, approvals/sandbox; `/clear` creates a new chat in the same CLI-sessions, `/status` shows active model, App Server links state with thread id; long thread takes into account the full history and compacts context; GPT-5.6 Sol/Terra/Luna | first-party, re-checked 2026-09-14 | **adopt (contract facts)** | provider contracts for; Goal/Constraints/Done, context/subagent budget, skill discovery and multi-source hooks for; Codex `plan-run` uses thread-bound current-state evidence with exact native argv fallback; Task does not create fresh root without typed boundary; separate native-steps `codex plugin marketplace add` → `codex plugin add` for machine bootstrap `core`/`task` |
| [OpenAI — Build plugins](https://learn.chatgpt.com/docs/build-plugins) | local plugin workflow: check manifest, refresh/install and test the installed plugin in the new conversation | first-party; direct reading 2026-09-11 | **adopt (delivery boundary)** | machine cache and loaded session are measured separately; internal cache digests are confirmed by local CLI/code evidence, rather than attributed to external documentation |
| [OpenAI — AGENTS.md discovery](https://developers.openai.com/codex/agent-configuration/agents-md) + [Agent Skills](https://developers.openai.com/codex/skills) + [Non-interactive mode](https://developers.openai.com/codex/non-interactive-mode) + [Developer commands](https://developers.openai.com/codex/developer-commands) | Codex root→cwd instruction chain; metadata-first skill disclosure, listing budget and explicit invocation; `codex exec --json` JSONL/usage surface; exact boundaries of `--ephemeral` and `--ignore-user-config` | first-party; Context7 partial/miss + Perplexity official-source cross-check 2026-09-09; high confidence for documented contracts, local effective loading intentionally unknown | **adopt (measurement boundary)** | –P6.3`: filesystem/plugin/source inventory is measured separately from provider docs; invalid or unknown loading is never normalized into a context-saving verdict |
| [Anthropic — New rules of context engineering for Claude 5](https://claude.com/blog/the-new-rules-of-context-engineering-for-claude-5-generation-models) + [Anthropic skill best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices) + [Anthropic skills overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview) + [OpenAI — Build skills](https://developers.openai.com/codex/build-skills) + [Agent Skills specification](https://agentskills.io/specification) | current-model skill/context guidance: light shared core, metadata-first progressive disclosure, discriminative triggers, provider-native invocation controls, real workflows/no-skill baseline/ablation; portable `SKILL.md` interchange | first-party + open specification; 14 requests via `perplexity-web`, primary pages rechecked 2026-08-10 | **adopt (contracts and method)** | –D61: minimum Skill Core, additive Claude/Codex/third-provider adapters, official-doc → real-provider replay/ablation → supplementary regression tests; rejected universal Gotchas, heuristic-only merge and transfer provider controls in shared frontmatter |
| [Anthropic token counting](https://platform.claude.com/docs/en/build-with-claude/token-counting) + [Messages count-tokens API](https://platform.claude.com/docs/en/api/messages/count_tokens) | model/payload-specific token estimate, including structured messages/tools/images/documents | first-party; checked via `perplexity-web` 2026-08-10 | **adopt (measurement boundary)** | provider/model/surface/unit/method/uncertainty/freshness become required fields; character heuristics remain fallback-estimate and do not accept corpus/release solutions at your doorstep |
| [HashiCorp — Detecting drift](https://developer.hashicorp.com/terraform/plugin/sdkv2/best-practices/detecting-drift) + [HashiCorp — State upgrade](https://developer.hashicorp.com/terraform/plugin/framework/resources/state-upgrade) | desired/observed separation, read-after-write reconciliation, explicit state migration | official sources, verified 2026-08-03 | **adopt (design pattern)** | provider control plane uses observe → diff → explicit managed apply → readback; legacy forms are migrated explicitly and unresolved ownership stays non-green |
| [`packages/aicore/configs/provider-distribution.json`](reference/provider-distribution.md) | SSOT skill connect/vendor/discovery channels per provider (Cursor D8 discovery-only) | repo-native, 2026-09-17 | **adopt** | `core.provider.distribution` + `publication.py`; without `if cursor` in Python |
| [`packages/aicore/configs/provider-projection.json`](reference/provider-projection.md) | SSOT instruction/command projection policies per provider | repo-native, 2026-09-17 | **adopt** | `core.provider.projection` + harness/task dispatch; shared configs in `configs/` |
| [`configs/config-inventory.json`](reference/configs.md) | Owner and consumer inventory of repository configs | repo-native, 2026-10-07 | **adopt** | `scripts/test-config-inventory.py` in CI hygiene; `core.shared_config_path` resolves owner paths without fallback |
| [Anthropic — Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) | task/trial/grader/transcript/outcome/harness; capability and regression evals; fixed task bank | first-party, 2026-01-09; verified 2026-07-24 | **adopt (method)** | base failure-corpus and transcript-aware eval plan design; 20–50 real tasks as a start, regression floor close to 100% |
| [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/) | vocabulary for conversation/agent/tool IDs, token usage, latency and evaluation attributes | open standard, development status; verified 2026-07-24 | **reference** | shape reference for stdlib-only unified trace; OTel runtime dependency is not added |
| [Google SRE — Postmortem Culture](https://sre.google/sre-book/postmortem-culture/) | blameless incident anatomy: impact, causes, action items, prevention and follow-up | first-party SRE book; verified 2026-07-24 | **adopt (method)** | same-finding loop is translated to incident/root-cause with owner/action/verification, and not infinite retry |
| [MT-Bench / LLM-as-a-Judge](https://arxiv.org/abs/2306.05685) · [Position Bias](https://aclanthology.org/2025.ijcnlp-long.18/) · [Self-Recognition](https://aclanthology.org/2024.findings-emnlp.703/) · [Self-Preference](https://aclanthology.org/2025.emnlp-main.86/) | bias and reproducibility limits model-judges: position/verbosity/self-enhancement, repetition stability, self-recognition, self-preference | primary academic publications; verified 2026-08-08 | **reference (architectural boundaries)** | `return-judgement` v1: judge like sensor, independent reviewer, first-class abstinence, prohibition LLM tie-break/self-judgement and monotonous influence |
| [Anthropic — Equipping agents with Agent Skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills) + [CSA/Trail of Bits — Skill Scanner Bypass](https://labs.cloudsecurityalliance.org/research/csa-research-note-ai-agent-skill-scanner-bypass-20260610-csa/) + [cisco-ai-defense/skill-scanner](https://github.com/cisco-ai-defense/skill-scanner) + [Heeler — Agent Skills security](https://www.heeler.com/resource/introducing-agent-skills-security-identify-and-prevent-risk-in-the-ai-agent-supply-chain) | supply-chain external skills: four threat classes (prompt injection · data exfiltration · malicious code execution · over-permissive tool use), position «there is no first-party scanner, audit the bundle manually», proven usefulness of scanners, «no findings ≠ safe» | first-party + CSA research note 2026-06 + OSS; verified 2026-07-31 | **adopt (method)** · **reference (patterns)** | human audit of 56 bundles as the LIMIT of trust + subordinate triage stage `update-upstreams.sh --check`. Patterns cisco-ai-defense **rewritten with their own stdlib rules** — taken as a PATTERN, not as a dependency (`root.engineering-invariants`); YARA/LLM-upstream stage is not transferred (external dependency / named CSA required) |
| [hesreallyhim/awesome-claude-code](https://github.com/hesreallyhim/awesome-claude-code) | curated directory | 47k★, active, NOASSERTION-persons. | reference | confirms the real subagent scheme; Design-Review ≈ agent-pack 1:1 |
| [vijaythecoder/awesome-claude-agents](https://github.com/vijaythecoder/awesome-claude-agents) | orchestrator + specialists | 4.3k★, MIT, ~stale | reference | blueprint `orchestrator → stack-detect → specialists` (= our profiles + `_common`) |
| [VoltAgent/awesome-claude-code-subagents](https://github.com/VoltAgent/awesome-claude-code-subagents) | 150+ subagents | 22k★, MIT, active | reference | seed-material roles; native frontmatter |
| [claude-rio](https://github.com/alex-popov-tech/claude-rio) | hooks-matcher (routing) | ~20★, MIT, early | adopt → `harness router` | contract `UserPromptSubmit.additionalContext` went into hooks `agent-router` |
| Self-Improving session-hooks | patterns session-hooks | talk-level, without repo | adopt → package `analyst` | confirms `additionalContext`-path (memory-digest-hook in maind) |
| [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) | multi-agent runtime | 35k★, MIT | **skip** (reference) | orchestration dictionary only (supervisor/swarm) for prose - a different layer |
| [itgoyo/awesome-agent-skills](https://github.com/itgoyo/awesome-agent-skills) | skills catalog | 138★, CC-BY | reference (deferred) | pattern `skill-rules.json` sidecar (deferred) |
| [wshobson/agents](https://github.com/wshobson/agents) | stack bundles + model-tiers + multi-harness generator (Claude Code · Codex CLI · Cursor · OpenCode · Copilot · Gemini CLI) | 38 346★, MIT, active (`pushed_at` 2026-07-22); verif. GitHub API + forward reading `ARCHITECTURE.md` 2026-07-29 | reference | profile blueprint: stack→bundle, per-agent model-tiers; invariant «generated gitignored and cannot be straightened by hand» + `make garden` as a reference for a single drift gate |
| [anthropics/skills](https://github.com/anthropics/skills) | official skills (skill-creator, mcp-builder, doc/creative) | first-party, Apache-2.0 (docx/pdf/pptx — Proprietary) | **adopt** (method) | eval-harnes skills from `skill-creator` (evals/benchmark, description optimization); docx/pdf/pptx — **skip** (Proprietary); `mcp-builder` — reference (deferred) |
| [obra/superpowers](https://github.com/obra/superpowers) | process/discipline-skills + frame (hooks-bootstrap) | MIT, active, multi-harness | **adopt** (method) | pressure-tests (`writing-skills` — TDD for documentation) in eval-format; iron-law/red-flag/SessionStart-bootstrap — reference (deferred) |
| [affaan-m/ECC](https://github.com/affaan-m/ECC) | cross-harness framework (skills/agents/hooks/security) | ~221k★, MIT, active | reference | supply-chain-vendor scan, hook-profiles, PreCompact, fact-force gate — **deferred**; infrastructure (memory/graph) is already at `maind` |
| [ai-agent-rules](https://github.com/wpfleger96/ai-agent-rules) · [anywhere-agents](https://github.com/yzhao062/anywhere-agents) · [agent-config](https://github.com/brianlovin/agent-config) · [ai-cli-mcp](https://github.com/mkXultra/ai-cli-mcp) · [agent-bridge](https://github.com/raysonmeng/agent-bridge) | multi-provider target classes, manifest/lock/hash/drift, lightweight sync and agent bridges | shallow commit-pinned audit 2026-07-19 | **reference** | P0/P1/P2 patterns; deterministic adapters/packaging controls accepted, external deps/symlink-first/runner bridge are not included in migration core |
| [Anthropic — Founder's Playbook](https://www.anthropic.com/) | methodology AI-native startup (Idea/MVP/Launch/Scale, Claude like structured devil's advocate) | first-party, May 2026 | **reference** | frame founder-track + `idea-audit` (4 module, stage-context, premature scaling); epigraph = paraphrase, not verbatim |
| [CB Insights — Why Startups Fail](https://www.cbinsights.com/research/report/startup-failure-reasons-top/) | startup post-mortems, «no market need» | classic ~2014, update 2026 | **reference** | zone argument idea-validation in `idea-audit`; cite as a classic (~42%), 2026 reformulates ~43% poor PMF |
| [Anthropic — Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) | context engineering for agents | first-party, Sep 2025 | **reference** | base Perplexity-skill `idea-architect` (role/modes/web search rules/antipatterns) |
| [Anthropic Claude Code best practices](https://code.claude.com/docs/en/best-practices) + [memory/instructions](https://code.claude.com/docs/en/memory) + [OpenAI Codex customization](https://developers.openai.com/codex/customization/overview) + [Codex prompting guide](https://developers.openai.com/cookbook/examples/gpt-5/codex_prompting_guide) + [PMI rolling-wave planning](https://www.pmi.org/-/media/pmi/documents/public/pdf/certifications/practice-standard-scheduling.pdf) + [NIST AI RMF](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf) + [GitHub Spec Kit](https://github.com/github/spec-kit) | short always-on context, progressive disclosure, rolling-wave/management-by-exception and risk-adaptive assurance for agentic-plans | first-party/standards + OSS; 4 regular request `perplexity-web`, primary pages rechecked 2026-08-10 | **adopt (method)** |: strict initial contract, adaptive grouping/local repair, audit only by material trigger; decomposition and new control plane — only with measured residual defect |
| [Google SRE — Reliable Product Launches](https://sre.google/sre-book/reliable-product-launches/) + [Release Engineering](https://sre.google/sre-book/release-engineering/) + [NASA SWE-141](https://swehb.nasa.gov/spaces/SWEHBVD/pages/102695499/SWE-141%2B-%2BSoftware%2BIndependent%2BVerification%2Band%2BValidation) + [NASA SWE-223](https://swehb.nasa.gov/spaces/SWEHBVD/pages/105710152/SWE-223%2B-%2BTailoring%2BIV%2BV%2Bproject%2Bselections) + [GitHub protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches) | light common path, assurance, proportional criticality and separate checks/review gates | primary sources; original straight web research 2026-09-11 (in that session Perplexity connector was missing) | **adopt (implemented locally)** | Solution: default direct-close; phase audit only when residual risk and address owner consent.  |
| [Anthropic — Building effective agents](https://www.anthropic.com/engineering/building-effective-agents) + [Google SRE — Reliable Product Launches](https://sre.google/sre-book/reliable-product-launches/) | simple agent workflows, price latency/cost, stopping conditions and simplified common path | primary pages opened 2026-09-11; Perplexity search is available but did not return a result before stopping waiting; direct used web fallback | **adopt (method; implemented locally)** | conflict resolved assurance/lifecycle, clarified closure in the current invocation and reuse checks; the results and boundaries are recorded in the report. Specific consent policy — is the owner's decision, not a requirement of these sources. |
| [PRINCE2 Agile progress reporting](https://www.prince2official.com/Prince2-News-and-Announcements/agile-progress-reporting-dashboards) + [GitHub Spec Kit spec of specs](https://github.github.com/spec-kit/concepts/spec-of-specs.html) + [Google SRE monitoring](https://sre.google/sre-book/monitoring-distributed-systems/) + [Azure Retry](https://learn.microsoft.com/en-us/azure/architecture/patterns/retry) + [Kubernetes probes](https://kubernetes.io/docs/concepts/workloads/pods/probes/) + [Claude Code environment variables](https://code.claude.com/docs/en/env-vars) | D9+D13 committed external ledger for causal field canary | first-party; verified and recorded 2026-08-11 | **reference** | prerequisite `; URLs remain reproducible committed-HEAD evidence, are not replaced item acceptance |
| [Perplexity — Prompt Guide](https://docs.perplexity.ai/guides/prompt-guide) + Help Center | official rules for wording requests (specificity, version+context, cap result counts, separate concerns, grounding-rules) | first-party, verif. 2026-06-29 | **reference** | fact-basis CORE-skill `research/query-craft` (5 request slots, anti-patterns, modes search/advanced/deep); verified RAG (WebSearch+WebFetch), not from memory |
| `perplexity-web-mcp` — integration note (contract MCP) | demon+pools (`--pool`, to `maxConcurrency` tabs, `idleShutdownMs`, auto-fallback in legacy); error codes (`BROWSER_BUSY`/`TIMEOUT`/`LOGIN_REQUIRED`/`PROTOCOL_MISMATCH`/`INTERNAL`); client-side resilience (retry-with-backoff 3×, `notify-send`, JSONL error-log `$XDG_STATE_HOME/…/errors.jsonl`); login grace-window (~3 min + cooldown, fail-fast) | sibling-package (outside the repo), checked by code `src/{config,resilience,dispatcher}.ts` 2026-07-03 | **adopt** | updated `research/query-craft` (section «Competitiveness and sustainability» — resilience/grace-window) and `general/mcp-advisor` (pull note); old bypass «do not parallel» filmed as legacy; `.mcp.json` umbrella → `--pool=swissknifeman` |
| Industry-patterns workflow-resilience 2025–2026 (rate-limit backpressure/circuit-breaker, job/worker/supervisor liveness, progress+deadline watchdog, `Promise.race`/cancellation, structured-output retry, infra-vs-task failure taxonomy) — Portkey/TrueFoundry/respan.ai/Vercel Workflow/claude-code issues | how to design sustainable agent-workflow under rate-limit/hang | web/vendor-blogs + official. SDK-docks, verification. `perplexity-web` 2026-07-01 | **reference** | fact-basis of the section «Resilience» (`background-agents.md`) and dev-loop-edits (audit `2026-07-01-workflow-resilience-ratelimit`): fail-fast, `infra-failed`, supervisor+`PushNotification`; rejected in-script `withDeadline` (V8-sandbox: no `Date.now()`/`setTimeout`/cancel) |
| LangSmith / AgentOps / Helicone (LLM-agent observability platforms) | categories of agent failure patterns that these platforms trace: clients tool-error, no-op/redundant retry, stuck reasoning loops, bloat context/token, latency/cost-anomalies | first-party docks/platform dashboards, verification. `perplexity-web` 2026-07-02 | **reference** | CATEGORIES benchmark for heuristics `core/pathology.py` (`file-reread`/`tool-error-loop`/`no-op-run`/`cache-miss`/`retrieval-stuffing`/`static-context`) — thresholds are NOT calibrated to these platforms, only waveforms; see [Pathology catalog](/analyst/guide/pathologies) |
| [Kulaxyz/self-learning-skills](https://github.com/Kulaxyz/self-learning-skills) | self-learning prompt skill (0 code/hooks, auto-recording of skills) | 621★, MIT, ~3 day, viral/no-track-record | **reference** | epistemic discipline of recording knowledge in `analyst` (promotion-rule: passing-check+named-failure+ruled-out dead-end; capture-failures; secret-by-link; triage skill/memory/skip). Auto-record **inverted** in human-gate (synthesis - in the internal design of the package `analyst`). |
| [affaan-m ECC — continuous-learning-v2](https://github.com/affaan-m/everything-claude-code) | observations→instincts→evolved-skills, confidence-shooting galleries, demon Haiku | MIT, active | **adopt (pattern)** | 3-tiered staircase + privacy-by-directory-layout + confidence 0.3/0.5/0.7/0.9 + human-gated evolve/promote in `analyst`. **Daemon abandonment** — cadence on-demand (v1). Verifier. GitHub API+DeepWiki+Mintlify |
| [Diátaxis](https://diataxis.fr/) | documentation structure framework (tutorial/how-to/reference/explanation by reader intent) | de-facto standard (Read the Docs etc.), verif. `perplexity-web` 2026-07-02 | **reference (method)** | umbrella site framework: landing = package directory map; per-package `index.md` = «what is this + when to take», usage — in `guide/`; separate `getting-started` (tutorial) and `tasks` (how-to). A complete 1:1 migration of all pages was NOT carried out - a navigation framework was introduced, all content was not rewritten |
| [mem0](https://github.com/mem0ai/mem0) ([arxiv 2504.19413](https://arxiv.org/abs/2504.19413)) | agent memory: extraction→consolidation | Apache-2.0 | **adopt (pattern)** | consolidation-taxonomy mem0 = **ADD/UPDATE/DELETE/NOOP** (canon `prompts.py`) → adapted as **ADD/UPDATE/NOOP/CONFLICT** (`analyst.lessons.classify_consolidation`): **CONFLICT instead DELETE** — auto-removal would violate the invariant «man in the gate» (F-RAG-2, verified perplexity 2026-07). Plus retrieve-similar-before-write (BM25/Jaccard stdlib); soft-invalidate instead delete; timestamp-ranking instead decay. Extraction facts - LLM-inherent (flag) |
| Self-improving/anti-poisoning canon: [SICA](https://arxiv.org/abs/2504.15228)·[Voyager](https://voyager.minedojo.org/)·[Reflexion](https://arxiv.org/abs/2303.11366)·Generative Agents·A-MEM · [OWASP ASI06](https://genai.owasp.org/)·[MITRE AML.T0080](https://ttps.ai/technique/memory_poisoning.html)·MINJA | guardrails vs model-collapse/memory-poisoning | academic.+security-frameworks, verification. 2026-07 | **reference (compliance)** | safety-core `analyst`: self-verification is proven sufficient against collapse → validate-before-promote; human-gate+provenance+namespace = Tier-1; segment-per-tenant/expire-unverified (OWASP). Synthesis - in the internal design of the package `analyst`. |
| Industry prompt-engineering for RAG-forcing / verification-footer / self-critique (2025–2026) — plan→retrieve→verify loop, tool-forcing, structural sections `unverified_assumptions`/`tool_failures`/`verification_report`, «cited but not verified» (dev.to · sey.pro) | how to force plan agent 100% rely on fresh RAG and honestly endure the untested | web-blogs, verification. `perplexity-web` 2026-07-01 | **reference** | fact-basis footer'a «Verification» in `verify-claims`/`decision-verification`/CLAUDE.md + block `VERIFICATION` orchestrator + `tool_failures[]` in `dev-loop.js`; token saving solution - aggressive flat-rate `perplexity-web` |
| [Roave/BackwardCompatibilityCheck](https://github.com/Roave/BackwardCompatibilityCheck) | static BC-public checker API PHP-packages (git diff current branch vs baseline-tag) | stable, MIT, `^8.13`, verif. RAG 2026-07-02 | **adopt** | BC-axis reviewer'a `agent-packs/laravel-package`: test interview `BC_CHECK_CMD` (`test -x vendor/bin/roave-backward-compatibility-check`) — in the absence of a binary, the axis remains prose and does not block the pack |
| [github/spec-kit](https://github.com/github/spec-kit) | spec-driven development: `constitution → spec → plan → tasks → implement`, MD-artifacts like SSOT project | first-party GitHub, MIT, active, ver. `perplexity-web` 2026-07-02 | reference | studied during design plan-protocol (`SKM-MASTER-002` phase A/P1): machine-markers/phase freezing/anti-staleness |
| [steveyegge/beads](https://github.com/steveyegge/beads) | git-backed graph-issue-tracker as persistent memory for AI-agents (DAG tasks, `bd ready` — unlocked only) | 13.7k★, active, ver. `perplexity-web` 2026-07-02 | reference | studied during design plan-protocol: machine-markers/phase freezing/anti-staleness |
| [planning-with-files](https://github.com/othmanadi/planning-with-files) (pattern Manus «Context Engineering for AI Agents») | Claude Code skill, reproducing Manus todo.md-recitation: `task_plan/findings/progress.md` + PreToolUse/Stop-hooks vs goal drift | third party skill-repo, ver. `perplexity-web` 2026-07-02 | reference | studied during design plan-protocol: machine-markers/phase freezing/anti-staleness |
| `perplexity-web` synthesis - voice-agent patterns 2025–2026 (LiveKit Agents · Pipecat smart-turn-v2 · OpenAI Realtime VAD · WebRTC RFC 8825) | architecture voice-agents: WebRTC media + WebSocket control, 3-layered turn-detection (VAD+semantic EOU+LLM-side), barge-in <500ms, latency <800ms (1200ms — LEGACY/IVR), session state-machine | web/vendor-docks+specs, verification. `perplexity-web` 2026-07-03 | **reference** | skill `voice-ai` (`skills/voice-ai/voice-ai/`): latency thresholds/barge-in, session-machine idle→listening→thinking→speaking, backchannel-detection |
| `perplexity-web` synthesis - RU voice-stack (Yandex SpeechKit gRPC v3 streaming · SaluteSpeech · YandexGPT/GigaChat) + offline alternatives (Whisper/pyannote/Piper-VITS/Llama) | what STT/TTS/LLM-services are relevant for voice agents in the Russian Federation, compliance with 152-FZ | vendor-docks, verification. `perplexity-web` 2026-07-03 | **reference** | skill `voice-ai`: RU-stack section + obvious remark of 152-FZ (region=RU, without cross-region fallback) |
| `perplexity-web` synthesis - monorepo.tools · contracts-as-SSOT+codegen patterns for polyglot monorepo | how to organize `services/+packages/js|php|flutter/+apps/+infra/`, dependency direction, per-package vs unified semver, separate lockfiles, CI multi-lang | web/vendor-docks, verification. `perplexity-web` 2026-07-03 | **reference** | `docs/guide/polyglot-monorepo.md` (skiller) + profile `platform-service` (`packages/skiller/profiles/`) |
| `code.claude.com/docs/en/skills` (frontmatter `model`/`effort`) · `…/model-config` (no API change session model) · `…/sub-agents` (no per-subagent effort) | official spec: where they live `model`/`effort`, what model change handles exist | first-party, verif. `perplexity-web` 2026-07-15 | **reference** | fact confirmed «no API switch model/effort sessions from within the team» → `plan-run` inherits the session route (routing-**gate failure** with a weak model), does not switch the model/effort |
| `perplexity-web` synthesis - token economy of agent systems 2026 (Anthropic prompt-caching docs · /compact-vs-/clear practice · sub-agent isolation · tool-result trimming/PARTIAL-receipts · MCP tool-def deferred loading (paddo.dev/reddit-case 92%) · tiered model-routing «do not downgrade reviewers») | current (2026) external token saving levers verified against repo architecture | web/vendor-docks + first-party Anthropic, verif. `perplexity-web` 2026-07-15 (6 requests; context7 — quota-miss) | **reference** (C4/C5 — adopt-candidates backlog) | `findings/P5-external-bestpractices.md` plan: C1–C3/C6 confirm what has already been accepted (`context-economy`, workflow-craft, D8/D9-routing); adopt-candidates - ceiling+truncation-receipt in replies maind MCP-tools (C4) and weeding MCP-servers / deferred tool-loading (C5, `ENABLE_TOOL_SEARCH` — `[UNVERIFIED]`, pre-check by first-party dock); C7/C8 → rejected-optimizations |
| [tirth8205/code-review-graph](https://github.com/tirth8205/code-review-graph) | local-first code graph (Tree-sitter AST → SQLite) + MCP (30 tools)/CLI; 40+ languages; application ~82× token-savings per question (self-metering) | 26k★, MIT, active; verific. GitHub API + README 2026-07-25; pilot-measurement 2026-07-27 (v2.3.7) | **skip** (measured, owner's verdict) | Pilot vs. Serena executed: `Ops` excellent (build 1.66 with / 405 files, increment 0.24 s), but precision blast-radius vs co-change ground truth `P_impact` = **0.039** at the threshold announced BEFORE measurement `≥ 0.40` (24 fold'and on 3 commits Laravel-project; threshold crossed 1 fold). Failure due to NOISE, not due to blindness: recall 0.40–0.43, but 110 files per seed, true - at positions 77 and 102. We do not connect **by our numbers on our codebase**; code graph canon remains **Serena** (LSP). Taken from: rule «graph-retrieval MCP does not connect via README — only after your co-change-measurements» + reopening triggers → skill body `general/mcp-advisor`; numbers -, solution package - `findings/P5.2-codegraph-verdict-packet.md` |
| [breferrari/obsidian-mind](https://github.com/breferrari/obsidian-mind) | Obsidian-vault as persistent agent memory (CC/Codex/Gemini), git-sync, hooks+MCP semantic search | 3.9k★, MIT, TS/Node; verif. GitHub API + README 2026-07-25 | **skip** (pattern-reference) | as a memory mechanism duplicates maind/agentmemory + Brain vault; useful pattern MEMORY.md-pointers are already canon; cross-machine is resolved by the host daemon |
| [ayghri/i-have-adhd](https://github.com/ayghri/i-have-adhd) | skill ADHD-friendly output: 10 rules (action-first, numbering, no preamble/closers) | 9.6k★, MIT, Python; verif. GitHub API + README 2026-07-25 | **skip** (reference) | duplicate lean output style + `core:compact-responses`; 1–2 rules (answer-first, no closers) — candidates for editing compact-responses |
| [openai/codex-plugin-cc](https://github.com/openai/codex-plugin-cc) | official OpenAI plugin CC: `/codex:review\|adversarial-review\|rescue\|transfer`, subprocess over local `codex` CLI | 29.9k★, Apache-2.0, first-party OpenAI; verif. GitHub API + README 2026-07-25 | **adopt (Codex CLI as second driver) · reference (plugin, opt-in per-plan)** | plan: Codex CLI directly drives the same plan-protocol when unavailable Claude (dogfood — «arrived with 4 interventions», 2 out of 4 were fixed by fixing the root `AGENTS.md`); plugin `codex-plugin-cc` is installed, but is ONLY enabled when explicitly specified in the plan (text rule, no machine gate) |
| [Anthropic — Prompting Claude Opus 5](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5) | first-party guide: explicit anti-pattern verify/double-check instructions (over-verification), effort-sweep (low/medium cheaper with quality), subagent-mouthguards, verbosity/scope-striping, 1M context | first-party, 2026; read 2026-07-25 | **adopt (method)** | plan: Brain model-notes squeeze + point revision task-commands/agent-packs (remove double-check from Opus-pinned, review effort-pins) — D5: model-specific in model-notes, not in evergreen-skills |
| [Anthropic — Prompting Claude Sonnet 5](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-sonnet-5) | first-party guide implementation-dash: same anti-pattern of explicit verification/status update forests also applies to Sonnet-timbered surfaces (5 of 10 stabbed commands); literalness of instructions (does not generalize the rule from one object to others); effort-mapping during migration (medium≈S4.6 high, high≈S4.6 max); +30% tokenizer; confidence-level for a find in code review | first-party, 2026; read 2026-07-25 | **adopt (method)** | plan: Brain model-notes `sonnet-5-prompting.md` + entry into revision P2.2/P2.3 |
| [Anthropic — Effort](https://platform.claude.com/docs/en/build-with-claude/effort) | first-party parameter spec `effort`: 5 levels (low/medium/high/xhigh/max) + typical use case, behavioral signal (not a budget token), `xhigh`/`max` — thinking cannot be disabled, cache invalidation when changing effort between requests | first-party, 2026; read 2026-07-25 | **adopt (method)** | plan: bearing the source of both Brain-notes (Opus 5 + Sonnet 5); effort-tables of both notes - direct squeeze |
| [romarayt/raytsystem-public-os](https://github.com/romarayt/raytsystem-public-os) | local-first agent-based workspace; for us - **gate mechanics**: policy as data, preflight-hash entry, one guard for CLI and pre-commit, simulator ≡ runtime, versioned contract registry, docs-DoD + coverage for live contracts, qualification report with certificate class | Apache-2.0; public tree - **squashed image** (1 commit, 0 tags), therefore ★/age is not an indicator; maturity removed by artifacts: 35 ADR, 73 test (809 KB), dated run report, field issue with numbers. Verify GitHub API + `raw.githubusercontent.com` + `perplexity-web` 2026-07-25 | **adopt (mechanics, 17 item'ov)** · **skip** (uv/pyproject/React, catalog snapshot of schematics per version, mandatory for pre-commit) · **reference** (politics simulator as code, `reason` in adapter directories) | (layer 1) + `research/09-rayt-adoption-map.md` (verdicts for each technique, map for packages). Addressee - **phase P8** plan (9 techniques), the remaining 10 are in his `roadmap.md` (D41: separate plan canceled) |
| External architectural audit `core`/provider (Perplexity, is pinned with hashes in) | third-party parsing of monorepo: suggests rebuilding `core`/provider layer, introduce mandatory contract tests, remove ownership policy from hooks, implementation program for 12 PR / 90 days | one-time parsing, the snapshot is pinned and immutable; verified **by code**, not as described, 2026-07-26 | **partially adopt (3 of 16), basically reject** |: 16 bearing hypotheses adjudicated against functions/callers/tests - **3 accept** (provenance of the config resolution is not rendered to anyone; `run-report` degrades silently; possession predicate `managed AND NOT user_owned` implemented three times without parity-gate) → are framed as FUTURE offers FP-1/FP-2/FP-3 with the owners, **11 reject**, **2 unknown** (H15/H16 — evidence does not exist). No hypothesis is implemented by this plan; verdicts -, `root/provider-core-hypotheses.md`; rejected - [rejected-optimizations](./rejected-optimizations.md) |
| [opencode.ai/docs/skills](https://opencode.ai/docs/skills/) | which skill catalogs does it read? OpenCode: `.opencode/skills/`, `~/.config/opencode/skills/`, `.claude/skills/`, `~/.claude/skills/`, **`.agents/skills/`**, `~/.agents/skills/`; required frontmatter `name` (1–64, lowercase-kebab, = directory name) + `description` (1–1024) | first-party, WebFetch 2026-07-29 | **reference** (provenance) |: channel `.agents/skills`, which skiller already writes as Codex-output, read WIDE than one Codex — rule «do not break `.agents/skills`». OpenCode remains out managed-providers; the fact is recorded as provenance. Measurement - F1 |
| [cursor.com/docs/skills](https://cursor.com/docs/skills) | Cursor looking for `.agents/skills/`, `.cursor/skills/`, `~/.agents/skills/`, `~/.cursor/skills/`; for back-compat additional `.claude/skills/` and `.codex/skills/`; recursive traversal (monorepo-friendly); optional `paths`/`disable-model-invocation`/`metadata` | first-party, WebFetch 2026-07-29 | **adopt** (managed provider) | Third managed-provider `cursor`: `skills.repository` — zero-writer binding on `.agents/skills` |
| [cursor.com/docs/reference/permissions](https://cursor.com/docs/reference/permissions) | `.cursor/permissions.json`: `mcpAllowlist`, `terminalAllowlist`, `autoRun`; per-user and per-repo arrays are concatenated (repo only expands) | first-party, verified_at 2026-09-17 | **adopt** (managed provider) | harness `settings.permissions` + IDE allowlist half; freeze S1 §3.2 |
| [cursor.com/docs/cli/reference/permissions](https://cursor.com/docs/cli/reference/permissions) | `.cursor/cli.json` `permissions.allow/deny`; `deny` wins `allow` and worries `--force` | first-party, verified_at 2026-09-17 | **adopt** (managed provider) | harness CLI permissions renderer; shared deny floor D4 |
| [cursor.com/docs/cli/reference/configuration](https://cursor.com/docs/cli/reference/configuration) | project-level `.cursor/cli.json` accepts **only** `permissions`; `approvalMode`/`sandbox` — global-only | first-party, verified_at 2026-09-17 | **adopt** (constraint) | E14.1: renderer fails when trying to write mode in project file |
| [cursor.com/docs/reference/hooks](https://cursor.com/docs/reference/hooks) | hooks merge layers; `failClosed: true`; `beforeShellExecution`, `sessionStart`, `subagentStop`, `stop` etc. | first-party, verified_at 2026-09-17 | **adopt** (partial P1) | P1 ships `security.safe-dirs` only; others lifecycle — P3+ |
| [cursor.com/docs/context/rules](https://cursor.com/docs/context/rules) | `.mdc` frontmatter: `alwaysApply`, `globs`, `description`; plain `.md` without frontmatter ignored | first-party, verified_at 2026-09-17 | **adopt** (managed provider) | `.cursor/rules/swissknifeman-{core,launch,packages}.mdc`; D11 trigger-scoped |
| [learn.chatgpt.com/docs/build-skills](https://learn.chatgpt.com/docs/build-skills) | budget **detection** skills Codex: are first loaded into the context only `name`/`description`/`path`, and THIS listing is restricted «maximum 2 % of the model context window or 8,000 characters for an unknown window»; after selection «Codex still reads the full SKILL.md» | first-party (via citing search `perplexity-web`), 2026-07-29 | **reference** |: thesis «8 KB — hard BODY limit `SKILL.md` y Codex» (incl. at wshobson, where they cut bodies for it) **debunked** — 8 000 limit the detection LISTING, not the body of the selected skill. 37 roster skills > 8 KB are not broken due to this fact (maximum — `general/plan-protocol` 89 988 bytes). The real shortage is quality `description` and the number of simultaneously installed skills. **`[UNVERIFIED]`:** own measurements live Codex CLI not carried out; As a rule, body drops cannot be taken without it. Parsing - `findings/01-rag-cross-harness-2026-07-29.md` F4 |
| [openai.com/index/harness-engineering](https://openai.com/index/harness-engineering/) | first-party OpenAI about hardware engineering - source of practices referenced `ARCHITECTURE.md` wshobson (along with the convention `agents.md`) | first-party; **`[UNVERIFIED]`** — is known from the link from `ARCHITECTURE.md` (read 2026-07-29), the text itself first-party not read | **reference** | So far only provenance: named as the root of the multi-harness generator practices wshobson (`findings/01-rag-cross-harness-2026-07-29.md` F3). Read the original source - before at least one of its thesis falls into a supporting position |
| Inbound owner audit (Perplexity, 2026-07-29) — is pinned in | summary external analysis of monorepo: skills/token-budget, matrix role × stack, transfer from `wshobson/agents` and Anthropic multi-agent research, target structure of the repository, what to add to the documents | one-time parsing, the snapshot is pinned and immutable; adjudicated by code 2026-07-29 | **reference** (partially **adopt**: §11-rules 1 and 4, §7 policy-layer, §12) | **Disclaimer: the audit is compiled according to public README, and not wood** — six of its eight core recommendations have already been implemented (agent-packs, bucket crushing, role × stack, model-shooting galleries, provider-contract), and he proposed what had already been rejected, because the provenance catalogs lagged behind what was decided. Accepted: root always-on context = short index; spawn by context budget; delegation contract as a required form; updating the frame canon (the input itself `framework-overview.md` went bad and generated false audit sections). Rejected - [rejected-optimizations](./rejected-optimizations.md) (§10.1/§10.2/§10.3/§10.5). Section-by-section verdict - /research/01-audit-adjudication.md` |

## Cards

### LLM-as-a-Judge — reference (boundaries `return-judgement` v1)

Four primary publications support different, non-interchangeable risk classes: MT-Bench —
position/verbosity/self-enhancement bias; IJCNLP-AACL 2025 — position bias and instability
permutations; Findings EMNLP 2024 — ability of models to recognize their own text; EMNLP 2025 —
self-preference with quality control of your own response. This is not runtime dependency and not the basis
delegate authority to the model. **Taken from:** reviewer is separated from executor, verdict — immutable
evidence with closed enum and abstinence, deterministic policy ignores confidence and cannot be
weakened verdict'ohm. **Not taken:** majority voting, ad-hoc resampling and promise token-level
reproducibility hosted-models. Verified 2026-08-08 on primary pages arXiv/ACL Anthology;
correction of erroneous attribution of the original research-of the slice is written to
.

### Official spec Claude Code — adopt
The canon on which everything stands. Subagent = `.claude/agents/*.md` with frontmatter
`name/description(+ <example>)/tools/model/color`; **auto-delegation proceeds according to `description`**, a
not by fictitious field `triggers`. SKILL.md — minimum `name/description`, auto-activation
progressive opening. Hooks - fix. list of events + JSON-contracts
(`hookSpecificOutput.additionalContext` etc.).
**Pros:** authoritative, free, diagram taken verbatim. **Cons:** docks moved to
`code.claude.com` (network inaccessible from some environments); new subagent fields
(`disallowedTools/skills/memory`) are not yet committed as first-party — it’s too early to build on them.
**Taken from:** canonical `description`+`<example>` in all pack agents, field `color`, `model`-shooting ranges.

### Official Codex + Claude Code docs — adopt (contract facts)

Fresh Codex manual and official Anthropic docs retested 2026-07-19 for plan
. **Pros:** first-party contracts for instruction/config layers,
skills/plugins, hooks, MCP and security knobs. **Cons:** identical names hide different ones
trust/precedence/permission semantics; 1:1 field mapping is not valid. **Taken from:** general capability
language + native adapters; `approval`, `sandbox/access` and `project trust` remain different axes.

### Multi-provider upstream audit — reference

Five small repos from the summary line are tested for pinned commits 2026-07-19. **Pros:**
practical target classes, manifest/lock/hash/drift and light sync. **Cons:** none
covers contract swissknifeman; meet symlink-first, external dependencies and runner/bridge
scope. **Taken from:** only deterministic adapter and packaging-control patterns; runtime dependency,
fleet rollout and unattended runner to this migration are not migrated.

### hesreallyhim/awesome-claude-code — reference
Huge curated catalog. **Pros:** signal «that really hiss»; Design-Review-Workflow ≈
our agent-pack; confirms the real scheme and refutes skm2-fiction `triggers/agents`.
**Cons:** is a list, not a framework; custom license (copy prose - with verification);
child `*-agents` weak. **Taken from:** guide to the structure of the pack.

### vijaythecoder/awesome-claude-agents — reference (key blueprint)
Proves the user's target architecture «in practice»: `tech-lead-orchestrator` →
`team-configurator` (stack detection) → specialists, everything is as usual `.md` without runtime.
**Pros:** direct prototype «template by project type» (= ours `profiles/` + `_common`-orchestrator);
native minimal frontmatter. **Cons:** ~stale (Oct-2025); set uneven; config is written
in CLAUDE.md (risk of collisions - we have deterministic delivery). **Taken from:** orchestrator idea +
per-type selection.

### VoltAgent/awesome-claude-code-subagents — reference
150+ persons, MIT, active. **Pros:** safe to copy with attribution; 100% native
frontmatter — falls straight into `.claude/agents/`. **Cons:** static list only (no engine,
no hooks - ours `dev-loop.js`+`review-gate` more powerful in execution); general agents/verbose, without
`PLACEHOLDER`-templating/`skills:`. **Taken from:** seed-ideas for roles for future packs.

### claude-rio — reference → roadmap
Hooks-matcher: `UserPromptSubmit` skill prompts/keyword agent. **Pros:** closes
real space - agents/commands are NOT auto-activated; clean contract I/O; is unobtrusive. **Cons:**
is redundant for skills (they already autoload); JS/npx — vs stdlib-only; matcher is naive.
**Solution:** the contract was accepted, implementation is on Python: hooks
`packages/harness/configs/claude-code/hooks/agent-router/` + `harness router` (spec roadmap closed and deleted).

### Self-Improving session-hooks — reference → roadmap
Patterns: direnv-prompts, strike/praise CSV, skill-activation, SessionStart-context injection.
**Pros:** everything falls on the one already used in maind `additionalContext`-path. **Cons:** «CSV-scoring»
without canon (talk-level); `UserPromptSubmit.additionalContext` goes bad resume. **Solution:**
safe form of self-study - package `analyst` (via memory maind, manual promo);
rest of the streaming capture — `packages/analyst/docs/roadmap.md`.

### langchain-ai/langgraph — skip (reference)
Production-grade multi-agent **runtime**. **Pros:** mature topology dictionary (supervisor/swarm/
checkpointing). **Cons:** another layer entirely is the runtime that you execute, and swissknifeman
only **configures** Claude Code; heavy non-stdlib stack. **Taken from:** prose dictionary only
docs about orchestration.

### itgoyo/awesome-agent-skills — reference → roadmap
Directory directory (value - 4-5 downstream-repo). **Pros:** indicates quality MIT-
implementations (skill-rules.json scoring, role-hierarchy packs, model-tier rules). **Cons:** the list itself
gives nothing structurally; the stars are unreliable; reference repo domain. **Taken from:** pattern
`skill-rules.json` — deferred.

### wshobson/agents — reference (profile blueprint)
38 346★, MIT, active (`pushed_at` 2026-07-22) — stack-named bundles + single source→a lot
harnesov (Claude Code, Codex CLI, Cursor, OpenCode, GitHub Copilot, Gemini CLI) + per-agent
model-tiers. Verified GitHub API and direct reading `ARCHITECTURE.md` (2026-07-29,
 F3), and not by
model memory. **Five invariants `ARCHITECTURE.md`:** (1) single source of truth — authoring
only in `plugins/<name>/`, harnes-specific **is generated and gitignored**, «never hand-edit
generated files» (exception - small native-install registries, they only point to the source);
(2) one canonical context file (`AGENTS.md`, `CLAUDE.md` — symlink); (3) adapters own
harnes mechanics, the source code does not carry conditional logic; (4) mechanical compulsion with
remediation-hint for each find; (5) progressive disclosure to the end (context files ≤ ~150
lines, skill bodies ≤ ~8 KB). **Three gates:** `make validate` (structure of the generated),
`make garden` (drift: dead links, outdated artifacts, oversize-components, orphan's
marketplace), `make test` (386 tests, including round-trip and real-CLI smoke). **Pros:** almost
ready blueprint for `maind`/skiller-profiles: `specialized/<framework>` + `universal` + `core`,
versionable, without an engine. **Cons:** multi-harness generator heavy - take **form, not
scale** (live scope - Claude + Codex + Cursor as third managed-provider since 2026-09-17;
OpenCode remains reference-only); their skill body cap ≤ 8 KB — reinsurance, not a claim
platforms (see the line about the skill detection budget Codex in the summary table above). **Taken from:**
idea per-agent model-tiers (is implemented as `profile.model_tiers` → `MODEL_*`-placeholders);
invariant 1 «generated cannot be straightened by hand» — as a strengthening of our provider-contract
(we have part of the derivative committed and moved apart manually) and `make garden` — as reference
one drift gate on top of generated surfaces, which we don't have (yes `validate.sh` by
packages and `provider-docs.py --check`). Both -, parsing -
`research/01-audit-adjudication.md` §6.

### anthropics/skills — adopt (methodology)
Official demos skills. **Pros:** `skill-creator` gives exactly what we didn’t have -
**eval/benchmark** skills and description trigger optimization; its 3-tier disclosure model matches
with our `budget.py` (we are even stricter - ≤150 body lines). `mcp-builder` — design reference MCP-servers
(relevant `maind`/bucket `ai`). **Cons:** `docx/pdf/pptx` under **Proprietary**-licensed (vendor
not possible); others - Apache-2.0 «for demonstration only»; no need to drag the code (stdlib-only) — take the method.
**Taken from:** eval-skills training (`lib/skiller/eval.py`, `skiller eval`, format `evals/`); `mcp-builder`
and doc/creative — reference/skip.

### obra/superpowers — adopt (methodology)
Frame process-skills (TDD/debugging/brainstorming) + SessionStart-bootstrap, injection «skills
exist». **Pros:** `writing-skills` = **TDD for documentation** (pressure-tests: temptation scenarios,
run by subagents until compliance) — direct donor of our `pressure.json`; iron-law and red-flag-tables
rationalizations are powerful coercive techniques. **Cons:** list process-skills are already covered
(`general`/`quality`); bootstrap/hooks - separate layer `harness`. **Taken from:** pressure-tests in
eval-format; bootstrap/iron-law/hook-mechanisms - reference (postponed, see plan).

### affaan-m/ECC — reference
Large cross-harness framework (~221k★): 271 skill, 67 agents, 20+ hooks, security, memory.
**Pros:** combat patterns supply-chain-vendor hygiene (IOC-scan, sanitization prompt-injection),
hook-profiles (minimal/standard/strict), PreCompact memory-save, fact-force gate. **Cons:** infrastructure
(memory/graph/install-profiles/cross-harness) is already closed for us `maind`/`harness`/`skiller`; bulk
skill import is not needed (domaińsame, supervised). **Taken from:** nothing right away - supply-chain-scan and
hook-mechanisms **deferred** (real gap: we vendor 54 external skills with only sha256).

### Founder/idea-audit — methodology (Founder's Playbook · CB Insights · context-engineering) — reference
External frame for founder-track and new skill `idea-audit` (from Perplexity-audit, facts verified through
RAG before commit). **Anthropic Founder's Playbook** (May 2026) — real first-party guide to AI-native
startup (stage Idea/MVP/Launch/Scale; «structured devil's advocate» — core stage Idea); already quoted
in `adversarial-check`/`startup-lifecycle`. **CB Insights «42% no market need»** — real but classic
(~2014) digit; update 2026 reformulates as «poor PMF ~43%» → to quote as a classic, not as a recent one.
**Anthropic «Effective context engineering for AI agents»** (Sep 2025) — real article, basis
Perplexity-skill `idea-architect`. **Pros:** authoritative framework for skeptical work with AI at the idea stage;
**cons:** audit epigraph - paraphrase (not verbatim), number CB Insights can easily be rendered obsolete. **Taken from:**
4 module `idea-audit` (first-principles → market → arch-pre-mortem → kill/build), stage-context in
`adversarial-check`, AI/Agentic-category in `risk-assessment`, business_rationale in `architecture`,
falsification-signals in `idea-discovery`, external-signal-gate in `startup-lifecycle`.

### mem0 — adopt (pattern, consolidation taxonomy)
Memory consolidation taxonomy source for `analyst.lessons.classify_consolidation`. Canon mem0
(`prompts.py`) — four operations: **ADD / UPDATE / DELETE / NOOP** (F-RAG-2, verified perplexity
2026-07). `analyst` takes the taxonomy, but **consciously adapts**: **ADD / UPDATE / NOOP / CONFLICT** —
`CONFLICT` replaces `DELETE`, because auto-deleting a conflicting lesson would violate the invariant
package «man in the gate» (auto-record/auto-deletion in knowledge is prohibited). On the contradiction analyst not
erases, and **flag-and-ask**: marks the conflict and gives the solution to a person (`--supersedes`/`--force`).
**Pros:** mature, production-tested scheme extraction→consolidation; retrieve-similar-before-write
falls on stdlib-Jaccard without dependencies. **Cons:** himself mem0 — runtime dependency (LLM-extraction),
we don’t drag it - we take only the pattern. **Taken from:** taxonomy (with replacement DELETE→CONFLICT), retrieve-before-write,
soft-invalidate instead hard-delete, timestamp-ranking as an alternative decay (we have both: decay + ts).

### garrytan/gstack — reference (watch, not yet used)
https://github.com/garrytan/gstack — setup Claude Code Harry Tan (YC): 23 «opinionated tools»
starring CEO/Designer/Eng Manager, 50+ skills (`/ship`, `/spec`, `/qa`, `/retro`, `/pair-agent`,
`/context-save`), `gbrain` — semantic memory on PGLite between sessions. 122.5k★, MIT,
active (July 2026, 2264+ PR). Verified by GitHub API 2026-07-18 (Perplexity falsely counted part
of this non-existent party - verdicts only on API/README). **Pros:** real operating room
documentation (ARCHITECTURE 32KB, CLAUDE.md 59KB), combat solo scale; role-oriented
model is close to ours `roles/`. **Cons:** drag your own self-sufficient world entirely = duplicate
skiller/harness/maind; part of the value (memory) is closed for us mAInd. **Potential:** ideological donor
role-structures for supervisors Foreman (credentials/zones), patterns `/spec`, `/context-save`;
be implemented based on the measured need, through the vendoring of individual skills with provenance.

### mvanhorn/last30days-skill — reference (watch, not yet used)
https://github.com/mvanhorn/last30days-skill — agent «search engine for people, not editors»:
fresh in 30 days from Reddit/X/YouTube/HN/Polymarket/TikTok/arXiv, scoring by upvotes/likes/
in real money. 52.6k★, MIT, active (July 2026), is set as CC-plugin or `npx skills add`.
**Pros:** zero-config, complements our RAG-stack (perplexity/context7) measurement «that community
really discusses» — helpful founder-track (competitive-analysis, idea-audit) and research-fanout.
**Cons:** external sources/keys, has nothing to do with supervisors. **Potential:** research-
ecosystem tool; candidate for vendor research-bucket according to need.

### aiwithremy/claude-skills-llm-council — reference (just an idea; ⚠ NO LICENSE)
https://github.com/aiwithremy/claude-skills-llm-council — skill «LLM Council» by methodology
Karpathy (karpathy/llm-council): 5 independent advisors → peer-review → chairman synthesis.
1.1k★, April 2026, **no license** → code not to be vendored, just an idea. **Pros:** mature
methodology for multi-perspective decision evaluation. **Cons:** we have already implemented the pattern
with their Workflow-primitives (judge panel, adversarial verify, perspective-diverse verify) —
duplication. **Potential:** reconciliation of our judge-panel-mechanics with canonical methodology;
possible use in a progress engine Foreman (advice on controversial verdict continue/escalate).

### openai/codex-plugin-cc — adopt (Codex CLI, second driver) · reference (plugin, opt-in per-plan) — verdict (D84/P7.1–P7.3), roadmap closed
https://github.com/openai/codex-plugin-cc — **official plugin OpenAI** for Claude Code:
`/codex:review` and `/codex:adversarial-review` (second opinion by another model), `/codex:rescue`/
`transfer`/`status`/`result`/`cancel` — task delegation and background job's on Codex, subagent
`codex:codex-rescue`. 29.2k★, Apache-2.0, active (July 2026). Requires subscription ChatGPT
(on Free) or OpenAI API key; is using up limits Codex, NOT Claude.

**Actual verdict (2026-07-29, `finish` D84 → dogfood P7.1 → instruction layer P7.2 →
plugin P7.3).** Role Codex — **SECOND DRIVER**, not trivia delegation channel: same
ecosystem, same skills, same teams, same plan; if you have problems with your subscription Claude
owner changes to Codex CLI directly (`codex`/`codex exec`, canonical forms -
`AGENTS.md` § «Codex launch and hook integrity») and continues the same work plan-protocol.
Dogfood live item'e plan gave a verdict **«arrived with 4 interventions»** — two out of four
fixed by fixing the root `AGENTS.md`, two remain a known canon risk `plan-protocol`. Plugin `codex-plugin-cc`
**installed and configured**: always-on price measured by TWO instruments separately (native
`claude plugin details codex@openai-codex` ≈449 upstream surface current; repo projection
`skiller budget --first-turn` — delta 0, instrument is structurally blind to marketplace-plugins,
border named `CLAUDE.md` § «Philosophy and framework»), rollback rule - by DELTA and translation
through the 10,000 threshold. **Activation Rule
(text, no machine gate, D84):** plugin is used ONLY when explicitly specified in
plan that this work is carried out by subagents Codex; not used by default - second driver
works Codex CLI DIRECTLY, not through a plugin. **Pros:** first-party quality; cross-model
adversarial-review (optional, track B); unloading **limit Claude** (consumption Codex — general
agentic-subscription pool OpenAI, not free work). **Cons:** second subscription/billing;
coordination of two CLI; quality Codex on Laravel/Dart-stacks not measured; numerical economics
delegation (track pilot A, `A`/`R`) was NOT deliberately measured - ready protocol
is pulled out based on need.
**Taken from:** Codex CLI as second driver (direct launch, same plan-protocol); rule
plugin activation (text); two-tool always-on gate. **Roadmap-stub closed and deleted
from the catalog**: dated verdict lives in git-stories.

### romarayt/raytsystem-public-os — adopt (gate mechanics), skip (stack)
https://github.com/romarayt/raytsystem-public-os — local-first agent workspace (knowledge,
documents, tasks, verifiable workflows), Apache-2.0, Python + React. We have different purposes
(we are a tool manager), was therefore compared **mechanics of the instruction layer and gates**,
not a product.

**Maturity assessment is separate, because conventional indicators do not work here.** Public
tree - squashed shot: exactly **one commit** (`b5ac7056`, 2026-07-13), **zero tags and
releases**; ★ and the age of public history do not provide information either plus or minus. What's real
proves operation: dated machine-readable qualification report
(`evals/m5a/results/synthetic-20260711T105905Z.json` — thread `codex/raytsystem-bootstrap`,
«252 passed», coverage 81.77 %, gates G0–G10 with certificate class), 35 ADR with `Consequences`
and `Alternatives considered`, 73 test file (809 KB) with policy tests/guard/crash-recovery,
chain of schematic versions 27→151. What weakens the picture: all 35 ADR dated three days
(07-10…07-12), benchmark published **no results**, and the author writes about himself on his website
«I'm not a programmer» — code is agent-generated under his control. Therefore the weight of the evidence
is moved to «there is a test/artifact», and not «the author has been exploiting this for years».

**Field evidence (issues 07-17…07-24, independent operators) — most valuable:** ingest
is quadratic («~4 s on an empty ledger → ~344 s when ~590 sources», 1 045 358 reads per
operation); code graph crashes entirely on empty `__init__.py` and **does not name the file**; Windows
breaks on unconditional `import resource`. No maintainer replies, PR's hanging → like **upstream**
the project is not supported, there is nothing to vendor; Let's take the mechanics.

**Pros:** policy as data with form validator next to it; preflight — edited hash entry
(`operation_key`, absolute path not saved) and `CHECKPOINTED_FOR_RESUME` + exact command
instead of false «success»; **one** `CheckpointGuard` for CLI and pre-commit, and the test asserts that
hook calls the same command; politics simulator calls **the same pure function**, that runtime gate;
docs-in-the-same-change-set like DoD + coverage-gate by **alive** contracts («cannot pass by
editing the coverage page alone»); possibility matrix with proof boundary («A visible UI
section or CLI group is not proof that its external runtime is enabled»); test, assertive
**instruction layer shape** (`AGENTS.md ≤65` lines, `SKILL.md ≤150`, required sections,
prohibit duplication of canon in bootstrap, pair golden+adversarial for each skill).
**Cons:** stack is not portable (uv/pyproject/pydantic/React); catalog snapshot of circuit diagrams for each
version accumulates dead contracts (15 remote domain schemas live in v1.2.0–v1.4.0);
docs-coarse gate (credit is given to any file under `website/docs/`); strict revalidation has
measured price O(N²); fail-closed without the name of the culprit - a real defect UX.

**Taken from:** nothing has been implemented yet - verdicts on 19 techniques and a map of borrowings are in
/research/09-rayt-adoption-map.md`; raw materials - `findings/rayt-deep-2026-07-25.md`.
Of these **9 wound up by phase P8** plan (D41 — separate plan has been canceled so as not to
produce interplane synchronization): phase closure report with certificate class
(synthetic/real/`baseline_pending`), `Consequences` in D-records, `CHECKPOINTED`-failure with command,
docs-impact gate, capability matrix, CI-hygiene + verify-tag, `assert_safe_replace_target` in
`core/io.py`, delta k `validate.sh` and `skiller eval`. The remaining 10 (role registry review as
data, preflight delegations, provenance records, register of contracts, coverage for the living
contracts, graph obsolescence invariant) — in `roadmap.md` of the same plan, they drag on after the fact.

### Artifex supervisor references — reference/adapt, no runtime dependency

The plan uses only design patterns and tests them
own stdlib-prototype. First-party sources, rechecked 2026-08-03:

- OpenAI Codex: <https://learn.chatgpt.com/docs/agent-configuration/subagents> and
  <https://developers.openai.com/blog/run-long-horizon-tasks-with-codex> — separate worker
  contexts, price multi-agent in shared tokens and long-horizon loop/status discipline.
- Anthropic Claude Code: <https://code.claude.com/docs/en/sub-agents> and
  <https://code.claude.com/docs/en/cli-reference> — isolated subagent context, bounded headless
  output/schema/turn/budget/permission controls. Exact installed envelope is not output from docs:
  measures it P0.3.
- Temporal: <https://docs.temporal.io/workflow-definition> and
  <https://docs.temporal.io/activities> — deterministic workflow/activity boundary and
  idempotent retry patterns; code/engine does not connect.
- SQLite: <https://sqlite.org/wal.html> — durability/checkpoint principles; SQLite does not become
  SSOT or new runtime dependency prototype.
- RunMaestro/Maestro: <https://github.com/RunMaestro/Maestro> — fresh sessions, filesystem
  playbooks, headless JSONL, attention/backpressure and cost visibility; AGPL-code is not portable.
- Superset: <https://github.com/superset-sh/superset>,
  <https://docs.superset.sh/workspaces>, <https://docs.superset.sh/agent-integration> and
  <https://docs.superset.sh/automations> — worktree ownership, persistent identity, attention and
  at-least-once dispatch; ELv2-code/stack is not migrated.

Verdicts and limits of proof lie in
,
`findings/02-reference-products-2026-08-03.md` and
`findings/04-p0-design-verification-2026-08-03.md`.

## How it became part of the architecture

- Subagent Canon (spec, Volt, vijay) → **agent-packs** with canonical `description`+`<example>`.
- Per-type templating (vijay `team-configurator`, wshobson) → **skiller `profiles/` + detector in
  `core/` + deterministic pack delivery** (`harness agent-packs`, `maind sync` provider).
- Model-tiers (wshobson) → `profile.model_tiers` → `MODEL_*`-placeholders.
- Router/self-learning/skill-rules (Rio, session-hooks, itgoyo) → **deferred** —
  implement based on the measured problem, not speculatively.
- Eval skills (anthropics `skill-creator` + superpowers `writing-skills`) → **`skiller eval` +
  format `evals/`** (behavioral testing: evals/pressure/triggers, with-skill vs baseline).
  Composite-provenance (several sources in one skill) → **`upstream.json strategy=merge`**
  (`origins[]` base+supplement, manual agent-merge). Supply-chain-scan/bootstrap/hook-profiles (ECC,
  superpowers) → **deferred** — see plan.

## Instruction-carrier weight policy (2026-08-07)

## Provider Stop adapters (2026-09-10)

### Verification instruction layers (2026-09-16)

For audit instruction layers checked:
[OpenAI model guidance](https://developers.openai.com/api/docs/guides/latest-model#instruction-following),
[AGENTS.md discovery](https://learn.chatgpt.com/docs/agent-configuration/agents-md),
[skills](https://learn.chatgpt.com/docs/build-skills),
[Codex Stop hooks](https://learn.chatgpt.com/docs/hooks#stop),
[Claude Code memory](https://code.claude.com/docs/en/memory),
[skills](https://code.claude.com/docs/en/skills) and [Stop hooks](https://code.claude.com/docs/en/hooks#stop).
They justify progressive disclosure and the difference between instructions, task state
and actual hook continuation. Perplexity was used for two exploratory syntheses;
findings are verified against open primary pages. No new policy was introduced by this study.

### Cursor models {#cursor-models}

Hand-verified class pins for Task routing (freeze 2026-09-17, `agent --list-models` @
`2026.09.15-d2fe57e`): `economy=composer-2.5-fast`, `implementation=composer-2.5`,
`frontier=claude-opus-5-thinking-high`. Inventory-only: `gpt-5.6-sol-medium`, `auto`
(`never-substitute-fixed-frontier`). Bare `composer` and `gpt-5.6-sol` **missing** in the directory.
SSOT: `packages/task/configs/command-routing.json` → generated
[Provider model roles](/task/reference/provider-model-roles).

### Initial Attestation

- [OpenAI Codex Hooks](https://developers.openai.com/codex/hooks): documented `Stop` payload
  includes `turn_id`, `stop_hook_active` and `last_assistant_message`; a `decision: "block"`
  requests continuation. The adapter remains opt-in and only translates the Task verdict.
- [Claude Code hooks](https://code.claude.com/docs/en/hooks): documented `Stop` receives the
  final assistant message and supports blocking continuation, with an eight-consecutive-block
  override. No provider-specific behavior becomes Task policy.

- <https://docs.anthropic.com/en/docs/claude-code/memory> and
  <https://docs.github.com/en/copilot/tutorials/optimize-ai-usage> informed the focused-carrier
  guidance recorded in /findings/14-*`.
- The fewer-than-500-lines vendor orientation is printed as an independent number; it never raises
  or replaces the measured environment cap.

### Coding-agent orchestration comparison — reference (2026-10-05)

**What:** the owner-requested research packet in `orch/` compares extending the existing
Task/Harness/Artifex execution path with an external
[AWS Labs CAO](https://github.com/awslabs/cli-agent-orchestrator) Python-workflow backend.
It preserves the original Perplexity dialogue, exact queries and returned answers,
primary-source pins, two separate audits, a portable integration proposal and pilot gates.

**Evidence:** CAO main `c31dc281ec1f215cef898c2ed919a0ce507afd08` and GitHub v2.5.1 were
reviewed separately from PyPI 2.5.0. Existing Task context/scout/unit suites passed
(56 tests), as did command-projection and provider-instructions-reference checks.
Current [Claude headless](https://code.claude.com/docs/en/headless),
[Codex SDK](https://learn.chatgpt.com/docs/codex-sdk) and
[Grok scripting](https://docs.x.ai/build/cli/headless-scripting) document structured
native interfaces; [Vercel HarnessAgent](https://ai-sdk.dev/docs/ai-sdk-harnesses/overview)
is an experimental additional option, not merely a direct model API.

**Pros/cons:** CAO offers visible native terminal sessions and existing workflow machinery,
but TUI compatibility and replay of external Git/Task effects require a concrete pilot.
An own runner can reuse current JSON context, routing and units and consume native streams,
but would own multi-provider compatibility and recovery. Vercel/Pydantic remain references
with distinct runtime, sandbox, authentication and maturity boundaries.

**Verdict/taken:** CAO is a conditional first pilot candidate, not an adopted dependency.
Task/Skiller remain canonical and the engine boundary is proposed as replaceable.
This research made no runtime, schema, delivery, release or migration policy changes.
Concurrent Task edits are recorded separately; test results describe their execution time.
No paid agent runs were performed; reliability, subscription entitlement and savings remain unmeasured.
Prior code-review-graph and style-skill skip decisions are preserved. Detailed evidence:
`orch/research/sources.md`, `orch/research/source-index.json` and
`orch/research/local-checks.json`.

**Role-decomposition follow-up (2026-10-05):** `orch/task-role-decomposition.md`
analyses separating Task data/lifecycle from execution, review and skill delivery.
Local context, scout, actor/receipt and Harness launch boundaries were inspected.
[Claude subagent configuration](https://code.claude.com/docs/en/sub-agents),
[Codex skill configuration](https://learn.chatgpt.com/docs/build-skills) and
[Grok extension discovery](https://docs.x.ai/build/features/skills-plugins-marketplaces)
were checked to distinguish discovery, preloading, invocation and actual access.
The proposed migration preserves acceptance requirements and canonical content;
it is a design artifact, with no runtime changes or measured savings claim.
