# Decisions Ledger — which is accepted / rejected

Registry of agent framework solutions. **Audit Login**
([framework-audit](../workflows/framework-audit)): you submit Perplexity, so that he does NOT
re-offered something that had already been rejected/accepted. You can reject a decision - but only with a NEW
proof.

Columns: date · solution · verdict · rationale · where it landed.

## Architectural principles

| Date | Solution | Verdict | Rationale |
|---|---|---|---|
| 2026-06-23 | Template database home - **harness**; playbook — **skiller** | ✅ accept | harness already owns `.claude/`-environment; skiller — skills |
| 2026-06-23 | **Per-pack** versioning (1 pack = 1 semver + 1 CHANGELOG) | ✅ accept | easier than per-template; project pins one version |
| 2026-06-23 | **Agent-driven**, not Python/Mustache engine | ✅ accept | owner requirement; templates = real files + lock |
| 2026-06-23 | Versatility: **packs for the concern + general roles** | ✅ accept | back/front/fullstack = pack composition; the roles are the same |
| 2026-06-23 | lock = `.claude/agent-pack.lock.json` (not `.swissknife.json`) | ✅ accept | different owners; need a nested one per-file structure + sha |

## From the audit #1 (universal-framework)

| Date | Idea | Verdict | Rationale / where |
|---|---|---|---|
| 2026-06-23 | AI Skills Index in CLAUDE.md | ✅ absorb | already hub; expandable (Phase 1), boost-aware (`.ai/guidelines`) |
| 2026-06-23 | Agent generation engine (Mustache `.tpl`, `generate-agents`) | ❌ reject | against agent-driven; templates = real `.md` in the pack |
| 2026-06-23 | Profiles-inheritance `laravel→php-backend→base` (render) | ⏸ defer | as data (`extends`), is not a render engine |
| 2026-06-23 | `.swissknife.json` diagram (`shape`/`stacks`/`skills_map`) | ✅ absorb | data only (Phase 3) |
| 2026-06-23 | path-scoped rules `.claude/rules/` | ✅ absorb | **native** (official. docs/en/memory); Phase 3 |
| 2026-06-23 | spec-first gate (spec-writer) | ✅ absorb (opt.) | as opt. role-agent for large features, not global. gate; artifact `tech-spec.md` |
| 2026-06-23 | task-graph `tasks.json` (Task Master) | ⏸ defer | do not spawn layer; if necessary - on maind/agentmemory |
| 2026-06-23 | `skiller init` | ⏸ defer | collapse to existing `integrate` |
| 2026-06-23 | file-lock protocol (`touch {file}.lock`) | ❌ reject | fragile; replaced one-branch/worktree |
| 2026-06-23 | <500-char system prompts | ✅ absorb (guideline) | convention, not a hard limit |
| 2026-06-23 | Agent file numbering `01_`,`02_` for priority | ❌ reject | **verified**: on `/agents` has no effect |
| 2026-06-23 | `skiller validate-agents` | ✅ absorb | validator (data, not engine): names `skills:`, duplicates, scope tools (Phase 3) |
| 2026-06-23 | explore-subagent | ✅ absorb | yes (`Explore`); add seed as |
| 2026-06-23 | complexity scoring 1–10 | ❌ reject | ceremony; delegation threshold is qualitative |

## From the audit #2 (agent-teams + ponytail)

| Date | Idea | Verdict | Rationale / where |
|---|---|---|---|
| 2026-06-23 | `extends:`/`@include` agent inheritance; frontmatter `triggers/role/version/project_type` | ❌ reject | **REFUTED** official. docks - not native/made up; inheritance = build-time pack |
| 2026-06-23 | `.claude/rules/` (path-scoped) native | ✅ confirmed | official. docs/en/memory → take |
| 2026-06-23 | skill-enforcement hook (TeammateIdle, exit 2, grep transcript) | ❌ reject (as a hook) | fragile heuristic; «skill gate» closes deterministic name matching `skills:` in hub |
| 2026-06-23 | ponytail (YAGNI-ladder + over-engineering review) | ✅ absorb (discipline) | without external plugin; in reviewer-role + opt. `quality/lean-code` |
| 2026-06-23 | Agent Teams (Mesh, teammates) | ✅ accept v1 | experiment; CC ≥2.1.178; Phase 6; roles = teammates |

## From the audit #3 (workflow resilience / rate-limit, 2026-07-01)

