# Development with Claude Code + swissknifeman

For the first task and the choice between direct work and Task start with [short route](./getting-started).
Below is a detailed scenario Claude Code for work that needs a plan; it is not required for
local reversible edits. Teams `planner` are triggered by an explicit call.

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
onboarding  /planner:design /planner:dev     verify-     release-
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
| **Plan** | `/planner:design` · skill `task-brief-template` · `complex-task-orchestrator` | decompose into **vertical slices** with risk and DoD; plan - in `.claude/plans/<task>.md` (durable, primary source) |
| **Execution** | `/planner:dev` · dev-loop (agent-pack) | slice → impl → tests-to-green → risk-adaptive review-gate |
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

## 4. Task management - plugin `planner`

Plugin `planner` — **default-on in each project** (connect-channel). Does not incur resident tax
(command descriptions are not injected into every request). That thin face above agent-packs/workflow: each
command **kicks the model + reasoning effort + profile workflow**, interrupting the session settings - to
do not switch manually.

| Command | Pinits | For what |
|:--|:--|:--|
| `/planner:design` | Opus / high | design → detailed technical specification/architecture |
| `/planner:dev` | Opus / high + dev-loop | development: vertical slices, risk-adaptive review-gate |
| `/planner:review` | high effort, risk-adaptive | code review |
| `/planner:research` | fan-out | research (breadth-first) |
| `/planner:fix` | — | spot bug fix |

