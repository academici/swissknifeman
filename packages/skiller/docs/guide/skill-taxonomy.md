# Taxonomy and skill granularity

Package philosophy: **how and by what principles to form registry skills**. Complements
[skill anatomy](./skill-anatomy.md) (file structure) and [creating skills](./creating-skills.md)
(procedure) — this document is about **granularity** (how much to split) and **placement** (where to put).

The registry has grown to ~190 skills. Without discipline, he degrades in two ways: his skills become
dump («one skill about everything») and become polluted by someone else's (stack/project-specific in shared buckets,
which loads for everyone). The doctrine below prevents this.

## Unit and area

- **Skill = one cohesive ability.** If the description contains «and … and …» about different topics -
  are two skills. If two skills overlap in content, this is one (expand the existing one,
  see skill-authoring «Step 0»).
- **Bucket = large role area** (engineering/infrastructure/business/…), not «folder for each
  skill». Splitting a bucket makes sense only when there are actually different consumer roles inside.

## Where the skill lives - three levels of placement

| Level | What's there | Channel |
|:--|:--|:--|
| **general** (cross-stack) | Applies to ANY stack/project: discipline, token economy, naming conventions, handoff | Connected by task; CORE — separate minimal list |
| **stack-bucket** (`php`/`frontend`/`devops`/…) | Stack Specifics/framework: Laravel, Vue, Docker, specific packages (`azguard/azguard`, `laravel-data-layer/laravel-broadcasting`) | by project type profile |
| **project-local** (`<project>/.claude/skills/`) | Project-specific business logic: domain classes, enum's, `App\…`, design workflow | not in the registry at all |

> **Rule general.** Bucket `general` is not equal CORE. B CORE includes only four skills from
> `configs/core-policy.json`: `anti-drift`, `context-economy`, `session-handoff`, `verify-claims`.
> The rest are connected according to the task; `plan-protocol` is also available via Task runtime.
> At the start Codex lists the metadata of active skills, and reads the bodies upon activation.

> **Rule project-local.** Specific project name/of the domain class in the body of the skill is a signal that
> it has no place in the general registry. Universal core (if available) summarize and leave in stack-bucket;
> purely design take into `<project>/.claude/skills/` (vendor/local-channel).

## Life cycle: init-only vs always-loaded

Not all skills are needed all the time. Skill that helps **once** (select stack/packets when
initialize the project, plan the structure), should not hang in the constant distribution - otherwise it
just takes up the context. Mark these `lifecycle: init` in frontmatter and **do not put in CORE/default
profile**. Always-loaded — working skills relevant to the course of tasks.

## Lean SKILL.md (progressive disclosure)

SKILL.md — **entry point**, and not an encyclopedia. This coincides with the recommendation Anthropic by
skill-authoring: easy entry + loading of parts on demand.

- **Body** (landmark **≤150 lines**): what is it, when to activate, key algorithm, checklist.
- **Details** (long examples, tables, templates, reference books) → `references/`/`snippets/`.
- `validate.sh` **gently warns** about bodies above the threshold - this is a signal to take out the details, not a prohibition.
- Why: when there are a lot of skills in a project, bloated bodies completely eat up the context. Thin entrance +
  references keeps the budget under control.

## Router-skill (thin orchestrator «background» cluster)

When a topic has **family of specialized sub-skills** (example: `docker` → `docker-php`,
`docker-postgres`, `docker-dev-prod`, `docker-services`, `docker-vite`, `makefile`), top skill
do **thin router'ohm**, and not «encyclopedia of expertise»:

- **`description` = trigger-route**, and not «advanced expertise»: «Router for X: directs to the right
  sub-skill (…). Use when the task involves X». So it works on the topic and immediately takes you to the desired sub-skill.
- **Body = routing table** «need → sub-skill» + assembly order (DAG is hardwired into `requires`/
  `produces_for` sub-skills). Deep expertise - in `snippets/`/`references/`, is loaded on demand.
- **`risk: read`** (router does not write himself - he directs; write sub-skills).
- Effect: «background» cluster is resident only by description -router'ohm; specialists are loading on-demand
  (progressive disclosure at family level). We climb into the cluster only when necessary.