| Date | Idea | Verdict | Rationale / where |
|---|---|---|---|
| 2026-07-01 | Honest statuses `green/deferred/infra-failed` (do not disguise infra as a defect) | ✅ accept | dev-loop.js ×4 + docks; P4 — first split CI-taxonomies «infra-flake vs code-deterministic» |
| 2026-07-01 | Fail-fast to terminal `agent()===null` + smaller batch (default 2) | ✅ accept | dev-loop.js; throttling itself will not pass from the transition to the next slice; big butch multiplies retry-surface |
| 2026-07-01 | Liveness via **external supervisor** (orchestrator report ~30 min + `PushNotification`; opt. GHA cron-watchdog) | ✅ accept | orchestrator.md + background-agents.md; main fuse, outside sandbox |
| 2026-07-01 | In-script wall-clock / agent-timeout (`withDeadline`/`setTimeout`) | ❌ reject (crutch) | `Date.now()`/`setTimeout` not available in sandbox/are unreliable, `agent()` not cancelable (no `AbortController`) → does not provide a warranty; hang → escalation to person |
| 2026-07-01 | Return marker text instead of strict outline on long returns | ✅ accept | dev-loop.js; StructuredOutput retry-cap (5) runtime interrupted the run - we go around, we don’t worry |
| 2026-07-01 | `perplexity-web` — bounded concurrency (not «sequential only») | ✅ accept | background-agents.md table; repo-docs `query-craft` already describe daemon v1.3.0 pools; incident 13-way fan-out just exceeded the limit |

## From the audit #4 (harness-agnostic, 2026-07-29)

| Date | Idea | Verdict | Rationale / where |
|---|---|---|---|
| 2026-07-29 | Canonical installation unit - plugin/pack, bucket - human category | ✅ accept | description of an already established (48 buckets, 10 packs, marketplace ~50 plugins), not a change - /§13 |
| 2026-07-29 | Root always-on context remains a short index | ✅ accept | number for the root price: `CLAUDE.md` 88 lines / 7 520 bytes (on `4647ad4b`, `wc -l -c CLAUDE.md`) vs previous 194/20 705 — ` Completion Notes |
| 2026-07-29 | Role templates are thin in knowledge, skills provide depth on demand | ✅ DONE | is fixed by canon; `roles.md` (self-load fallback skills in the body of the role) |
| 2026-07-29 | Spawn Policy/delegation - from budget context | ✅ accept | accepted, content and media - ` (declarative policy schema), here is only a link |
| 2026-07-29 | Each pack comes with verification-contracts and eval-fixtures | ⚠ partially DONE | SubagentStop review-gate (`hooks/review-gate.sh` + `REVIEW_GATE_CMD`) is in 4/10 packs (`backend-laravel`, `dart-flutter`, `node-frontend`, `python-backend`); honest agent `test-verifier` — only for `backend-laravel` (1/10); 6/10 packs (`laravel-package`, `_common`, `role-cto`, `role-founder`, `role-maintainer`, `role-tech-lead`) do not carry either one or the other - the gap is real, it is not closed by this entry |

## Verified facts Claude Code (official. documents, version of the fact - its own date)

| Fact | Verdict |
|---|---|
| `.claude/rules/` with `paths:` — auto-loading by paths | ✅ native (docs/en/memory, 2026-06-23) |
| Subagent `extends:`/`@include` inheritance | ❌ does not exist (2026-06-23) |
| Frontmatter `triggers/role/version/project_type` at the agent | ❌ does not exist (2026-06-23) |
| Agent file numbering → priority `/agents` | ❌ has no effect (2026-06-23) |
| `${CLAUDE_PROJECT_DIR}` / `${CLAUDE_PLUGIN_ROOT}` in hook commands | ✅ native (2026-06-23) |
| Agent Teams — experimental (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`), `teammateMode` default `in-process` with v2.1.179 (was `auto`), `iterm2`-mode with v2.1.186; command hook events: `TeammateIdle`/`TaskCreated`/`TaskCompleted`; teammates do not inherit `/model` Lida, effort leads are inherited from v2.1.186 in split-pane | ✅ confirmed `code.claude.com/docs/en/agent-teams` (2026-07-29) |
| Fields `skills`/`mcpServers` subagent definitions are NOT applied when it is run as teammate (loads skills/MCP from project settings/user as a normal session) | ⚠ limits the framework role model - caveat included in `roles.md`/`agent-teams.md`, `code.claude.com/docs/en/agent-teams` (2026-07-29) |
| Limits Agent-Tula: 200 subagents per session (`CLAUDE_CODE_MAX_SUBAGENTS_PER_SESSION`, v2.1.212+), 20 at the same time (`CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`, v2.1.217+), nesting depth 3 (v2.1.219) | ✅ `code.claude.com/docs/en/sub-agents` (2026-07-29) — separate ceiling from workflow-runtime below, do not mix |
| Workflow-runtime (`agent()` from `Workflow`): ~16 competitive, up to 1000 per run - in the limit Agent-tula does NOT count | ✅ repo-grounded (workflow tool description), tested against F17 (2026-07-29) |
| `skills:` subagent preload: the full body of the skill is injected into the context; unknown/disabled name - silent pass + entry in debug-log (no visible error) | ✅ `code.claude.com/docs/en/sub-agents` (2026-07-29) |
