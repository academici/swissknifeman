# Development with Claude Code + swissknifeman

For the first task and the choice between direct work and Task start with [short route](./getting-started).
Below is a detailed scenario Claude Code for work that needs a plan; it is not required for
local reversible edits. Teams `task` are triggered by an explicit call.

One operational runbook: **how to actually conduct the development process** with Claude Code, when the project
connected to the ecosystem academici. Not «what is installed», a «how to use it day after day» —
plan phases, sessions and `/compact`, tasks, memory, graph, roles, token-levers, verification.

This **back-connector**: it connects subsystems and gives solutions-to-the-situation, and sends for depth
to profile docks ([token-budget](/skiller/guide/budget), [memory](/maind/guide/memory),
[graph](/maind/guide/graph), [toolchain](/skiller/workflows/)). She doesn't duplicate them
tries - repo rule «single source of truth > copies».

> Read from top to bottom. If you need one answer, see the section [Scripts](#scripts-faq) at the end.

## 0. Process Map

```
setup ──▶ PLAN ──▶ EXECUTION ──▶ CHECK ──▶ RELEASE
  │        │           │             │           │
onboarding  /task:design /task:dev     verify-     release-
skills+    task-brief-  dev-loop +    claims +    discipline
MCP+memory template     review-gate   analyze     (validate→PR)
+graph
  ▲ lever: CORE-skills   ▲ compact/    ▲ Haiku↔    ▲ RAG-       ▲ CHANGELOG
    permissions            new session   Opus       stairs      + semver
```

Each step has its own **token-lever** (section 6). The main principle is below.

## 1. Thinking model: sessions are disposable

Knowledge lives **outside the dialog** — in the plan-file, in the docks, in memory mAInd and in native memory
Claude Code. A session is a working surface, not a storage. Here's the whole process:

- Significant decision - **wrote down** (memory/plan/doc), do not keep it only in the chat history.
- The context has grown - **compressed or started again** (section 3), without fear of losing: durable already outside the session.
- Big task - **decomposed into phases**, you make each one from a written brief.

Everything else in this runbook is a consequence of this principle.

## 2. Task life cycle

| Step | Command / tool | What's going on |
|:--|:--|:--|
| **Onboarding** | `swissknifeman setup <project>` | skills (CORE) + permissions + MCP + memory + graph with one command (→ `maind onboard`). Details: [ecosystem-integration](/maind/) |
| **Plan** | `/task:design` · skill `task-brief-template` · `complex-task-orchestrator` | decompose into **vertical slices** with risk and DoD; plan - in `.claude/plans/<task>.md` (durable, primary source) |
| **Execution** | `/task:dev` · dev-loop (agent-pack) | slice → impl → tests-to-green → risk-adaptive review-gate |
| **Verification** | `verify-claims` · `decision-verification` · `cross-layer-change-checklist` · `maind analyze` | facts - via RAG; affected layers - according to the checklist; post-run analysis of the run |
| **Release** | skill `release-discipline` | `validate.sh` → `skiller registry` → `CHANGELOG [Unreleased]` → PR |

Everything except `swissknifeman setup`, — inside Claude Code. `task-brief-template`,
`complex-task-orchestrator`, `release-discipline` are distributed by skills (on-trigger, non-resident).

## 3. Sessions, context and phases ★

The most common practical question: **plan phase ended - `/compact` or a new session?**
Canon (verified from official. docks Claude Code — `memory`, `checkpointing`, `prompt-caching`):

### Pattern Plan → Clear → Execute

A major task shared in the session: **plan** write to file (`.claude/plans/<task>.md`) → `/clear` →
**execution** with only the plan loaded. Intermediate planning attempts do not fit into context
execution. Command Templates `/plan`/`/execute` — in skill `context-economy` (snippets).

### `/compact` vs new session

| Situation | Action | Why |
|:--|:--|:--|
| **Phase boundary of one plan** (related work) | **`/compact`** | Official recommendation. Summary ~20–30k instead ~150k, ≤1 slow speed, **without re-briefing**, stream is saved. `/compact Focus on <next phase>` directs the summary. Survive CLAUDE.md, MEMORY.md, summoned skills |
| **Mid-phase, hit the ceiling** | **`/compact`** | Clean handoff-there is no artifact yet - all the value «in flight». Don't wait for auto-compaction, press pause yourself |
| **The following work is NOT related / need a blank slate** | **new session** (+ brief `/task`) | Reset accumulated deadlocks. More expensive (complete cache miss on turn 1 + manual re-briefing), but the brief + recorded memory is insured against loss |
| **Entire multi-phase plan** | **never** `/compact` like «protocol handoff» through the entire plan | Summary of losses; but between adjacent phases compact — normal (see first line) |

**Key:** `/compact` cheaper when work continues (associated phases). A new session is justified,
whenever you want **forget** past (unrelated task, accumulated noise). Durability of knowledge
(memory/plan/doc) — is what allows **safe** start from scratch when necessary; but she
**not** makes a new session cheaper compact'and to continue.

`/compact` ≠ `/clear`: compact summarizes (saves solutions), clear — full reset (change topic).
Brief format for handoff — skill `session-handoff` (`.claude/handoffs/…`). Complete flow discipline -
[context-economy](/skiller/guide/budget).

## 4. Task management - plugin `task`

Plugin `task` — **default-on in each project** (connect-channel). Does not incur resident tax
(command descriptions are not injected into every request). That thin face above agent-packs/workflow: each
command **kicks the model + reasoning effort + profile workflow**, interrupting the session settings - to
do not switch manually.

| Command | Pinits | For what |
|:--|:--|:--|
| `/task:design` | Opus / high | design → detailed technical specification/architecture |
| `/task:dev` | Opus / high + dev-loop | development: vertical slices, risk-adaptive review-gate |
| `/task:review` | high effort, risk-adaptive | code review |
| `/task:research` | fan-out | research (breadth-first) |
| `/task:fix` | — | spot bug fix |

**How phase is transferred to phase.** `/task:dev` is planning on Opus, cuts into slices (`model→service→
controller→test`, everyone at risk `LOW/MED/HIGH`), and if installed agent-pack — drives them through
`*-dev-loop.js` (passes slices as `args.slices`). No pack - sequentially, one slice at a time.
Fan-out on coding **not** is used (≈15× tokens; justified only on research). Text that
`/task:dev` suggests when moving to the next phase - this is **brief** from section 3: do it
self-sufficient (target · DoD · files · solutions · dead ends · how to check).

## 5. Roles and agent-packs

**Agent-pack** — versionable artifact bundle Claude Code (subagents + workflow + hooks + settings +
docks), which is installed and updated in the project (`harness agent-packs render|upgrade`). Distributes data,
is not code. Two types:

- **Stack packs** (according to the project form): `backend-laravel`, `node-frontend`, `python-backend`, `dart-flutter`.
- **Role-packs** (cross-stack): `role-tech-lead`, `role-cto`, `role-founder`, `role-maintainer`.

**dev-loop** (`.claude/workflows/{prefix}-dev-loop.js`) rolls out vertical slices through
subagents (`slice-builder → test-writer → reviewer`) with **risk-adaptive review-gate**: trivial —
Haiku, impl — Sonnet, HIGH-risk review — Opus+xhigh. More details: [harness](/harness/),
[roles](./skiller/agent-framework/roles.md).

## 6. Token levers (staircase by ROI)

Full ladder with measured magnitudes - [budget.md](/skiller/guide/budget) and skill
`context-economy`. Here is the operational summary (which saves more):

| Lever | Magnitude | How |
|:--|:--|:--|
| **Trim CLAUDE.md** | to ~92% injectable | ≤200 lines, only what will surprise the experienced; path-scoped rules `.claude/rules/` |
| **Skill entry form** | is measured `skiller budget --first-turn` | short `description` + `when_to_use`; procedural bodies go to `context: fork`, a `paths:` do not count as automatic savings |
| **Model routing** | to ~75% | Haiku (reconnaissance/routine) · Sonnet (default) · Opus (architecture/debug). Via `/model` or `/task:*` |
| **Audit MCP** | ~10–20k/server resident | keep 1–2 for the task, the rest - CLI; unused disable |
| **Reconnaissance by subagents** | reads do not go to main-context | hard reading (cards, impact) — read-only to the subagent, summary only to top |
| **Selective-input** | 5–50× | function slice/class, `tail -n`/`grep`, `git diff` — «point, don't paste» |
| **Prompt caching** | 0.1× to prefix | pays for itself from ≥1 hits for TTL (5 min API / 1 hour subscription) |
| **Conciseness of output** | output ~4–5× more expensive input | skill `compact-responses`; output-style `lean` (`harness hooks --output-style lean`) |
| **EN-harness** | ~60–67% translated | static rules/agents - in English, human-facing — in Russian |

**PAO** (skill `php/pao`) — narrow but useful lever for **PHP-stack**: `composer require laravel/pao
--dev` forces PHPUnit/Pest/PHPStan/Rector give compact to agent JSON (~20 tokens instead
thousand), when tests are run inside the agent (detect `CLAUDE_CODE`/`CURSOR_AGENT`). Man in terminal
sees normal output. Requires PHP ≥ 8.3.

For the first move, measure both axes: `skiller budget --first-turn --target .` shows
design surface, and `--with-plugins` adds always-on price included marketplace
plugins. In the current model the signal becomes elevated above 16K and warning above 23K; incomplete
plugin metering prints reason (`broken` or `unparsed`), rather than zero cost.

## 7. Memory mAInd — demystification ★

Common confusion: «he writes some `.md`-file is agentmemory or base memory Claude?».
Answer: **TWO independent memory layers work**, they are not synchronized and solve different problems.

| Layer | Where is it stored? | Who writes | How to read |
|:--|:--|:--|:--|
| **agentmemory (mAInd)** | daemon :4111, binary KV in `maind/data/` | agent via MCP `maind_memory_store` or memory hook (`MODE=maind`) | **digest at the start** (`maind memory digest` prints the top 8 facts, **only private memory of this project** — `shared_max=0` default) + semantic `recall`/graph by `ns:<name>` on-demand for cross-project task |
| **native memory Claude Code** | `~/.claude/projects/<slug>/memory/*.md` + index `MEMORY.md` | **himself Claude Code** (basic feature, not our code) | loads the first 200 lines/25KB `MEMORY.md` at start; thematic `.md` — upon request |

**Why two.** agentmemory — **general** ecosystem memory (isolated by namespace, is visible linked
projects of the same group; fact lives in a single pool, provides isolation scope-marker `[[s:<scope>]]`). Native
memory Claude Code — **local** to your car, about this project, controlled by yourself Claude
(`autoMemoryEnabled`, defaulton with v2.1.59; is worried `/compact`; off `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`).
Both layers are cross-session durable and **partially duplicate** each other.

**Than recall is different from digest.** Digest is deterministic (list of recent facts scope when
start). `recall` — semantic search for a query (`maind memory recall "<topic>"`), with filter by
scope-token and grandfather in private + `ns:<tag>` + `global`.

**Recommendation for operator (verified RAG).** Hold **both** layer is **not** negative if divided
roles: native memory = local «working set» repo (solutions/gochi/conventions; auto, ≤200 lines),
agentmemory = cross-project/ecosystem/highly valuable (by scope, on-trigger). Real loss
tokens - not double storage, but **double re-injection**: the same fact in `MEMORY.md`, and in
digest mAInd. So - **do not duplicate** one fact in both layers (digest mAInd is already limited
top 8). Disable native (`autoMemoryEnabled:false` / `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`) — only
in a fully centralized single memory or regulated environment. Check each layer:

- agentmemory: `maind health --cwd` (round-trip write→recall→forget), `maind memory count` (how much
  facts on scope — see section 9), viewer `http://127.0.0.1:3113`.
- native: `/memory` (memory file browser Claude Code), `ls ~/.claude/projects/<slug>/memory/`.

Deeper: [memory (agent-memory)](/maind/guide/memory), [namespaces](/maind/guide/namespaces).

## 8. Graph mAInd — demystification ★

Second confusion: «the graph seems to be supposed to help with connections and save tokens, but the agent still climbs
for hundreds of files». Parsing - two different graphs + two features.

| Graph | What connects | Engine | Indexing |
|:--|:--|:--|:--|
| **maind-graph** | topology **between** projects (composer/npm/Brain/skills) | federation (graph per project + index) | `maind graph derive` from sources |
| **code graph (Serena)** | characters/files **inside** project | Serena (LSP, per-project MCP) | itself, on the fly through LSP |

Two features that explain «scanning hundreds of files»:

1. **Scan - manual.** Watcher'a/git hook/guard demon **no**. maind-the graph is reassembled only by
   `maind graph derive` / `maind sync --only graph` / `onboard`. Dependencies have changed
   (composer/npm), Brain-frontmatter or skills-lock → **himself** call `maind sync --only graph`.
   Otherwise the graph becomes obsolete. (Lightweight cron once a day/week is justified as insurance.)
2. **Reading - pull-model.** In context graph **is not injected**. The agent must **himself** call
   `maind_graph_query`/`neighbors`/`path`. Rules «first ask the Count» no by default - so
   agent and goes to `grep`. Skill `ecosystem-mcp` (is distributed to each connected project) now
   prompts **graph-first**: before wide `grep`/reading many files - first a graph or
   Serena `find_symbol`/`get_symbols_overview` (reads character by character, not the entire file → saves tokens).
   **Disclaimer:** graph may be outdated (scan manual) → if suspected `maind sync --only graph`
   or fallback to file search.

**Where are the real savings.** On **code** — Serena via LSP: `find_symbol`/`get_symbols_overview`/
`find_referencing_symbols` give the symbol/review instead of reading the entire file (more precisely `grep` when
refactoring). Works automatically, **if** in `.mcp.json` project has a server `serena` (him
provisioning `maind onboard`; no server - navigation by regular search). On **topologies** — maind-graph:
100 lines JSON about neighbors instead `grep` on many manifestos, but only with conscious challenge.

Deeper: [connection graph](/maind/guide/graph), [code graph (Serena)](/maind/guide/code-graph),
[how it all works](/maind/guide/how-it-works).

## 9. Performance measurement ★

«It seems to write, but whether it’s readable and whether it helps is unclear, there’s nothing to measure it with». What the answer is today:

| Question | Tool |
|:--|:--|
| Real cost of the first move | `skiller budget --first-turn [--with-plugins] --target .`; compare `total` and `session_total`, do not attribute the effect of changing the meter model to diet |
| Is memory really alive (not «idle») | `maind health --cwd` — round-trip write→recall→forget; `maind verify` — proof-of-life 3 planes (memory/graph/Serena), features «raised» from «really write» |
| How many facts are in the project memory | `maind memory count [--project <id>]` — by scope (private/ns/global) |
| Graph size and shape | `maind graph stats` — nodes/edges/types/components |
| **Whether the agent accessed memory/column per run** | `maind analyze` — after the session shows `memory: recall×N→M facts, store×K; graph: query×J→S neighbors` and highlights **«code graph was not used for heavy scanning»**, if there were a lot `Read`/`Grep`/`Glob` and 0 calls to the graph |
| Memory through the eyes | viewer `http://127.0.0.1:3113` |

`maind analyze` collects this from run-report (SessionEnd-hook writes `.claude/runs/<sid>.json` from
transcript) → verdict GREEN/ATTENTION/RED. Parse current run - command `/maind:analyze`.

**Honestly about limits.** Direct correlation «graph saved specific `grep`» no - there is only indirect
heuristic (heavy scanning + 0 column → signal). `recall` with 0 found many times - signal
«memory is empty or not at the address» (check scope/filling), and not proof of uselessness.

**Self-learning - outline and status.** Now learning loop **manual, with a person in the gate**: capture
(`run-report`) → parsing (`maind analyze`, experimental skill `session-observer` — weaknesses in
axes agents/skills/settings) → lesson → **person** will promote him in the skill/rule (`field-feedback-loop`
+ gates `skill-authoring`/`anti-drift`). Automatic **cross-project** outline (pattern detection
on many projects → confidence-scoring → auto-drafts `SKILL.md`) — designed
(`research/analyst-package-design.md`) and implemented by the package `analyst` (`digest`→`confidence`→`promote`):
gate — confidence + manual promo to false «lessons» were not included in the skills automatically.

## 10. RAG and verification

External facts (versions/API libraries, «still relevant», market, possibilities of someone else's service) — **not by
memory**, and through RAG before committing. staircase (skills `verify-claims`, `query-craft`, `mcp-advisor` —
all CORE):

```
context7 ──▶ perplexity-web ──▶ WebSearch
(accurate API   (flat-rate,        (last
 libraries)    token-cheap; fallback)
               push to the maximum)
```

- **`query-craft`** — how to ask: never a naked request for a library without a version+context
  («Laravel like X?» → «Laravel 11: X for 2025»).
- **`verify-claims`** — when/what to verify (repo-facts - reading the code; external - RAG).
- Formation of plan 100% stands on fresh data and ends footer'ohm «Verification» (which is checked ·
  unverified → **REPEAT PASS**, if the engine was unavailable).

Reliability `perplexity-web`: do not parallel (profile one), split a heavy request into narrow ones search
or escalate to `research`; lock/timeout → WebSearch+WebFetch/context7.

## 11. Monitoring and diagnostics

| What | Command |
|:--|:--|
| 4-project layer inventory (skills/MCP/agents/memory/graph in one request) | [control-surface](/control-surface) |
| Project connection to the hub | `maind health --cwd` (+ `--fix`) |
| Hub environment (demons/config) | `maind doctor`, `maind status` |
| Skill environment | `skiller doctor`, `skiller status` |
| Environment Claude Code (permissions/MCP/hooks) | `harness doctor` |
| All at once (fan-out) | `swissknifeman doctor` |

### Provider operations and rollback

Use the generated [provider support](./provider-support) page as the capability matrix. It is
provider-qualified: `native`, `adapted`, and `unsupported` are different states, and one green
provider never makes a missing or degraded peer green. Start with read-only evidence, then act
only on an explicit, authorized target:

```text
select provider and operation
→ help / plan / check / dry-run
→ inspect provider-qualified diagnostics
→ authorized apply or repair
→ read back and reconcile
→ roll back on a mismatch
```

Never put raw environment values, credentials, absolute host paths, or provider payloads in a diagnostic.

`plan`, `check`, and `--dry-run` are no-write operations. Apply or repair needs the exact managed
target, an accepted action digest or owner authority where the command requires it, ownership and
preimages/backups, readback, and an empty second reconcile. A mismatch remains non-green: restore
only declared owned preimages, then re-run the no-write check. Generated provider docs are
restored by their generator, not by editing the output. A release candidate is evidence only; it
does not authorize a tag, push, publication, fleet rollout, or provider repair.

**Gate docs-impact (CI, `.github/workflows/hygiene.yml`).** `scripts/docs-impact.py` stops
change-set, which enters/removes/renames the package surface file (`packages/<pkg>/
{bin,lib,commands,configs}/**`, `core/*.py`, root `bin/**`/`install.sh`/`scripts/*.{sh,py}`)
or edits its interface paths (`bin`/`commands`/`configs`/`install.sh`), without editing docks
**of the same package** (`packages/<pkg>/docs/**`; y `task` — second legal home `docs/task/**`;
root - `docs/*.md`) in the same range. Bypass - commit trailer `Docs-Not-Needed: <reason>`
(reason is printed, an empty value is not considered bypass).
Measured frequency (research/24-P8.4-refine-2026-07-27.md` §1–§2,
tree `cd93dbc8`): **8 of 12** PR, **11 of 41** commit. Coverage Boundary: Gate **does NOT catch**
changing the behavior of an existing module `lib/**`/`core/*.py`/`scripts/*.{sh,py}` without new
file and without editing the interface - this is a conscious narrowing (form «any surface editing» painted
100 % PR and would have filmed on the very first controversial evening), rather than full coverage.

**Gates CI-wood hygiene (`.github/workflows/hygiene.yml`, P8.6).** Two stdlib-script,
lists of rules - data:

- `scripts/public-hygiene.py` — fail-closed by **monitored** tree (`git ls-files`,
  content is not readable) for prohibited suffixes/names/directories: `.sqlite`/`.log`/`.pem`/
  `.key`/archives (`.zip`/`.tar`/`.tar.gz`/`.tgz`/`.rar`/`.7z`), `.env` (except `*.example`),
  `__pycache__`/`.venv`/`node_modules`. Each violation is a line `<path> — is prohibited by the rule
  «<reason>»`; step `public-hygiene` in job `hygiene`. Red on the current tree is a gate
  **reports**, repaired by a man (files are not deleted silently).
- `scripts/verify-tag.py <tag>` — tag `vX.Y.Z` must be **top released** header
  `## [X.Y.Z] - YYYY-MM-DD` in root `CHANGELOG.md` (umbrella version carrier - CHANGELOG, not
  `package.json`: there is no root, package versions do not carry tags). Step `verify-tag` in a separate job
  `release-tag` (`on: push: tags: ['v*']`) — red on the release tag stops publishing
  before the version diverges from the title.

**Managed blocks (`scripts/sync-managed-blocks.py`, step `managed-blocks` in job `hygiene` and `[7/7]` in
`packages/task/scripts/validate.sh`).** A canonical text is marked `<!-- export:begin <anchor> -->` …
`<!-- export:end <anchor> -->` in its owner file; the target holds a generated copy between
`<!-- managed:begin id=<id> source=<path>#<anchor> sha256=<hex> -->` and `<!-- managed:end id=<id> -->`.
Blocks are listed in `configs/managed-blocks.json`. `--check` prints `DRIFT`/`MISSING <id>` and exits 1;
`--write` regenerates only the text between the managed markers (the block itself is inserted by hand once).
Never edit a managed block directly — edit the source and run `--write`.

Repair: list of violations `public-hygiene` — in Completion Notes closing item'ah, deletion
artifacts made of wood - a separate decision of the owner (not auto-editing the gate).

## Scripts-FAQ

**«Phase ended, he proposes `/task` with text - compact or a new session?»**
Associated next phase → `/compact` (cheaper, no re-briefing). Really unrelated work / want
blank slate → new session, but do `/task`-text as a self-contained brief. See section 3.

**«Ran into context in the middle of a phase».** `/compact` (don't wait for auto-compaction). If this was a change of topic -
`/clear` with a plan file.

**«Starting a new feature».** `/task:design` → plan in `.claude/plans/` → `/clear` → `/task:dev`.

**«Analyzing someone else's audit/plan».** External verdicts to be checked via RAG (section 10), even if
«looks full». Call a crutch a crutch (`[POSSIBLE-DEFECT]`), should not be presented as a solution.

**«The agent crawls through hundreds of files, although there is a graph».** The graph scan may be out of date - `maind sync --only graph`.
For code navigation - is there `serena` in `.mcp.json` (otherwise Serena doesn't work). After run -
`maind analyze` will show whether the agent pulled the graph at all. See sections 8–9.

**«Graph is outdated».** `maind sync --only graph` (idempotent, rebuilds entirely).

**«Memory is empty on recall».** Check scope (`maind memory count`), is the demon alive (`maind health --cwd`),
is the pool saturated? (recall warns). Possibly written to native memory Claude, and not in agentmemory
(section 7).

---

_Depth by subsystem: [token-budget](/skiller/guide/budget) · [toolchain](/skiller/workflows/) ·
[semantics loop'ov](/skiller/guide/loop-semantics) · [memory](/maind/guide/memory) ·
[graph](/maind/guide/graph) · [control-surface](/control-surface)._

## Manual branch reconciliation

The 2026-10-05 reconciliation keeps `feat/plan-json-v3` as the working branch and compares main's
changes from their common ancestor. It changes working-tree bytes without merge, cherry-pick,
commits or branch movement. Generated projections are rebuilt from canonical sources.

JSON v3 remains the plan source of truth. Review is optional; an explicit `--reviewer` selects a
separate native read-only session, while checks and lifecycle use the existing `plan.py` verbs.
Memory compatibility accepts `fact` and at most 72-hour legacy records with trustworthy creation
time; Grok tools remain independent of mAInd connection health. Released notes and attestations
remain historical, and new v3 work stays under `[Unreleased]`.

Before promoting the branch, review the working diff, commit the agreed result, and choose the
GitHub integration separately. No main ref or remote is changed by this reconciliation.

The compared snapshots are feature `00750a57`, main `b0f63fd4`, common ancestor `b881696d`.
The main changes have these dispositions:

| Main change | V3 result |
|:--|:--|
| Published package/skill versions and 0.28.0/0.28.2/0.28.3 attestations | Retained exactly as release history; v3 changes remain unreleased |
| Provider diagnostic escaping, Grok payload normalization, Codex request observer, release-source delivery | Already present in the feature branch; retained |
| Temporary-memory policy | Retained; added bounded legacy/fact compatibility without unknown-age records |
| Cleanup of installed commit-copying hooks | Adapted as a retirement-only sync provisioner; no seed/feature-log APIs restored |
| Declared execution order | Already covered by v3 phase batches/frontier tests; no numeric-order heuristic added |
| Exact optional reviewer and effort/context selector | Adapted in `review_selection` and command projections, independent of JSON storage |
| Read-only role separation, bounded correction, systemic invariant model | Adapted in command/skill guidance and optional workflow slots |
| Mandatory risk-based review, Grok mAInd tool gate | Omitted according to the owner's decisions |
| Markdown acceptance runner, review packet/ACP jobs, source archives, old route/terminal receipts | Retired with v2; measured failures remain inputs to future JSON orchestration |
| Whole-plan-only close and old phase/audit findings reducers | Omitted; existing JSON lifecycle and `plan-close` semantics retained |
| Registry/command locks, manifests and documentation copies | Regenerated from v3 canonical sources; obsolete copied v2 pages removed |

Verification uses the Task, Harness, mAInd and Skiller validators, registry freshness and targeted
route/workflow/memory/retirement tests. Archived PLAN1 may warn about old removed reads; it remains
schema-valid historical data and is not rewritten by this reconciliation.