## Granularity ↔ distribution channel

- **connect** (marketplace) = **bucket-granular**: the entire bucket is connected (plugin = bucket).
  You cannot sub-select an individual skill. Rough, quick setup.
- **vendor** (physical. transfer) = **skill-granular**: `include: ["bucket/skill"]` — exactly needed
  positions in repo + lock. Fine tuning.

Output: **fine-tune the dialing via vendor**; connect — when satisfied «whole bucket».
Split the bucket into sub-plugins just for the sake of connect-choice is a last resort (marketplace-churn,
orphan `enabledPlugins` from consumers).

### Move migration/renaming buckets

Moving a skill between buckets or renaming a bucket - **breaking** for already connected
projects on the channel connect: key `<bucket>@swissknifeman` in their `.claude/settings.local.json`
becomes «orphaned». `skiller connect` this **detects and warns** (drift), but
does not fix automatically - consumer restarts `connect` with current profile/set.
Vendor-projects are more sustainable (skills are addressed along the path `bucket/skill`), but `.swissknifeman/config.json`
with an outdated bucket name will give an error - update manually. Any such change → mark
**breaking** in CHANGELOG + migration note.

### Border git/github-skills

Universal commit-hygiene (`git status`/`diff`, message format, prohibit `--no-verify`) lives in
`general/git-commit-rules` — needed **everyone** projects, not only GitHub. GitHub/OSS-specifics (Issue→PR→
Tag→Release, SemVer-oracle, templates issue/PR, governance-documents) — in `oss-dev`
(`github-flow`/`gh-review`/`oss-governance`/`release-engineering`). Do not duplicate: interpretation
commit type → bump version is described only in `oss-dev/github-flow`, `git-commit-rules` references.

## `context: fork` — selection criterion (axis B, session length)

Body `SKILL.md` enters the session with one message and remains there until the end of the turn (first-party:
«stays there for the rest of the session», `code.claude.com/docs/en/skills` §Skill content
lifecycle) — client does not reread the file. `context: fork` takes the body into a forked
subagent context instead of the main session - but the doc directly warns: field «makes sense
only for skills with an explicit task»; skill book given to the subagent is returned
**empty** (no task - nothing to accomplish and nothing meaningful to answer).

**Criterion - procedural skill with a task, not a reference book:**

- [ ] The body gives **executable procedure** (numbered steps/algorithm) with final
      **artifact or testable result** — not only conventions/best practices for
      help along the way.
- [ ] Task **is self-sufficient**: does not require conversation history of the current session and does not read
      state of the session itself (it cannot be executed «in vacuum» with one artifact on the input -
      the forked subagent can search for such an artifact himself, using file tools).
- [ ] Task side effect - **local** (repository files, git-status worktree),
      not writing to an external system without being able to safely check the response (ticket-
      tracker, etc. - a fork of such skills greatly complicates the test on the stand and remains outside
      of this passage is not prohibited forever).
- [ ] Skill that carries the canon for the MAIN session (standing instructions read multiple times
      session - `plan-protocol` and the entire circuit `planner:plan-*`, supervised CORE), is NOT forkable.
- [ ] Doubts about the class - **do not fork**: false fork gives empty subagent response in
      prod; a false refusal is only worth lost savings (asymmetry cost).

Checking before inserting a field is MANDATORY individually on a live client (auto-activation AND
explicit `/skill-name`), not a batch: registry §P3.4,
.

## `when_to_use` + description compression (axis A, listing entry)

`description` and `when_to_use` — ONE listing entry (`name` + `description` + ` ` +
`when_to_use`, cap first-party 1 536 char; `when_to_use` — «Appended to `description` in the
skill listing», code.claude.com/docs/en/skills §Frontmatter reference). Transfer
trigger phrases from `description` in `when_to_use` by itself does NOT provide savings - it does provide savings
CUMULATIVE record compression only (`scripts/validate.sh` length gates/trigger
consider this exact amount, P3.5).

