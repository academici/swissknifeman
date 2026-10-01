# Bucket-audit — 2026-07 (P7.2, SKM-MASTER-002)

Snapshot «to»: run `skiller bucket-audit` on the live registry (206 skills / 45 buckets),
fixed as the basis for the content steps of the phase G (P7.3 monoliths →
thin-navigator, P7.4 dead-pass, P7.5 alias-mechanism). All numbers below are verbatim from
command output (not from memory), see [«How to reproduce»](#how-to-reproduce).

```
skiller bucket-audit --json   # since=30 (default)
```

Run date: 2026-07-02. Script software (`audit.py`) — P7.1, is already in working order
copies at the time of this run.

## Honesty usage-windows (read before verdicts)

**Real window: 30 days, and this is the entire available horizon.** `bucket-audit`
believes usage fan-out by `~/.swissknifeman/projects.json` (23 registered
project) → JSONL-session transcripts Claude Code. Empirically tested: run with
`--since 3650` (10 years) gives **the same** result as `--since 30` — 21
scanned project, identical verdicts. The reason is not «telemetry only
turned on», but the fact that there are physically no older logs: among the 334 session files there are 21
of the project, the oldest is dated 2026-06-02, the newest is 2026-07-02 (exactly 30 days
stories). So «30 day window» here = «the whole story that is», rather than truncation
artificial `--since`.

⚠ **[POSSIBLE-DEFECT] discrepancy with the problem statement.** Objective of this plan item
assumed «telemetry SCHEMA=2 enabled 2026-07-02 - window ~1 day». Verified
reading the code (repo-grounded, not an external fact): `SCHEMA=2` — is a separate format
run-report package hook `harness` (`packages/harness/configs/claude-code/hooks/run-report/_lib.py`,
`usage-trend.ndjson`), and its commit (`070e529`) is actually dated today. But
`bucket-audit.collect_usage` **does not read** this source - it uses much more
old mechanism (`analyze.py::agent_stats`, explicit calls Skill-tool in transcripts),
which was long before SCHEMA=2. In other words: the premise about «SCHEMA=2 → window ~1 day»
is not relevant usage-signal that really stands behind the verdicts of this
document - real window usage-signal bucket-audit wider (30 days = entire horizon
project), but the number itself «30» is essentially no different from «1 day»: it's still
too early to draw conclusions about the death of the skill (below why). **ESCALATION-REQUIRED**: if
someone's master plan was aimed precisely at reducing the audit to data SCHEMA=2
(`usage-trend.ndjson`) — this is a separate modification `audit.py` (was not included in P7.1
scope, is clearly recorded there «usage — fan-out by projects.json → transcripts»), not
made here; this does not affect the current run, except for the formulation of the reason
short window.

**Second, more important reason not to trust `dead` literally - structural, not about
window length.** `analyze.py` documents this directly: «skill loading is detected
ONLY by explicit Skill-tool-calls; native `skills:`-preload subagent and
auto-trigger plugin by description like Skill-call NOT visible → «DEAD» heuristic».
Empirical confirmation on this very run: CORE-skills (`context-economy`,
`anti-drift`, `compact-responses`, `mcp-advisor`, `verify-claims` — are distributed in
**each** connect-default project, see `configs/core-policy.json`) all five
show `loaded_count=0` and verdict `dead`, despite the fact that they are actually resident in
every request of those projects (otherwise CORE-policy did not work). So high
share `dead` (180 of 206 = 87%) — this is basically the blind spot of the detector
(auto-trigger/preload is not logged as explicit `Skill`-call), and not 180 really
unused skills.

**Practical conclusion**: verdict `dead` in this report read EXACTLY as
«not caught explicitly Skill-tool-call 30 days in advance (entire available horizon)» — not
«is proven dead». Action on it - **P7.4 (profile-excludes, reversible)**, and then
not before «≥2 weeks pro-usage data after telemetry appears» by phase spec;
this wave does not produce hard deletions anywhere.

## Summary in one line

Skills: **206**. Baketov: **45**. Projects scanned: **21** of 23
registered (2 without log directory). Overlap-pars: **2** (3 skill).

| Verdict | N | What is this |
|---|---|---|
| `dead` | 180 | 0 explicit downloads outside the window - see honesty above, action = P7.4 (exclude, not deleting) |
| `keep` | 13 | really caught Skill-tool in the window |
| `thin` | 8 | monolith body (↻tier1 ≥ 6000 current) — candidate thin-navigator |
| `merge` | 3 | overlap with another skill (Jaccard/shingle) — is waiting alias-mechanism, not executed |
| `retrieval-only` | 2 | noticeable body + rare use |

## Bucket table

Amount ⊕tier0/↻tier1 — cumulative resident/on-trigger bucket tax (tokens,
`skill_budget`, review `budget.py`).

| Bucket | Skills | Σ⊕tier0 | Σ↻tier1 | keep | thin | retrieval-only | merge | dead |
|---|---|---|---|---|---|---|---|---|
| ai | 2 | 199 | 2018 | 0 | 0 | 0 | 0 | 2 |
| architect | 14 | 880 | 44597 | 0 | 0 | 0 | 1 | 13 |
| azguard | 1 | 37 | 1679 | 0 | 0 | 0 | 0 | 1 |
| blender | 2 | 140 | 2287 | 0 | 0 | 0 | 0 | 2 |
| blender-modeling | 6 | 506 | 8887 | 0 | 0 | 0 | 0 | 6 |
| botkit | 1 | 29 | 234 | 0 | 0 | 0 | 0 | 1 |
| creative | 1 | 155 | 26240 | 0 | 1 | 0 | 0 | 0 |
| devops | 11 | 548 | 9181 | 2 | 0 | 0 | 0 | 9 |
| finance | 1 | 179 | 21503 | 0 | 1 | 0 | 0 | 0 |
| founder | 10 | 406 | 15188 | 0 | 0 | 0 | 0 | 10 |
| frontend | 3 | 285 | 3795 | 0 | 0 | 0 | 0 | 3 |
| frontend-animations | 1 | 55 | 920 | 0 | 0 | 0 | 0 | 1 |
| frontend-backend | 3 | 288 | 5488 | 0 | 0 | 0 | 0 | 3 |
| frontend-figma | 1 | 99 | 813 | 0 | 0 | 0 | 0 | 1 |
| frontend-linting | 4 | 323 | 5920 | 0 | 0 | 0 | 0 | 4 |
| frontend-naive-ui | 1 | 103 | 2041 | 0 | 0 | 0 | 0 | 1 |
| frontend-nuxt | 3 | 255 | 2564 | 0 | 0 | 0 | 0 | 3 |
| frontend-reka | 1 | 105 | 2007 | 0 | 0 | 0 | 0 | 1 |
| frontend-tailwind | 2 | 240 | 4458 | 0 | 0 | 0 | 0 | 2 |
| frontend-vite | 4 | 180 | 3150 | 0 | 0 | 0 | 0 | 4 |
| frontend-vue | 11 | 854 | 25744 | 0 | 1 | 0 | 0 | 10 |
| frontend-wayfinder | 1 | 48 | 994 | 0 | 0 | 0 | 0 | 1 |
| general | 20 | 1402 | 23319 | 3 | 0 | 0 | 0 | 17 |
| laravel-architecture | 6 | 677 | 9730 | 0 | 0 | 0 | 0 | 6 |
| laravel-auth | 3 | 202 | 3358 | 0 | 0 | 0 | 0 | 3 |
| laravel-data-layer | 2 | 160 | 3314 | 1 | 0 | 0 | 0 | 1 |
| laravel-extras | 3 | 225 | 4257 | 0 | 0 | 0 | 0 | 3 |
| laravel-filament | 1 | 63 | 2374 | 0 | 0 | 1 | 0 | 0 |
| laravel-livewire | 1 | 128 | 1283 | 0 | 0 | 0 | 0 | 1 |
| laravel-testing | 4 | 323 | 7993 | 0 | 0 | 0 | 0 | 4 |
| legal | 1 | 145 | 29249 | 0 | 1 | 0 | 0 | 0 |
| marketing | 1 | 142 | 16617 | 0 | 1 | 0 | 0 | 0 |
| mobile | 1 | 107 | 867 | 0 | 0 | 0 | 0 | 1 |
| operator | 6 | 296 | 31668 | 0 | 0 | 0 | 1 | 5 |
| oss-dev | 10 | 627 | 13978 | 1 | 0 | 0 | 0 | 9 |
| php | 17 | 1122 | 19300 | 4 | 0 | 0 | 0 | 13 |
| php-packages | 9 | 685 | 5417 | 1 | 0 | 0 | 0 | 8 |
| pm | 10 | 438 | 33491 | 0 | 0 | 0 | 1 | 9 |
| python | 2 | 58 | 1163 | 0 | 0 | 0 | 0 | 2 |
| quality | 10 | 738 | 19065 | 1 | 0 | 1 | 0 | 8 |
| research | 2 | 325 | 24400 | 0 | 1 | 0 | 0 | 1 |
| roles | 4 | 80 | 5253 | 0 | 0 | 0 | 0 | 4 |
| sales | 1 | 143 | 25593 | 0 | 1 | 0 | 0 | 0 |
| security | 1 | 184 | 30199 | 0 | 1 | 0 | 0 | 0 |
| system | 7 | 607 | 11012 | 0 | 0 | 0 | 0 | 7 |

All 45 buckets are covered (amount N = 206).

## Name verdicts

### merge (3) — is waiting alias-mechanism P7.5, NOT executed

| Skill | ↻tier1 | Overlap with | desc Jaccard | body shingle |
|---|---|---|---|---|
| `architect/dev-engineering-super-skill` | 23962 | `operator/operations-cx-super-skill` | 0.412 | 0.001 |
| `operator/operations-cx-super-skill` | 22355 | `architect/dev-engineering-super-skill`, `pm/pm-super-skill` | 0.412 / 0.404 | 0.001 / 0.001 |
| `pm/pm-super-skill` | 23037 | `operator/operations-cx-super-skill` | 0.404 | 0.001 |

See [controversial case №1](#1-merge-verdict-by-3-super-skill-monoliths--probable-false-positive)
below - overlap this is almost certainly a false signal (pattern phrase in description,
not content).

### thin (8) — monolith body (↻tier1 ≥ 6000 current), candidate thin-navigator P7.3

| Skill | ⊕tier0 | ↻tier1 | usage |
|---|---|---|---|
| `security/agent-security-super-skill` | 184 | 30199 | was not used in the 30 day window |
| `legal/legal-super-skill` | 145 | 29249 | was not used in the 30 day window |
| `creative/content-creative-super-skill` | 155 | 26240 | was not used in the 30 day window |
| `sales/sales-super-skill` | 143 | 25593 | was not used in the 30 day window |
| `finance/finance-super-skill` | 179 | 21503 | was not used in the 30 day window |
| `research/research-knowledge-super-skill` | 195 | 20472 | was not used in the 30 day window |
| `marketing/marketing-super-skill` | 142 | 16617 | was not used in the 30 day window |
| `frontend-vue/vueuse-functions` | 34 | 10838 | was not used in the 30 day window |

First 7 - external `*-super-skill` monoliths (see [monoliths section](#10-external-monoliths-≥50kb--list-for-p73)).
`vueuse-functions` — is also a token monolith (10838 current), but the body is 36.0KB —
**below** threshold 50KB from TK P7.3, is therefore not on the confirmed list «10»
(see card [controversial case №4](#4-vueuse-functions--monolith-by tokens-but-not-by-the-stated-threshold-p73)).

### retrieval-only (2)

| Skill | ↻tier1 | Uses |
|---|---|---|
| `quality/playwright-e2e` | 2544 | 1× in 30 days |
| `laravel-filament/filament` | 2374 | 1× in 30 days |

### keep (13) — really caught Skill-tool in the window

| Skill | ↻tier1 | Uses |
|---|---|---|
| `general/git-commit-rules` | 934 | 25× in 30 days |
| `php/database` | 961 | 5× in 30 days |
| `php/repositories` | 1563 | 4× in 30 days |
| `general/complex-task-orchestrator` | 659 | 2× in 30 days |
| `php/laravel-structure` | 2020 | 2× in 30 days |
| `quality/code-review` | 1622 | 2× in 30 days |
| `devops/ci-cd` | 1150 | 1× in 30 days |
| `devops/db-test-preflight` | 1703 | 1× in 30 days |
| `general/task-brief-template` | 1253 | 1× in 30 days |
| `laravel-data-layer/laravel-broadcasting` | 1257 | 1× in 30 days |
| `oss-dev/resolving-merge-conflicts` | 335 | 1× in 30 days |
| `php/namespace-refactor-safety` | 365 | 1× in 30 days |
| `php-packages/laravel-package-compatibility` | 446 | 1× in 30 days |

### dead (180)

Full list of names - [Appendix A](#application-a-full-output-audit-206-lines)
(table covers all 206 skills, including all 180 `dead` from their ⊕tier0/↻tier1). By
buckets - column `dead` in [table above](#table-by-buckets). Read the verdict on
section rules [«Honesty usage-windows»](#honesty-usage-windows-read-before-verdicts):
not «list to delete», a «list without explicit trigger in window».

## 10 external monoliths ≥50KB — list for P7.3

Confirmed by measurement (not from memory from Phase Context): exactly **10** skills with
body SKILL.md ≥50KB, all external (`upstream.json`, repositories `get-zeked/*-super-skill`,
MIT, `strategy: notify`). The sum of them ↻tier1 = **239 227 current** — this is it «~240K
body tokens on-trigger» from Phase Context P7 (matches up to rounding).

| Bucket | Skill (name) | Catalog | Body, KB | ↻tier1, current | Audit verdict | Upstream repo |
|---|---|---|---|---|---|---|
| security | agent-security-super-skill | `skills/security/security` | 101.7 | 30199 | thin | get-zeked/agent-security-super-skill |
| legal | legal-super-skill | `skills/legal/legal` | 97.5 | 29249 | thin | get-zeked/legal-super-skill |
| sales | sales-super-skill | `skills/sales/sales` | 89.6 | 25593 | thin | get-zeked/sales-super-skill |
| creative | content-creative-super-skill | `skills/creative/content-creative` | 88.4 | 26240 | thin | get-zeked/content-creative-super-skill |
| architect | dev-engineering-super-skill | `skills/architect/engineering` | 80.0 | 23962 | merge* | get-zeked/dev-engineering-super-skill |
| pm | pm-super-skill | `skills/pm/product` | 77.1 | 23037 | merge* | get-zeked/pm-super-skill |
| operator | operations-cx-super-skill | `skills/operator/operations-cx` | 75.2 | 22355 | merge* | get-zeked/operations-cx-super-skill |
| finance | finance-super-skill | `skills/finance/finance` | 72.1 | 21503 | thin | get-zeked/finance-super-skill |
| research | research-knowledge-super-skill | `skills/research/research` | 68.4 | 20472 | thin | get-zeked/research-knowledge-super-skill |
| marketing | marketing-super-skill | `skills/marketing/marketing` | 55.9 | 16617 | thin | get-zeked/marketing-super-skill |

`*` — 3 monolith bear AT THE SAME TIME the verdict `merge` (overlap wins among themselves
`thin` by signal priority in `verdict()`) and status «monolith ≥50KB». For P7.3 this
not a blocker: translation to thin-navigator and solution for alias/merge —
independent axes; see [controversial case №1](#1-merge-verdict-by-3-super-skill-monoliths--probable-false-positive).
Paths - from package root `packages/skiller/`.

## Controversial cases

### 1. `merge`-verdict on 3 super-skill monoliths - probable false-positive

`architect/dev-engineering-super-skill`, `operator/operations-cx-super-skill`,
`pm/pm-super-skill` give desc Jaccard 0.40–0.41 (threshold 0.4), but body shingle total
**0.001** (threshold 0.3, i.e. They don’t share the contents of their bodies at all.). Reason
overlap is visible in the description — they are almost verbatim template:

> «Broad **{X}**-bucket navigator (composite of external {X} skills). For specific
> work prefer the granular skill — … Use only for a cross-cutting overview when no
> single skill fits.»

Vendor template matches (`get-zeked/*-super-skill`), and not the subject area
(engineering vs ops vs pm — three different domains). Practical conclusion: `merge` here,
most likely a false signal from the Jaccard-threshold on template descriptions, not
reason to drain three role-playing buckets. Even when alias-mechanism will appear, these
three pairs should be reviewed manually before real alias — fact itself «description
similar» doesn't mean «merge». Additional nuance: their own description already
call them «navigator» — that is, these are ideal and low-risk candidates for
P7.3 thin-navigator regardless of the outcome merge-question.

### 2. CORE-skills show `dead` with known activity - confirms the detector's blind spot

`general/anti-drift`, `general/compact-responses`, `general/context-economy`,
`general/mcp-advisor`, `general/verify-claims` — all 5 out of 8 `CORE_SKILLS`
(`configs/core-policy.json`), distributed in every connect-default project -
verdict `dead`, 0 downloads. The remaining 3 CORE (`session-handoff`, `query-craft`,
`gh-review`) for verification: `session-handoff` too dead, `query-craft` (bucket
`research`) too dead, `gh-review` (bucket `oss-dev`) too dead. All 8/8 CORE_SKILLS
— `dead` for this audit. This is not «CORE doesn't work» (this is checked separately
`skiller budget --check-core`, see below), but direct empirical confirmation
restrictions `analyze.py`: auto-trigger plugin by description is not in the transcript
looks like explicit `Skill`-tool-call. Reference: `skiller budget --check-core`
(separate from usage-audit channel) at the time of this run showed `CORE resident
(⊕ tier-0): 662 current / target 750 — OK (8/8 skills)` — that is, all 8 CORE
are physically distributed, just usage-the detector does not see them. Conclusion: `dead`-verdict
CORE-skills **definitely false** — a compelling argument not to touch these 8 in P7.4
regardless of their usage-lines (in P7.4 they are already outside the perimeter - CORE obviously not
candidate for exclude).

### 3. `general` — the largest dead-bucket (17/20), but 3 living skills keep it high loaded_count

`general` — 20 skills, 17 `dead`, but `git-commit-rules` (25× in 30 days - the most
high usage throughout the registry) and `complex-task-orchestrator`/`task-brief-template`
(`keep`) are actually used. Bucket mixes CORE (auto-trigger, blind spot
detector, see case №2) and non-CORE general-skills, some of which (for example
`git-commit-rules`) are explicitly called as a separate Skill. Mixing statistically
«drowns» bucket in dead-percent, although inside there is a working core. Lesson for P7.4:
exclude-decisions to make **by skill**, not for the bucket as a whole.

### 4. `vueuse-functions` — monolith by tokens, but not by the stated threshold P7.3

`frontend-vue/vueuse-functions` — verdict `thin` (↻tier1=10838 ≥ 6000), but the body
36.0KB < 50KB threshold that describes the perimeter P7.3 in Phase Context/this document.
Formally this is also «monolith», is simply an order of magnitude smaller than the other ten
(they are 55.9–101.7KB). Solution: **do not include** to the confirmed list «10» this
waves (P7.3 is tied to a specific number and threshold from the plan), leave as separate
`thin`-is a candidate for a separate future passage - especially since it is the only one
non-`*-super-skill` (not from `get-zeked`) monolith in the registry, physical layout
navigator may differ.

## Target Topology Sketch 45 → ~34 (Sketch ONLY, separate future release)

Below is an illustration, NOT a solution and NOT a plan for execution in this wave. Based on
structural observation (many one-/low-skill thematically related buckets),
not on overlap-audit detector (for small buckets below overlap hardly pops up -
Jaccard is calculated according to description, for different tools Vue/Nuxt/Tailwind descriptions
are not similar, although the domain is the same). Waiting alias-mechanism for safe execution
(back-compat D14).

| Candidate group | Now (buckets / skills) | Shorthand sketch | Rationale |
|---|---|---|---|
| `frontend-animations`, `frontend-backend`, `frontend-figma`, `frontend-linting`, `frontend-naive-ui`, `frontend-nuxt`, `frontend-reka`, `frontend-tailwind`, `frontend-vite`, `frontend-wayfinder` | 10 buckets / 21 skill | → ~3 (e.g. `frontend-tooling`, `frontend-ui`, `frontend-nuxt`-group) | every 1–4 skills, all under one domain (Vue-frontend ecosystem), crushing is clearly excessively granular |
| `blender` + `blender-modeling` | 2 bucket / 8 skills | → 1 (`blender`) | one tool, artificial separation mcp/modeling |
| `azguard`, `botkit` | 2 bucket / 2 skill | → 0 (removal from the registry, not merge) | CLAUDE.md already marks them «for transferring inside packages» — this is not bucket-merge, and another process (out of P7 scope) |
| `laravel-livewire` (1 skill) → `laravel-extras` | 2 bucket / 4 skill | → 1 | livewire-blade-attributes — the only skill of Bucket, thematically related to extras |

Sketch total: 45 − 7 (frontend) − 1 (blender) − 2 (azguard/botkit removal) − 1
(livewire) ≈ **34 bucket**. No rows in this table are executed in P7 —
is an input for a future separate release after P7.5.

## What we are NOT doing in this wave and why

- **We do not rename or merge buckets** (incl. those 3 of «controversial case
  №1» and the entire topology sketch above) — solution D14 master plan: 13 projects sitting
  on marketplace-channel (`enabledPlugins` in `.claude/settings.local.json`),
  renaming/merging a bucket breaks their connection without migration. Confirmed
  by direct counting `~/.swissknifeman/projects.json`: exactly **13** projects with
  `channel: marketplace` at the time of this run (matches the number D14).
- **Don't cut 10 monoliths into subskills** — solution D13: cutting grows resident
  ⊕tier-0 (each new skill has its own description line, tax for each request);
  instead - thin-navigator (SKILL.md-navigator + `references/full.md`,
  the body remains physically one file, it just doesn’t load entirely on-trigger).
  This P7.3, separate item, not here.
- **Not executable `merge`-verdicts** — are waiting alias-mechanism P7.5 (marketplace-entry
  with `skills[]`-list, use case - curated plugin `core`). Before it merge
  physically breaks the connection «bucket name → plugin» for consumers.
- **We do not exclude any skill from profiles (P7.4 not done here)** — condition
  phases: «≥2 weeks pro-usage data after telemetry appears»; on 2026-07-02
  real horizon usage-data - 30 days, and this is all that has accumulated (see
  window honesty section). P7.4 — separate item, after accumulating more windows.
- **We do not edit the content upstream-monolith bodies** — faithful-first (CLAUDE.md
  root): transferred to P7.3 bodies `references/full.md` are translated verbatim,
  without editing.

## Channel correction (P2.2 SKM-MASTER-003) — 2026-07-02

Second, transcript-independent source of visibility usage closes the blind spot,
described above («Honesty usage-windows» + Controversial case №2). This is an addition, not
rewrite - original numbers/the tables of this document above remain as a snapshot
«to» (P7.2, only transcript-channel).

**What has changed (`audit.py`, P2.2):** skill is considered **resident**, if he
(1) is included in `CORE_SKILLS` (`configs/core-policy.json`, is loaded with tier-0 in each
connect-project) **or** (2) is included in the active set (`budget.resolve_active_set` —
profile/buckets `.swissknife.json`, the same path that is already used
`analyze._active_skill_names`) of at least one of the projects registered in
`~/.swissknifeman/projects.json`. Resident skill without a single explicit one Skill-tool-
call in transcript **no longer receives a verdict `dead`** — instead `keep` with
usage_note `«resident, no direct calls visible (auto-trigger out of detection)»`.
B JSON/in the renderer, each skill now has a field `channel: skill-call | resident |
none` — it is clearly visible WHAT source saw the skill (`skill-call` — stronger, wins
when matching `resident`).

**Deviation from setting item'a (recorded honestly).** Wording P2.2 in
plan (`Inputs`) assumed the second source SCHEMA=2-trend/run-reports
(`<project>/.claude/analyze/usage-trend.ndjson`). Read repo-grounded: format
trend lines - `{ts, session, in, out, cache_read, cache_creation, by_model,
tools_total, files_changed, agents, wall_s, retr_chars}` (writes
`packages/harness/configs/claude-code/hooks/run-report/run-report.py` +
`_lib.py`, docstring `analyst/token_report.py`) — it carries tokens/timings/tool-
counters AGGREGATE, but **does not carry per-skill call/load signal in general** (hook not
detect `Skill`-tool calls, only `skills-lock.json`-managed paths for
`protected_writes`). This is exactly the fact that has already been recorded above as
ESCALATION-REQUIRED (lines 27–43, run P7.2): «SCHEMA=2 → bucket-audit» from
production does not correspond to the real data of this source. So instead of reading
`usage-trend.ndjson` channel implemented `resident` on CORE_SKILLS + active set
profile/buckets - it solves the same problem (P2.2 Why: «resident CORE-skills
look dead»), building on an already existing, tested path `resolve_active_set`
(instead of a new parser for a non-existent signal). This is NOT improvisation beyond the plan: point
clearly provided for a truncated blind spot, and its real reason/repair has already been made
was partially explored in the same document in a previous pass.

**New numbers dead/keep** (run 2026-07-02, `since_days=30`, 21 scanned
project, 139 resident skills out of 206):

| Verdict | N (was*, transcript-only) | N (became, + channel resident) |
|---|---|---|
| `dead` | 187 | **65** |
| `keep` | 13 | **135** |
| `merge` | 3 | 3 |
| `thin` | 1 | 1 |
| `retrieval-only` | 2 | 2 |

\* «was» reconstructed from the current run (same 206 skills, same
transcript-usage): lines with `channel=resident` and `verdict=keep` when `loaded_count=0`
before the amendment would have received `dead` — 122 such lines. Absolute numbers of this column
different from table «Summary in one line» above (180/13/8/3/2, snapshot P7.2) —
the difference is due to natural registry drift/content between runs
(P7.3 thin-navigator has already passed, `thin` fell 8→1), not a channel correction; comparison
«was/became» in this table - **within one run**, honestly isolates exactly
resident channel effect.

All **8/8 `CORE_SKILLS`** (`context-economy`, `anti-drift`, `compact-responses`,
`session-handoff`, `mcp-advisor`, `verify-claims`, `query-craft`, `gh-review`) now
`keep`/`resident` — Controversial case №2 above is closed. The remaining 122 flipped skills are
not CORE, and the skills of the buckets that are actually included in the active profile of at least one of the 21
registered project (for example `php/*`, `frontend-vue/*`, `devops/*`,
`oss-dev/*`) — they are physically distributed to these projects via connect/vendor, therefore
are formally resident, even if a specific project has never caught their trigger.

**What does this mean for P7.4 (dead-pass, next item, same plan).** Resident channel
removed false positives at the level «distributed but not caught by transcript» — remaining
**65 `dead`** no longer intersect with any CORE, neither with active dialing none of 21
known projects: this is a narrower, more reliable candidate list for
profile-excludes. He still hasn't «proven useless» (projects outside
`~/.swissknifeman/projects.json` are not visible to both channels; residence through
`.swissknife.json` — best-effort snapshot of the current state of the configs, not history) —
P7.4 remains to be executed as reversible exclude, not deleting, and not before «≥2 weeks
cont.usage» according to its own spec.

**How to get the current numbers again:**

```bash
cd packages/skiller
PYTHONPATH="$(pwd)/lib:$(cd ../.. && pwd)" python3 -m skiller "$(pwd)" bucket-audit --json \
  | python3 -c "import json,sys; d=json.load(sys.stdin); \
      from collections import Counter; print(Counter(r['verdict'] for r in d['items'])); \
      print('resident_skills', d['resident_skills'])"
```

## P3.5 postscript - 2026-07-28: sketch updated for today's dates, consolidation is NOT performed

**Frame (must be read before the numbers below).** The motive for this postscript is
**SUPPORT** (46→48 buckets are expensive to run), and NOT listing budget: measurement
2026-07-25 refuted the section premise «Sketch of target topology» above -
listing entries add **skills**, not buckets; fine granularity
**saves** narrow subscriber symbols, consolidating them **would take away**.
Sell update below as listing budget win **prohibited** (same
frame as the section above). Execution is still not done by this or
any subsequent item'om of the current wave - the decision goes to the owner as
**OQ-10** (open-questions.md`), closed for `finish`
option **(b)**: consolidation is not performed at all.

**What has changed since the 2026-07-02 cut:** registry has grown **46 → 48 buckets**
(canonization 13 bootstrap-skills to a new bucket `repository-bootstrap`,
commit `589c320e`, outside families `frontend*`/`laravel-*` — the sketch below does not
concerns). Blocker `alias_of` remains unchecked (P7.5 🟢, archived
) — is still declared today in the registry of aliases
zero, the mechanism is available but not enabled.

**Mandatory calculation: listing BEFORE/AFTER for ACTUAL subscribers according to their
`enabledPlugins`**, standard - `flexcrm` (23 plugin, the most loaded
fleet subscriber, same project as control reconciliation D83):

| Family | Baketov now | ENABLED `flexcrm` (characters) | NOT included (characters) | Listing AFTER hypothetical merger |
|:--|--:|--:|--:|--:|
| `frontend*` (12 buckets, sketch → ~3) | 12 | 7 060 (8 buckets) | 1 683 (4 bucket: `-animations` 180, `-figma` 323, `-nuxt` 835, `-reka` 345) | **8 743** (merge - all-or-nothing by merged bucket, `flexcrm` would get back the excluded 1,683 characters) |
| `laravel-*` (7 buckets, sketch → 6: `-livewire`→`-extras`) | 7 | 4 772 (6 buckets) | 409 (`laravel-livewire`) | **5 181** |
| **TOTAL** | 19 | **11 832** | **2 092** | **13 924** |

Method and numbers are reproducible (same command as control reconciliation D83 below);
**11 832 / 2 092 char - byte-to-byte match** with reference D83 (measured 2026-07-25),
despite the growth of the registry - families `frontend*`/`laravel-*` was not affected by the growth itself.

The result of the sketch with the number of buckets has not changed (46 → ~34 from the section above became 48 → ~36
after growth `repository-bootstrap`, direction same): **consolidation returned
would `flexcrm` 2 092 symbols that it does NOT carry today** thanks to granularity
— that is, according to the listing budget metric, the sketch is not a win, but **loss**.
The only legal motive for performance is accompaniment (48 it’s more expensive to carry buckets,
than ~36), and ONLY he goes to OQ-10.

**Control reconciliation (play):**

```bash
cd <REPO_ROOT>
PYTHONPATH=packages/skiller/lib python3 -c "
from pathlib import Path
from skiller.common import parse_frontmatter
root = Path('packages/skiller/skills')
enabled = {'frontend','frontend-backend','frontend-linting','frontend-naive-ui',
           'frontend-tailwind','frontend-vite','frontend-vue','frontend-wayfinder',
           'laravel-architecture','laravel-auth','laravel-data-layer',
           'laravel-extras','laravel-filament','laravel-testing'}
fam = [d.name for d in root.iterdir() if d.name.startswith('frontend') or d.name.startswith('laravel-')]
inc = exc = 0
for b in fam:
    chars = sum(len(parse_frontmatter(md).get('description','') or '')
                for md in (root/b).rglob('SKILL.md'))
    (globals().__setitem__('inc', inc+chars) if b in enabled else globals().__setitem__('exc', exc+chars))
print('included', inc, 'excluded', exc)
"
```

Sources: §0/§3
(budget adjustment 30,000/6 000) ·
(full calculation of this approach) · D74–D77/D83
(motive frame, prohibition on selling as a budget gain) · `open-questions.md` OQ-10.

## How to reproduce

```bash
cd packages/skiller
PYTHONPATH="$(pwd)/lib:$(cd ../.. && pwd)" python3 -m skiller "$(pwd)" bucket-audit --json
# human-readable render:
PYTHONPATH="$(pwd)/lib:$(cd ../.. && pwd)" python3 -m skiller "$(pwd)" bucket-audit
# another window:
... bucket-audit --since 14 --json
```

> Observations during the preparation of this document: `bin/skiller` (bash-launcher) at the time
> run **didn't know** command `bucket-audit` — whitelist commands in `case "$CMD" in
> connect|vendor|…)` (string ~58 `packages/skiller/bin/skiller`) was not expanded
> along with adding the command to `lib/skiller/cli.py::COMMANDS`. Summary CLI
> reached `python3 -m skiller <repo_root> bucket-audit …` directly, bypassing
> launcher - the command is fully working, but the end user through `skiller
> bucket-audit` will receive `Unknown command: bucket-audit`, while line whitelist
> will not be updated. File `bin/skiller` out scope this item (P7.2 Files:
> this document only) — I record as a find for P7.1/orchestrator, I don't edit
> here.

## Appendix A: full audit output (206 lines)

| Skill | ⊕tier0 | ↻tier1 | Verdict | Usage |
|---|---|---|---|---|
| `ai/ai-agents` | 88 | 613 | dead | was not used in the 30 day window |
| `ai/token-efficient` | 111 | 1405 | dead | was not used in the 30 day window |
| `architect/agent-design` | 25 | 1744 | dead | was not used in the 30 day window |
| `architect/api-design` | 26 | 1129 | dead | was not used in the 30 day window |
| `architect/architecture` | 27 | 1329 | dead | was not used in the 30 day window |
| `architect/codebase-design` | 117 | 1996 | dead | was not used in the 30 day window |
| `architect/data-schema` | 28 | 924 | dead | was not used in the 30 day window |
| `architect/dev-engineering-super-skill` | 133 | 23962 | merge | was not used in the 30 day window |
| `architect/domain-modeling` | 122 | 1261 | dead | was not used in the 30 day window |
| `architect/eval-design` | 32 | 1570 | dead | was not used in the 30 day window |
| `architect/figma-mcp-core` | 136 | 1629 | dead | was not used in the 30 day window |
| `architect/legal-compliance` | 26 | 1841 | dead | was not used in the 30 day window |
| `architect/observability-design` | 32 | 1315 | dead | was not used in the 30 day window |
| `architect/package-contribution-protocol` | 106 | 1857 | dead | was not used in the 30 day window |
| `architect/security-design` | 38 | 2151 | dead | was not used in the 30 day window |
| `architect/tech-stack-selection` | 32 | 1889 | dead | was not used in the 30 day window |
| `azguard/azguard` | 37 | 1679 | dead | was not used in the 30 day window |
| `blender/mcp-blender` | 118 | 1503 | dead | was not used in the 30 day window |
| `blender/version-gotchas` | 22 | 784 | dead | was not used in the 30 day window |
| `blender-modeling/build-loop` | 128 | 2137 | dead | was not used in the 30 day window |
| `blender-modeling/config-conventions` | 114 | 2219 | dead | was not used in the 30 day window |
| `blender-modeling/model-rules` | 31 | 761 | dead | was not used in the 30 day window |
| `blender-modeling/parametric-config` | 111 | 2196 | dead | was not used in the 30 day window |
| `blender-modeling/scene-conventions` | 95 | 914 | dead | was not used in the 30 day window |
| `blender-modeling/threading` | 27 | 660 | dead | was not used in the 30 day window |
| `botkit/botkit` | 29 | 234 | dead | was not used in the 30 day window |
| `creative/content-creative-super-skill` | 155 | 26240 | thin | was not used in the 30 day window |
| `devops/ci-cd` | 55 | 1150 | keep | 1× in 30 days |
| `devops/db-test-preflight` | 104 | 1703 | keep | 1× in 30 days |
| `devops/docker` | 66 | 400 | dead | was not used in the 30 day window |
| `devops/docker-dev-prod` | 42 | 952 | dead | was not used in the 30 day window |
| `devops/docker-php` | 40 | 794 | dead | was not used in the 30 day window |
| `devops/docker-postgres` | 43 | 834 | dead | was not used in the 30 day window |
| `devops/docker-services` | 48 | 885 | dead | was not used in the 30 day window |
| `devops/docker-vite` | 39 | 706 | dead | was not used in the 30 day window |
| `devops/gitops` | 30 | 743 | dead | was not used in the 30 day window |
| `devops/makefile` | 43 | 759 | dead | was not used in the 30 day window |
| `devops/node-pnpm-preflight` | 38 | 255 | dead | was not used in the 30 day window |
| `finance/finance-super-skill` | 179 | 21503 | thin | was not used in the 30 day window |
| `founder/adversarial-check` | 55 | 1162 | dead | was not used in the 30 day window |
| `founder/competitive-analysis` | 30 | 1343 | dead | was not used in the 30 day window |
| `founder/customer-discovery` | 55 | 1315 | dead | was not used in the 30 day window |
| `founder/defensibility` | 42 | 1151 | dead | was not used in the 30 day window |
| `founder/idea-audit` | 61 | 2502 | dead | was not used in the 30 day window |
| `founder/idea-discovery` | 35 | 1668 | dead | was not used in the 30 day window |
| `founder/new-project` | 28 | 1387 | dead | was not used in the 30 day window |
| `founder/pitch-deck` | 26 | 1583 | dead | was not used in the 30 day window |
| `founder/risk-assessment` | 32 | 1302 | dead | was not used in the 30 day window |
| `founder/startup-lifecycle` | 42 | 1775 | dead | was not used in the 30 day window |
| `frontend/document-writer` | 88 | 1283 | dead | was not used in the 30 day window |
| `frontend/filepond-upload` | 136 | 2242 | dead | was not used in the 30 day window |
| `frontend/web-design-guidelines` | 61 | 270 | dead | was not used in the 30 day window |
| `frontend-animations/motion` | 55 | 920 | dead | was not used in the 30 day window |
| `frontend-backend/backend-type-sync` | 100 | 2075 | dead | was not used in the 30 day window |
| `frontend-backend/inertia-vue` | 58 | 1485 | dead | was not used in the 30 day window |
| `frontend-backend/laravel-echo-client` | 130 | 1928 | dead | was not used in the 30 day window |
| `frontend-figma/figma-to-vue` | 99 | 813 | dead | was not used in the 30 day window |
| `frontend-linting/antfu` | 74 | 1282 | dead | was not used in the 30 day window |
| `frontend-linting/eslint-flat-config` | 112 | 2411 | dead | was not used in the 30 day window |
| `frontend-linting/js-code-style` | 47 | 870 | dead | was not used in the 30 day window |
| `frontend-linting/ts-library` | 90 | 1357 | dead | was not used in the 30 day window |
| `frontend-naive-ui/naive-ui-theming` | 103 | 2041 | dead | was not used in the 30 day window |
| `frontend-nuxt/nuxt` | 80 | 1095 | dead | was not used in the 30 day window |
| `frontend-nuxt/nuxt-modules` | 125 | 644 | dead | was not used in the 30 day window |
| `frontend-nuxt/nuxt-seo` | 50 | 825 | dead | was not used in the 30 day window |
| `frontend-reka/reka-ui-cva` | 105 | 2007 | dead | was not used in the 30 day window |
| `frontend-tailwind/dark-mode` | 113 | 2209 | dead | was not used in the 30 day window |
| `frontend-tailwind/tailwind-conventions` | 127 | 2249 | dead | was not used in the 30 day window |
| `frontend-vite/vite` | 57 | 615 | dead | was not used in the 30 day window |
| `frontend-vite/vite-module-loader` | 27 | 692 | dead | was not used in the 30 day window |
| `frontend-vite/vite-multi-build` | 47 | 1013 | dead | was not used in the 30 day window |
| `frontend-vite/vitepress` | 49 | 830 | dead | was not used in the 30 day window |
| `frontend-vue/pinia` | 54 | 691 | dead | was not used in the 30 day window |
| `frontend-vue/pinia-stores` | 128 | 1920 | dead | was not used in the 30 day window |
| `frontend-vue/vitest` | 47 | 817 | dead | was not used in the 30 day window |
| `frontend-vue/vitest-vue` | 55 | 1049 | dead | was not used in the 30 day window |
| `frontend-vue/vue` | 63 | 876 | dead | was not used in the 30 day window |
| `frontend-vue/vue-best-practices` | 99 | 2560 | dead | was not used in the 30 day window |
| `frontend-vue/vue-composition-api` | 80 | 531 | dead | was not used in the 30 day window |
| `frontend-vue/vue-dynamic-icons` | 76 | 1303 | dead | was not used in the 30 day window |
| `frontend-vue/vue-router-best-practices` | 141 | 2792 | dead | was not used in the 30 day window |
| `frontend-vue/vue-testing-best-practices` | 77 | 2367 | dead | was not used in the 30 day window |
| `frontend-vue/vueuse-functions` | 34 | 10838 | thin | was not used in the 30 day window |
| `frontend-wayfinder/wayfinder` | 48 | 994 | dead | was not used in the 30 day window |
| `general/anti-drift` | 43 | 1258 | dead | was not used in the 30 day window |
| `general/compact-responses` | 60 | 570 | dead | was not used in the 30 day window |
| `general/complex-task-orchestrator` | 44 | 659 | keep | 2× in 30 days |
| `general/context-economy` | 71 | 2133 | dead | was not used in the 30 day window |
| `general/cross-layer-change-checklist` | 37 | 461 | dead | was not used in the 30 day window |
| `general/git-commit-rules` | 29 | 934 | keep | 25× in 30 days |
| `general/git-safety` | 84 | 600 | dead | was not used in the 30 day window |
| `general/grill-with-docs` | 98 | 911 | dead | was not used in the 30 day window |
| `general/implement` | 88 | 479 | dead | was not used in the 30 day window |
| `general/mcp-advisor` | 107 | 1893 | dead | was not used in the 30 day window |
| `general/naming-conventions` | 86 | 1564 | dead | was not used in the 30 day window |
| `general/packages-stack` | 85 | 530 | dead | was not used in the 30 day window |
| `general/plan-protocol` | 43 | 1889 | dead | was not used in the 30 day window |
| `general/project-map` | 83 | 645 | dead | was not used in the 30 day window |
| `general/session-handoff` | 41 | 618 | dead | was not used in the 30 day window |
| `general/skills-ssot` | 35 | 1771 | dead | was not used in the 30 day window |
| `general/spec-interview` | 58 | 753 | dead | was not used in the 30 day window |
| `general/task-brief-template` | 79 | 1253 | keep | 1× in 30 days |
| `general/verify-claims` | 133 | 2696 | dead | was not used in the 30 day window |
| `general/writing-style` | 98 | 1702 | dead | was not used in the 30 day window |
| `laravel-architecture/config-driven-abstraction` | 135 | 487 | dead | was not used in the 30 day window |
| `laravel-architecture/eloquent-accessors` | 119 | 1255 | dead | was not used in the 30 day window |
| `laravel-architecture/enum-attributes` | 131 | 1977 | dead | was not used in the 30 day window |
| `laravel-architecture/enum-state-machine` | 132 | 1585 | dead | was not used in the 30 day window |
| `laravel-architecture/laravel-subagents` | 77 | 1287 | dead | was not used in the 30 day window |
| `laravel-architecture/modular-architecture` | 83 | 3139 | dead | was not used in the 30 day window |
| `laravel-auth/attribute-authorization` | 83 | 2129 | dead | was not used in the 30 day window |
| `laravel-auth/laravel-permissions` | 68 | 426 | dead | was not used in the 30 day window |
| `laravel-auth/laravel-security-audit` | 51 | 803 | dead | was not used in the 30 day window |
| `laravel-data-layer/laravel-broadcasting` | 40 | 1257 | keep | 1× in 30 days |
| `laravel-data-layer/laravel-data` | 120 | 2057 | dead | was not used in the 30 day window |
| `laravel-extras/medialibrary` | 33 | 1048 | dead | was not used in the 30 day window |
| `laravel-extras/pennant-development` | 58 | 505 | dead | was not used in the 30 day window |
| `laravel-extras/spatie-settings` | 134 | 2704 | dead | was not used in the 30 day window |
| `laravel-filament/filament` | 63 | 2374 | retrieval-only | 1× in 30 days |
| `laravel-livewire/livewire-blade-attributes` | 128 | 1283 | dead | was not used in the 30 day window |
| `laravel-testing/health-checks` | 129 | 2325 | dead | was not used in the 30 day window |
| `laravel-testing/laravel-dusk` | 34 | 1008 | dead | was not used in the 30 day window |
| `laravel-testing/laravel-testing` | 56 | 3061 | dead | was not used in the 30 day window |
| `laravel-testing/test-isolation-guard` | 104 | 1599 | dead | was not used in the 30 day window |
| `legal/legal-super-skill` | 145 | 29249 | thin | was not used in the 30 day window |
| `marketing/marketing-super-skill` | 142 | 16617 | thin | was not used in the 30 day window |
| `mobile/figma-to-flutter` | 107 | 867 | dead | was not used in the 30 day window |
| `operator/capacity-planning` | 41 | 2083 | dead | was not used in the 30 day window |
| `operator/incident-response` | 41 | 1845 | dead | was not used in the 30 day window |
| `operator/oncall-rotation` | 37 | 1708 | dead | was not used in the 30 day window |
| `operator/operations-cx-super-skill` | 98 | 22355 | merge | was not used in the 30 day window |
| `operator/postmortem` | 43 | 1929 | dead | was not used in the 30 day window |
| `operator/runbook` | 36 | 1748 | dead | was not used in the 30 day window |
| `oss-dev/dependency-audit` | 33 | 1160 | dead | was not used in the 30 day window |
| `oss-dev/dx-design` | 31 | 1237 | dead | was not used in the 30 day window |
| `oss-dev/gh-review` | 77 | 1162 | dead | was not used in the 30 day window |
| `oss-dev/github-flow` | 71 | 2090 | dead | was not used in the 30 day window |
| `oss-dev/issue-triage` | 114 | 2163 | dead | was not used in the 30 day window |
| `oss-dev/oss-development` | 38 | 1392 | dead | was not used in the 30 day window |
| `oss-dev/oss-governance` | 31 | 1595 | dead | was not used in the 30 day window |
| `oss-dev/release-engineering` | 37 | 1660 | dead | was not used in the 30 day window |
| `oss-dev/resolving-merge-conflicts` | 103 | 335 | keep | 1× in 30 days |
| `oss-dev/to-issues` | 92 | 1184 | dead | was not used in the 30 day window |
| `php/code-style-spatie` | 47 | 1127 | dead | was not used in the 30 day window |
| `php/cursor-pagination-design` | 136 | 412 | dead | was not used in the 30 day window |
| `php/database` | 51 | 961 | keep | 5× in 30 days |
| `php/dependency-injection` | 39 | 1285 | dead | was not used in the 30 day window |
| `php/laravel` | 21 | 1573 | dead | was not used in the 30 day window |
| `php/laravel-best-practices` | 40 | 1727 | dead | was not used in the 30 day window |
| `php/laravel-structure` | 44 | 2020 | keep | 2× in 30 days |
| `php/named-arguments` | 50 | 694 | dead | was not used in the 30 day window |
| `php/namespace-refactor-safety` | 131 | 365 | keep | 1× in 30 days |
| `php/pao` | 59 | 654 | dead | was not used in the 30 day window |
| `php/php-naming-conventions` | 80 | 1426 | dead | was not used in the 30 day window |
| `php/php-patterns` | 25 | 2538 | dead | was not used in the 30 day window |
| `php/php-upgrade-checklist` | 71 | 672 | dead | was not used in the 30 day window |
| `php/production-readiness-checklist` | 128 | 575 | dead | was not used in the 30 day window |
| `php/repositories` | 31 | 1563 | keep | 4× in 30 days |
| `php/static-analysis` | 35 | 1123 | dead | was not used in the 30 day window |
| `php/transactional-outbox-relay` | 134 | 585 | dead | was not used in the 30 day window |
| `php-packages/laravel-package-compatibility` | 76 | 446 | keep | 1× in 30 days |
| `php-packages/laravel-package-docs` | 75 | 713 | dead | was not used in the 30 day window |
| `php-packages/laravel-package-expressive` | 114 | 578 | dead | was not used in the 30 day window |
| `php-packages/laravel-package-generate-skill` | 84 | 804 | dead | was not used in the 30 day window |
| `php-packages/laravel-package-release` | 68 | 382 | dead | was not used in the 30 day window |
| `php-packages/laravel-package-scaffold` | 77 | 615 | dead | was not used in the 30 day window |
| `php-packages/laravel-package-service-provider` | 73 | 551 | dead | was not used in the 30 day window |
| `php-packages/laravel-package-testing` | 85 | 540 | dead | was not used in the 30 day window |
| `php-packages/laravel-packages` | 33 | 788 | dead | was not used in the 30 day window |
| `pm/brd` | 28 | 592 | dead | was not used in the 30 day window |
| `pm/business-process` | 27 | 572 | dead | was not used in the 30 day window |
| `pm/go-to-market` | 26 | 1325 | dead | was not used in the 30 day window |
| `pm/monetization-design` | 36 | 1400 | dead | was not used in the 30 day window |
| `pm/pm-super-skill` | 120 | 23037 | merge | was not used in the 30 day window |
| `pm/pmf-diagnostics` | 53 | 1413 | dead | was not used in the 30 day window |
| `pm/prd-from-brd` | 38 | 1441 | dead | was not used in the 30 day window |
| `pm/product-roadmap` | 35 | 1266 | dead | was not used in the 30 day window |
| `pm/requirement-critic` | 51 | 1606 | dead | was not used in the 30 day window |
| `pm/unit-economics` | 24 | 839 | dead | was not used in the 30 day window |
| `python/ml-project-structure` | 28 | 614 | dead | was not used in the 30 day window |
| `python/venv-dependencies` | 30 | 549 | dead | was not used in the 30 day window |
| `quality/code-review` | 36 | 1622 | keep | 2× in 30 days |
| `quality/code-simplifier` | 68 | 1260 | dead | was not used in the 30 day window |
| `quality/diagnosing-bugs` | 106 | 2577 | dead | was not used in the 30 day window |
| `quality/mutation-testing` | 106 | 2580 | dead | was not used in the 30 day window |
| `quality/playwright-e2e` | 107 | 2544 | retrieval-only | 1× in 30 days |
| `quality/refactoring-plan` | 33 | 1878 | dead | was not used in the 30 day window |
| `quality/tdd-discipline` | 100 | 1374 | dead | was not used in the 30 day window |
| `quality/tech-debt-audit` | 44 | 2200 | dead | was not used in the 30 day window |
| `quality/test-strategy` | 61 | 2274 | dead | was not used in the 30 day window |
| `quality/testing-safety-report` | 77 | 756 | dead | was not used in the 30 day window |
| `research/query-craft` | 130 | 3928 | dead | was not used in the 30 day window |
| `research/research-knowledge-super-skill` | 195 | 20472 | thin | was not used in the 30 day window |
| `roles/open-source-maintainer` | 19 | 1235 | dead | was not used in the 30 day window |
| `roles/solo-founder` | 17 | 1188 | dead | was not used in the 30 day window |
| `roles/startup-cto` | 23 | 1417 | dead | was not used in the 30 day window |
| `roles/tech-lead` | 21 | 1413 | dead | was not used in the 30 day window |
| `sales/sales-super-skill` | 143 | 25593 | thin | was not used in the 30 day window |
| `security/agent-security-super-skill` | 184 | 30199 | thin | was not used in the 30 day window |
| `system/agent-packs` | 120 | 2332 | dead | was not used in the 30 day window |
| `system/brain-locator` | 47 | 1337 | dead | was not used in the 30 day window |
| `system/cross-project-coordinator` | 83 | 1430 | dead | was not used in the 30 day window |
| `system/local-topology` | 62 | 1389 | dead | was not used in the 30 day window |
| `system/session-observer` | 117 | 1649 | dead | was not used in the 30 day window |
| `system/shared-memory` | 124 | 1450 | dead | was not used in the 30 day window |
| `system/swissknifeman-locator` | 54 | 1425 | dead | was not used in the 30 day window |