**How phase is transferred to phase.** `/planner:dev` is planning on Opus, cuts into slices (`model→service→
controller→test`, everyone at risk `LOW/MED/HIGH`), and if installed agent-pack — drives them through
`*-dev-loop.js` (passes slices as `args.slices`). No pack - sequentially, one slice at a time.
Fan-out on coding **not** is used (≈15× tokens; justified only on research). Text that
`/planner:dev` suggests when moving to the next phase - this is **brief** from section 3: do it
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
| **Model routing** | to ~75% | Haiku (reconnaissance/routine) · Sonnet (default) · Opus (architecture/debug). Via `/model` or `/planner:*` |
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
{bin,lib,commands,configs}/**`, root `bin/**`/`install.sh`/`scripts/*.{sh,py}`)
or edits its interface paths (`bin`/`commands`/`configs`/`install.sh`), without editing docks
**of the same package** (`packages/<pkg>/docs/**`; y `planner` — second legal home `docs/planner/**`;
root - `docs/*.md`) in the same range. Bypass - commit trailer `Docs-Not-Needed: <reason>`
(reason is printed, an empty value is not considered bypass).
Measured frequency (research/24-P8.4-refine-2026-07-27.md` §1–§2,
tree `cd93dbc8`): **8 of 12** PR, **11 of 41** commit. Coverage Boundary: Gate **does NOT catch**
changing the behavior of an existing module `lib/**`/`scripts/*.{sh,py}` without new
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

**Managed blocks (`scripts/sync-managed-blocks.py`, step `managed-blocks` in job `hygiene`).** A canonical text is marked `<!-- export:begin <anchor> -->` …
`<!-- export:end <anchor> -->` in its owner file; the target holds a generated copy between
`<!-- managed:begin id=<id> source=<path>#<anchor> sha256=<hex> -->` and `<!-- managed:end id=<id> -->`.
Blocks are listed in `configs/managed-blocks.json`. `--check` prints `DRIFT`/`MISSING <id>` and exits 1;
`--write` regenerates only the text between the managed markers (the block itself is inserted by hand once).
Never edit a managed block directly — edit the source and run `--write`.

**Partner commands.** A module imports only itself and `aicore`. When it needs data or a service of another module it calls
the partner's public command with JSON output, found by `aicore.util.partners` (`SKM_<NAME>_BIN`, then `SKM_<NAME>_ROOT/bin/<name>`,
then `PATH`; for planner `PLANNER_PLAN_PY` or `PLANNER_ROOT`). A module routed by the umbrella (`swissknifeman <id>`, the project
launcher) gets these roots of every discovered module (names from `partner_env` of `configs/umbrella.json`, else
`SKM_<ID>_ROOT`; a variable already set wins), so a bridge it starts finds its partners. A missing partner is `PARTNER_UNAVAILABLE` on stderr and the command
degrades; a test that needs a partner is skipped when none is found. `bash scripts/test-integration.sh` runs the tests of
`harness` (and, with `--with-tools`, of the tools `analyst` and `maind`) with every partner wired from the hub layout, in a
temporary `HOME`, so those tests run instead of being skipped. `maind` and `analyst` are auxiliary tools outside the core
verification (`standalone.tools` in `configs/ecosystem-units.json`): `standalone --baseline` and the integration run skip them
unless `--with-tools` is given, and CI tests them in a separate job that never blocks the core. There is no `core/` folder any more; code that imported it imports `aicore`.

**Which tests to run.** Develop one module, test that module: `python3 scripts/affected-tests.py --run` (fast tier, `dev.test`
of the touched units and of the bridges that require them; `--tier full` adds `dev.validate`; `--base REF` takes the changed paths from a
diff; without `--run` it only prints the commands). A change of the foundation (`aicore`) affects every unit, a change of any other
module affects only itself and its bridges: no module requires another one, so their tests never need to run for each other. A *tool*
(`standalone.tools`, now `analyst` and `maind`) is tested only when its own files change, because it only reads data (and maind writes
it) and is not part of the core; its tests run when the tool itself is developed (`bash packages/<tool>/scripts/test.sh`). The full pass of every non-tool unit
(`--tier all --run`, plus `scripts/test-integration.sh`) is for the end of a phase or a release, not for each item; the quick pass runs
for each item. Hub checks finish before unit jobs; units run in descending order of their last measured duration.
`--fail-fast` stops submitting jobs after the first failure and marks unstarted commands `[skipped]`; running jobs finish.
In `full`/`all`, each unit runs test then validate. Validate gets `SKM_VALIDATE_SKIP_TESTS=1` only after that unit's full
test ran (or was reused as green); a failed test still fails the invocation. Focused tests never permit this skip.
Fast can select explicit test-file subsets for known planner/orch test-only changes; unknown helpers, runners, product
inputs and dependency mappings fall back to full suites, retaining the owner and dependent-unit closure. Mixed changes
combine obligations; renames include both owners, and `--base` also includes untracked files. `--json` explains the
profiles, inputs, context, per-unit obligation and requested/effective jobs. Nested runners divide `SKM_TEST_JOBS`.

Green receipts are bound to content, Python, tools, configuration and execution environment; changed inputs during a
command prevent reusable green. `--tier all` never uses the general green cache: reuse requires a safe `SKM_CHECK_RUN`
(`A-Za-z0-9`, then letters, digits, `_` or `-`) and is confined to that conductor run. Manual/release runs without that
variable stay full; `--no-cache` disables all reuse. Receipts and duration data are atomically merged in the git
directory, and run receipts older than 14 days are pruned when a run cache is written. Planner's `scripts/test.sh`
discovers the engine once; `-p PATTERN` selects matching test files for a focused check.

**Measuring the runners.** `python3 scripts/bench-checks.py --before REV [--pairs N] [--warm] [--commands-file FILE] [--out FILE]`
times the same commands on `REV` (a detached `git worktree` in `$TMPDIR/skm-bench-<pid>`, removed in `finally`) and on the
current tree, in 2 (at most 3) before/after pairs that alternate which side runs first. The default workload is one cold
`python3 scripts/affected-tests.py --run --tier all --no-cache` per side and pair: it already contains the orch, planner and
validate suites, so those are not run again. `--warm` adds warm scheduling and warm result reuse (the same tier twice in one
`SKM_CHECK_RUN`) as results of their own; a `diagnostic: true` command of `--commands-file` is timed but never part of the
total. Both sides get the same Python, `SKM_TEST_JOBS` and their own partner roots; a non-zero exit is recorded, not raised
(an error of the bench is exit 2: `BENCH_REV_INVALID`, `BENCH_PAIRS_INVALID`, `BENCH_COMMANDS_INVALID`,
`BENCH_WORKTREE_FAILED`). The document `urn:swissknifeman:hub:bench-checks:v1`
(`configs/schemas/bench-checks.schema.json`, default `.swissknifeman/orch/reports/p2-bench.json`) holds per-pair timings,
`ratio` (after/before by command id), `total.ratio` against the target 2/3, `loadavg` and `cpu_count` (compare ratios, not
seconds: the machine load moves them), the logical workload of each side (`affected-tests.py --json`) and a case census
(`SKM_PAR_UNITTEST_REPORT=<dir>/report-{pid}.json`, one file per runner): case ids by context, executed, skipped, retries and
invocations, equal or not between the sides; a runner that cannot write the report is "not comparable", never guessed.
The base of P2 is the parent of the first `Plan-Ref: P2.1` commit of the plan.

For the default workload the bench also takes an **execution census** (`--no-census` skips it, `--census` asks for it with a
commands file): after the timing pairs it runs the workload once more on each side with an observer
(`usercustomize.py` in an isolated `PYTHONUSERBASE`, so it survives `test.sh` replacing `PYTHONPATH`) that records every test
that really ran, with outcome, skip reason, subtest failures and context, into per-process ledgers; the timings of these two
runs never enter a ratio. Before the observed runs the observer is shown to be transparent (same unittest result with and
without it) and active in the plain and the `par_unittest` driver of both trees. A case that ran on one side only must be
explained by the source (`added: new method`, `removed: method gone`); a method that merely vanished from the source is an observation, never proof that its assertion is still run, so a removed case keeps the verdict unknown until an explicit mapping (`{"ctx|key": {"replacement": ..., "reason": ...}}`) names a replacement that ran and passed; an unknown primary outcome (the observer could not read the result) is unknown too; a missing start/end marker, a test unit with no observed
test or an unreadable ledger is *unknown*, never zero or equal. The whole default measurement is at most six workload
executions (two pairs plus the two observations; `BENCH_BUDGET_EXCEEDED` otherwise). The timing cache of `affected-tests` is put
back before every cold leg and at the end, and the source identity of the current tree must not move during the run.
**Recovery** (`--recovery-evidence FILE`, after a producer crash or a census that could not be completed): no timing leg is
run. The four recorded legs of FILE (found by content: `side`/`seconds`/`exit` rows, or `before`/`after` lists with `exits`) are
reused only while the base revision, Python, jobs, the workload and the *relevant inputs* (`relevant_inputs: {path: sha256}`,
or the recorded source identity of the timed candidate) still match; a missing proof is `valid: null`, a mismatch `false`, and
either leaves `target_met` `null`. Missing load averages stay empty (`loadavg_reason`). At most two new observation workloads
are taken (before, then after), only after a workload-free **preflight** on tiny fixtures (transparent plain driver, replaced
`PYTHONPATH`, a `sys.executable` child, skip/subtest/expected-failure/import-failure outcomes, real `par_unittest` `--worker`
processes over two modules in both trees, a lossless surrogate checkpoint). Paths handed to children are always absolute (the output may be given relative to the project). A failed preflight with no admitted
observation may run again; the failed receipt is kept in `preflight_history`. Each attempt is written to
`<out>.recovery/attempts.json` before it starts, so the cap survives corrections; the first incomplete observation stops the
second; raw ledgers stay under `<out>.recovery/ledger-<side>/`; a later invocation recomputes from them and runs nothing. Two
activation channels are used together (an isolated `PYTHONUSERBASE` and a `python3` shim around the same absolute interpreter
with `sitecustomize`); the observer never wraps twice. JSON is written ASCII-escaped, so a path with undecodable bytes is kept.

`result.target_met` is `null` when the timings are not valid and comparable (failed or timed-out runs, a different logical
workload, a moving source) or when the ratio is within 2/3 but the census is not conserved; `false` for a valid ratio above
exactly 2/3; `true` only for a valid ratio at or below 2/3 with a conserved census. `python3 scripts/bench-census.py gate
BENCH.json` re-derives that verdict from the document alone and fails if the document claims more than its own evidence shows.

**Bridges.** A package core stays pure: it never names other repository packages. All knowledge
about a partner lives in a bridge, a unit of the hub in `bridges/<id>/` (`unit.json` of kind `bridge`), which talks to
its partners through their public CLI/JSON and finds them by environment variable or command on `PATH`, never by a
neighbouring folder. The planner finds bridges through the `bridges.roots` setting (`.swissknifeman/config.toml` of this
repository sets `["bridges"]`); list them with `python3 packages/planner/scripts/plan.py bridge list`
(`planner-orch`: verbs `brief`, `register`, `register-review`, `commit`, `launch`; `orch-skiller`; `orch-harness`).
Run the tests of every bridge with `bash scripts/test-bridges.sh` (it wires the partners from the hub layout, uses a temporary `HOME` and turns event delivery off). A missing partner is `BRIDGE_PARTNER_UNAVAILABLE` (exit 3) and the conformance tests are skipped; set the variable of the partner (`PLANNER_PLAN_PY`, `SKM_ORCH_ROOT`, `SKM_SKILLER_ROOT`, `SKM_HARNESS_ROOT`) to run them against another checkout. The end-to-end checks of the work-source cycle and the events are `scripts/e2e-work-source.sh` and `scripts/e2e-plan-events.sh`; run them in a sandbox (`scripts/dev-sandbox.sh`). The boundary check of `scripts/ecosystem-units.py`
and the planner and orch test suites enforce the rule.

Repair: list of violations `public-hygiene` — in Completion Notes closing item'ah, deletion
artifacts made of wood - a separate decision of the owner (not auto-editing the gate).

## CI matrix of modules

`scripts/ci-matrix.py` is the one source of the CI steps of every module and bridge; the workflow
`.github/workflows/modules.yml` and a developer's shell run the same steps
([ADR 0078](architecture/decisions/0078-installed-form-smoke-and-ci-matrix.md)). Units are read from
`packages/*/unit.json` and `bridges/*/unit.json`; nothing is listed by hand.

| Steps of a module | `lint`, `test`, `validate`, `standalone`, `cli-smoke`, `contracts`, `schema-compat`, `secrets` |
| --- | --- |
| Steps of a bridge | `test`, `contracts` |

```bash
python3 scripts/ci-matrix.py list                          # the matrix of units
python3 scripts/ci-matrix.py steps skiller                 # the steps of one unit
python3 scripts/ci-matrix.py run --unit planner --step test --step contracts
python3 scripts/ci-matrix.py run --all                     # every unit, tools excluded
python3 scripts/ci-matrix.py --check --strict              # the workflow covers the matrix
```

The tests of a module run once per invocation: after a green `test` step the `validate` step runs with
`SKM_VALIDATE_SKIP_TESTS=1` (the `validate.sh` of a module skips its test run; `--repeat-tests` turns this off), and
`standalone` runs the tests in its copy once and then `validate` the same way.

Each step runs with a throwaway `HOME` and `SKM_HOME` and prints `ok|fail|skip <unit> <step> <seconds>`; the exit code is
1 when a step failed. `modules.yml` builds its matrix from `list --json`, tests on Python 3.9 and 3.13, marks the tools
named by `standalone.tools` (`maind`, `analyst`) as `continue-on-error`, and has a `hub` job: `--check`,
`ecosystem-units.py check --strict`, golden, `scripts/test-*.py`, `scripts/smoke-installed.sh` and
`swissknifeman conformance engine`, the last two in a sandbox. `test.yml` and `validate.yml` no longer exist.

The documentation site is built from `docs/`: `cd docs && npm ci && npm run docs:build` (the `docs:sync` script first copies
`packages/<module>/docs` into `docs/<module>/`; those copies are ignored by git). `.github/workflows/docs.yml` runs the same
commands with `working-directory: docs`.

## Scripts-FAQ

**«Phase ended, he proposes `/task` with text - compact or a new session?»**
Associated next phase → `/compact` (cheaper, no re-briefing). Really unrelated work / want
blank slate → new session, but do `/task`-text as a self-contained brief. See section 3.

**«Ran into context in the middle of a phase».** `/compact` (don't wait for auto-compaction). If this was a change of topic -
`/clear` with a plan file.

**«Starting a new feature».** `/planner:design` → plan in `.claude/plans/` → `/clear` → `/planner:dev`.

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

Verification uses the planner, Harness, mAInd and Skiller validators, registry freshness and targeted
route/workflow/memory/retirement tests. Archived PLAN1 may warn about old removed reads; it remains
schema-valid historical data and is not rewritten by this reconciliation.

## Stable worktree (development of a big plan)

1. **Why a worktree.** The live checkout `~/projects/packages/swissknifeman` stays on `main`. Links in
   `~/.local/bin`, project launchers, marketplace paths and mAInd MCP point there: an uncommitted edit changes
   the tools of every connected project immediately. Develop in `~/projects/packages/swissknifeman-next` on
   a phase branch `stable/p<N>`. Both worktrees share git objects and branches, so promotion needs no fetch.
   Keep the live checkout unchanged until phase validation passes.

2. **Prepare and bind.** The owner or operator creates the worktree and makes it the project's primary binding:

   ```bash
   cd ~/projects/packages/swissknifeman
   scripts/dev-worktree.sh create --branch stable/p1
   cd ~/projects/packages/swissknifeman-next
   scripts/dev-worktree.sh bind
   scripts/dev-worktree.sh status
   ```

   `create` defaults to `--from main`, `--branch stable/p1` and a sibling `swissknifeman-next`; `--path DIR`
   changes the target. It refuses an existing path (`DEV_WORKTREE_EXISTS`) or branch (`DEV_WORKTREE_BRANCH_EXISTS`).
   `status [--json]` reports branch, HEAD, ahead/behind main, changed and untracked counts, workspace/project,
   primary binding and whether it points here. JSON marker and status boundaries are validated against schemas;
   the script-owned status schema is embedded in the script. The workspace CLI override
   `SKM_DEV_WORKTREE_WORKSPACE_CLI` exists only for isolated tests.
   `bind` runs one mutation:
   `workspace project rebind <project_id> --path <worktree> --preserve-paths --include-path <live> --json`.
   `unbind` runs the same command with `--path <live> --include-path <worktree>` to restore the live primary.
   Each command validates both checkout markers and includes both paths in one transaction, even if either path
   was initially unbound. All previous paths keep their order, including missing directories; `bound_at` and other
   projects are preserved. Repeating either command adds no duplicates. These commands change machine bindings;
   the owner or operator runs them, never an item executor. CLI failures give `DEV_WORKTREE_BIND_FAILED`.

3. **Execute through the worktree launcher.** Plans stay in the shared workspace. The launcher chooses this
   checkout while installed planner, conductor and bridges keep running from the stable live checkout:

   ```bash
   cd ~/projects/packages/swissknifeman-next
   python3 -I .swissknifeman/launcher.py orch conduct --project "$PWD" run --plan <PLAN> --items <ITEM>
   ```

   A launcher binding is PID-bound and does not bind conductor subprocesses. The bridge invokes planner with
   cwd equal to the project, so the primary binding must point to the worktree **before the first run**.
   A bare `plan.py` command in another checkout of the same workspace/project refuses with
   `CHECKOUT_BINDING_MISMATCH` before using source paths. Use that checkout's launcher, or rebind it.
   Commands through the live checkout's own launcher continue to resolve to that checkout.
   Test changed tools from the worktree; keep the installed execution tools stable until promotion.

4. **Promote a validated phase.** After phase validation, run:

   ```bash
   scripts/dev-worktree.sh promote-check --branch stable/p1
   ```

   It requires the live checkout to have `main` checked out (`DEV_WORKTREE_LIVE_NOT_MAIN`): another
   branch or a detached HEAD is refused even at the same commit as `main`. It also requires an existing
   branch (`DEV_WORKTREE_NO_BRANCH`), `main` to be its ancestor
   (`DEV_WORKTREE_NOT_FF`), no tracked changes in the live checkout (`DEV_WORKTREE_LIVE_DIRTY`) and a clean
   worktree including untracked files (`DEV_WORKTREE_DIRTY`). It prints the owner's commands:

   ```bash
   [ "$(git -C ~/projects/packages/swissknifeman symbolic-ref --quiet HEAD)" = refs/heads/main ] && git -C ~/projects/packages/swissknifeman merge --ff-only stable/p1
   swissknifeman doctor
   ```

   The printed merge explicitly targets the verified live checkout and checks again that it is on `main`.
   The script never merges, pushes, resets, cleans or removes a worktree. The operator promotes by fast-forward
   after green phase validation. Start the next phase in the worktree with a new branch from the promoted
   `main`, for example `git switch -c stable/p2 main`.

5. **Sandbox (permanent tool, PLAN3 D88).** `scripts/dev-sandbox.sh new [--name N] [--copy <project>]...`
   creates `${TMPDIR:-/tmp}/skm-sandbox-<N>` with its own `HOME`/XDG directories and copies of the projects
   (the originals are never modified) and prints its path. Use `run DIR -- <command>` to execute a command
   with that environment, `source DIR/env.sh` for an interactive shell, `list` to see sandboxes and
   `remove DIR` to delete one. `remove` deletes only a directory named `skm-sandbox-*` directly in `TMPDIR`
   with the `.skm-sandbox` marker. Provider CLIs (`claude`, `codex`, `grok`) are not logged in inside it.
   Run `harness instructions apply`, `skiller budget` and other HOME-dependent manual checks there.
   `scripts/e2e-module-skills.sh` uses a sandbox to check `skiller connect` and `skiller sync`.

6. **Golden cycle (permanent tool, PLAN3 D88).** `scripts/golden.py` pins behaviour across code moves:
   CLI fixtures (`tests/golden/cases.json`, `tests/golden/cli/*.txt`) run in a throwaway sandbox with paths,
   hashes and timestamps normalised; generated files have sha256 digests and generator freshness checks
   (`tests/golden/generation.json`). `golden.py list` shows cases; `golden.py check [--only ID,...]` compares
   them and prints a diff (exit 1 on differences).
   A case may set cwd using `{REPO}` or `{SANDBOX}`. Project-state readers such as `analyst status` run in
   `{SANDBOX}/projects`, an empty project, with an absolute launcher path under `{REPO}`: an isolated HOME
   alone does not isolate checkout state. Preserve local bootstrap skills if they make completeness checks
   fail; check the candidate in a clean tracked worktree including any uncommitted candidate changes.
   At the start of each phase from `main`, check the relevant golden fixtures. A code move preserves them
   byte for byte. Record intended output changes with `golden.py capture --only ID,... --reason "..."`
   and an explanation; never recapture the whole set to hide unrelated regressions.

7. **Finish.** The owner or operator runs `scripts/dev-worktree.sh unbind`, changes to the live checkout,
   then removes the finished worktree with `git worktree remove ~/projects/packages/swissknifeman-next`.
   The sandbox and golden tools stay available.

### Module checks

`packages/aicore/scripts/test.sh` and `packages/skiller/scripts/test.sh` accept no arguments
or a single `-v`. Unsupported arguments exit 2 before Python starts. For a specific test,
use an explicit unittest module/file selector with the module's isolated environment;
these two shell entry points do not implement `-p`.

Every `packages/<id>/` folder is a module described by its `unit.json`
([architecture](architecture/index.md)). `scripts/ecosystem-units.py` guards that:

- `check [--strict] [--json]` checks manifests, ownership, schema identifiers and module boundaries.
  The baseline is empty and CI runs `check --strict`, so any violation fails; cross-module imports or
  code paths are forbidden, and `path_allow` holds only data with a reason.
- `baseline --update` recomputes the baseline and prints differences. Commit it only with the reason;
  it never hides a newly introduced violation.
- `render [--check]` generates `docs/architecture/ownership.md` from `configs/ecosystem-units.json` and
  manifests; `--check` fails on drift.
- `standalone <id>... | --all | --baseline [--update-baseline]` tests modules in copies with a stand-in
  for `aicore` and isolated HOME; the CI `standalone` job runs the recorded passing baseline.
- `list [--json]` reports module kind, version, destination, stability and requirements.

Tests live in `scripts/test-ecosystem-units.py`; the hygiene workflow checks boundaries and `render --check`.