**Formula** (verified Perplexity + first-party
doc): **«[what does the skill do]. Use when [explicit trigger phrases/synonyms]»** — third party,
the most discriminating signal first. When editing an existing record that is over budget -
squeeze `description` (remove the implementation enumerations, leave the domain+result), move
trigger condition in compact `when_to_use`; edit both fields in ONE pass, not «first
transfer, then someday we will compress».

Debt bucket prioritization (`scripts/desc-trigger-burndown.txt`) — usage-signal
`skiller bucket-audit --description-debt` (loaded_count) × share of record in the general listing
(`tier0`/amount `tier0`), NOT alphabet and NOT bucket size. JSON-projection
`description-trigger-priority/v1` preserves the denominator and distinguishes
`observed-skill-call`, `resident-only` and `unobserved`: lack of direct call is not
a verdict of non-use or a reason to rewrite skill. Invalid ratchet (missing,
malformed, duplicate or stale key) fail-closed for this filtered projection only;
normal `bucket-audit` remains inversely compatible.

## Shooting Ranges `model:`/`effort:` (axis B, active move cost)

`model`/`effort` in frontmatter override model/effort sessions **for the remainder of the CURRENT
progress** (RAG:✅ first-party, «not saved to settings») — this is NOT a skill body setting, but
command for the client to change the performer while the skill is active.

**Applicability gate (is required BEFORE choosing a shooting range - many skills should not carry override
at all):**

- [ ] Skill - **discrete constrained problem** (interview, template, one-time run), which
      naturally finish and return to your previous job - NOT advisory/meta-discipline,
      applied IN PARALLEL to the main task of the session (`anti-drift`, `context-economy`,
      `session-handoff`, `skills-ssot` — discipline/checklist on top of current work, not
      separate task). Override on advisory-skill forces a model change for the rest of the turn
      for the sake of a third-party checklist, breaking the range of the MAIN task - the skill itself does not benefit from this,
      and the session loses its shooting range. **Don't force override on advisory-class - not a space, but
      find P3.5** (`findings/P3-desc-burndown.md` §Shooting Ranges).
- [ ] `plan-protocol` and the entire circuit `planner:plan-*` — exception by design: EVERYONE route
      item'and is already itching §3 Routing plan (`plan-run` reads it),
      blanket override on top of this is a second, conflicting source of truth. Skill carries
      `Exec`-table as canon, not native `model:`/`effort:`.

Shooting range - by skill class (not by `risk:` — the one about the side effect of the action, not about
depth of judgment), support the same ladder as Routing plan (`plan-protocol` §9):

| Job class | Example | `model` | `effort` |
|:--|:--|:--|:--|
| Discrete judgment problem without open solutions (interview, assessment, analysis) | `spec-interview` | `sonnet` | `medium` |
| Discrete mechanical problem (template/structure according to the finished form) | `task-brief-template` | `sonnet` | `low` |
| Advisory/meta-discipline, active PARALLEL to the main task | `anti-drift`, `context-economy` | — (without override) | — (without override) |
| Canon with its own routing table (`§3 Routing`/`Exec`) | `plan-protocol` | — (without override, route - by item'y) | — (without override) |

Register run - mechanical application ONLY after manual gate classification
applicability above (one class error per CORE-skill forcing shooting range for EVERY fleet project, where
it is resident) — rollout to the rest of the registry (`general` the bucket is completely closed P3.5,
) continues along the same lines usage-prioritization, as
`when_to_use`-debt.

## Checklist for posting a new/right skill

- [ ] This **one** ability? No intersection with existing (otherwise expand it).
- [ ] Universal → `general` (and really cross-stack, not «basically PHP»)?
- [ ] Stack-specific → corresponding stack-bucket?
- [ ] Project-specific (names `App\…`/domain) → **project-local**, not in the registry?
- [ ] Needed once → `lifecycle: init`, out CORE/default?
- [ ] Body lean (≤~150 lines), details in `references/`/`snippets/`?

Related: [creating skills](./creating-skills.md) (procedure+review), [profiles](./profiles.md),
[anti-bloat methodology](./methodology.md).
