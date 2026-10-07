# Task JSON plans — layout v4

JSON owns plan contracts, instructions, orchestration and outcomes. Agents use
`python3 <TASK>/scripts/plan.py` or read JSON. Human Markdown is generated from templates
under `views/` and excluded from agent input and indexing. The API never parses those views.

```text
plans/<YYYY.MM.DD-№N-SLUG>/
  plan.json  brief.json  log.jsonl
  phases/<Pn>/phase.json
  phases/<Pn>/<Pn.m>.json
  phases/<Pn>/<Pn.m>/<U#>.json             # optional subtasks
  phases/<Pn>/<Pn.m>/<U#>/brief.json       # generated worker input
  decisions/<D#>.json
  knowledge/<id>.json                     # complete design/runbook/evidence sections
  artifacts/ research/ findings/ backlog/ # raw supporting evidence
  views/                                 # template-generated human views
  context/<Pn.m>.json                     # generated executor input
  .ignore .cursorignore .gitignore
```

Schemas in `schemas/plan/v1/` use Draft 2020-12 and markers
`urn:swissknifeman:task:plan:<kind>:v1`. Document shapes are closed; provider-native `route.settings`
and event `data` carry arbitrary JSON. Unknown schema keywords are rejected. Paths are
repository-relative or `@plan/…`; `..` is rejected. Stable identities may contain leading zeroes.

| Document | Main fields |
| --- | --- |
| plan | identity, goal, context, rules, non_goals, phase order, settings, contracts, sections, orchestration |
| brief | owner quotes or explicitly marked source records, requirements, constraints, environment, sections |
| phase | design, goal, scope, contracts, dependencies, pitfalls, validation, ordered batches, closure, sections |
| item | status, summary, why, scope, reads, files, rules, guidance, checks, outputs, route, review, authority, units, result |
| unit | kind, goal, files, reads, checks, instructions, dependencies, parent, route, mode, outputs, command, status, outcome |
| decision | status, question/options or decision/rationale, applicability, evidence, supersession, sections |
| document | id, title, sections, applies_to, provenance; stored as `knowledge/<id>.json` |
| snapshot | complete plan graph and events, used by export/import |

A section is `{id, title, text}` and retains its complete body, including code/examples.
A knowledge read can select its section id or exact title. A document without `applies_to`
is global context; otherwise it applies to the named phases/items.
An item read names exactly one of `path` or `ref`. Local refs include phases, items,
units (`P1.1/U1`), decisions, `knowledge/<id>[#section-id]` and `artifact/<id>`.
The separate `section` key accepts a knowledge section id or exact title; it cannot
accompany a ref fragment. `check` resolves both ref forms, and `start`
refuses an unreadable required section in a ref read with `READ_MISSING` before
writing any state.

An item's optional `skills` is a unique list of skill or capability names, such as
`skill-creator` or `blender:mcp-blender`. These names declare what the executor must load;
the plan API does not install or launch them.

## API

```bash
python3 <TASK>/scripts/plan.py new --codename DEMO --title Demo --actor provider/model/high --message-file owner.txt
python3 <TASK>/scripts/plan.py show PLAN1 plan
python3 <TASK>/scripts/plan.py context PLAN1 P1.1 --stdout
python3 <TASK>/scripts/plan.py --output json next PLAN1 --json
python3 <TASK>/scripts/plan.py apply PLAN1 --file coordinated-patches.json
python3 <TASK>/scripts/plan.py export PLAN1 > snapshot.json
python3 <TASK>/scripts/plan.py import plans/<existing-id> --file snapshot.json
```

Author with `add-phase`, `add-item`, `add-decision`, `add-document`, `set`, `push`, `batches`.
Knowledge references for show/set are `knowledge/<id>`. `apply` accepts a non-empty array of
`{ref, patch}` objects and validates their combined graph before writing. Identity and lifecycle
fields are protected from authoring edits. Refusals write nothing and carry a stable code.
`--output json` provides an `{ok, data}` or `{ok: false, error}` envelope.

`export` includes every current JSON document and the event log. `import` validates a complete
snapshot, stages the destination with supporting files, then publishes it with rollback on
publication failure. Existing JSON requires `--replace`. Historical dates, states and evidence
survive import exactly. Import is a data API; source-format conversion is never runtime behavior.

## Named bridges

The Task core knows no partner tool by name: every link to one lives in `bridges/<name>/` with a
`bridge.json` manifest (`plan.py schema bridge`). `plan.py bridge list` shows the bridges found by
scanning `bridges/`; `plan.py bridge <name> <verb> [args…]` runs a declared entrypoint and passes its
output and exit code through. A bridge may import Task modules but reaches its partner only through
the partner's public CLI or files. `tests/test_boundary.py` keeps the core clean; its temporary
`tests/boundary_allowlist.json` may only shrink. `validate.sh` also runs `bridges/*/tests`.
Bridges: `plan.py bridge list`; a bridge projects plan data for an external executor (see the bridge's README).

## Attempts and evidence

`plan.py commit PLAN1 P1.1 --role executor` makes one scoped Git commit containing the item's
declared `task_files` and operation-owned plan files; a unit ref uses its `files` instead.
Roles are `executor`, `reviewer` and `fix`; reviewers commit operation-owned plan files,
knowledge reports and artifacts.
Foreign dirty paths return `OUTSIDE_SCOPE`; `--leave-outside` preserves them, including staged
content. Use repeated `--path` for explicit extra paths and record a deviation with `plan.py log`.
`--dry-run --json` previews paths, message and `paths_digest` without writes.
Plan and Git index locks protect the operation; a private index keeps failed staging/commit
attempts from changing existing staged work. Git hooks remain enabled.

Messages use `task-plan-commit/v1` with `Plan`, `Plan-Ref` and `Plan-Role` trailers.
Optional `settings.commit` sets `scope` and attribution `trailers`; CLI overrides include
`--type`, `--scope`, `--summary`, `--trailer` and `--actor`. The helper prints the resulting SHA
without changing the journal afterward. Existing `finish --commit SHA` remains available for
commits made before finish. Plans receive `.gitattributes` with `log.jsonl merge=union`;
parallel journal changes integrate through local Git merge/rebase, with timestamps allowed
to appear out of order. GitHub web-merge does not apply `merge=union`: integrate parallel plan
branches locally, then push. `union` does not resolve conflicts in shared JSON (`plan.json`,
`phase.json`).

`plan.py commits PLAN1 [P1.1[/U1]] [--role executor|reviewer|fix]` reads the commits linked to a plan
by `Plan` trailers (read-only JSON envelope, schema `plan.py schema read-commits`); an item ref
includes its units. A named bridge may return the same commit in its partner's result format
(see the bridge's README).

`start --registrar` records the caller separately from the executor; `finish --executed-by` records and validates the executor's route.
A matching `--attempt-id` with the same status/checks/evidence registers once; conflicting results return `ATTEMPT_CONFLICT`.
`finish` / `unit accept --evidence V#=PATH` accept check evidence; `settings.evidence: required` makes finish require evidence for every acceptance check (default: optional).
The check-evidence file follows Task's field contract (`plan.py schema check-evidence`): `$schema` is any non-empty marker, so files of an external executor pass without conversion; the key fields (`subject`, `check_id`, `candidate.head`, `procedure`, `exit` or `verdict`) are checked.

## Lifecycle and scheduling

Items: `todo → in_progress → done | done_with_deviations | blocked | skipped`.
Blocked items do not satisfy dependencies; skipped items require an accepted decision.
Phases progress `skeleton → detailed` via `design-done`. A detailed item needs real scope,
acceptance checks, deliverables and supporting input or self-contained guidance/sections.
Skeleton scope may be empty. `finish` closes a terminal phase and finishes a plan only when all
phases close without blockers. `reopen` clears the affected item/phase closure.

Batches cover every phase item exactly once and preserve execution order. Recommended batches
can be split; required batches are atomic. Explicit phase dependencies express parallel branches.
An item may depend on a concrete item of another phase instead of the whole phase, and a phase may declare
`depends_on: []` and rely on item dependencies; `check` reports a cycle that crosses an item and a phase
dependency as `dependency_deadlock`. `next --parallel N [--json]` is a read-only ready set across the whole
plan: lanes for items whose dependencies are met, `task_files` do not overlap with running or selected lanes
(an item without `task_files` conflicts with every lane), plus `running`, `conflicts`, `waiting` and `deferred`;
plain `next` is unchanged. When every item of a phase is terminal but the phase is not closed (lanes finished
in separate worktrees), the integrator runs `plan.py reconcile <plan>`: it closes such phases and the plan,
idempotently and without a second writer. `check` warns with `phase_unclosed` and `phase_closure_stale`.
Lanes are integrated locally and one at a time (GitHub web-merge does not apply `merge=union`).
`next --json` reports one semantic action and its required route. Owner gates are declared in
`authority`, granted through `grant --note` with authentic owner permission.

An `external_gate` declares an identity (`gate` or `label`) and a source `scope` controlled
outside the plan. `next` waits for it, `start` refuses with `EXTERNAL_GATE`, and owner
`grant` cannot satisfy it. Reconcile the external evidence before changing its authority
through the authoring API.

Routes specify minimum `class: economy|implementation|frontier` and effort
`low|medium|high|xhigh|max|ultra`. Optional `provider` and `model` select an exact executor;
`settings` carry native JSON options. `start --actor` and unit dispatch reject mismatched explicit
selections or known capability/effort undershoots. Unknown model classes are reported honestly.
No process is launched merely because it appears in JSON.

## Orchestration units

An item lists unit IDs; documents live under its workspace. `kind` names preparation,
implementation, review, verification, integration or command work. `files` is write ownership
and may be empty for read-only work; `outputs` describes produced evidence. Command units carry
an exact command check. `parent` permits nested subtasks without introducing another lifecycle.

Plan → phase → item `orchestration` overrides `strategy: dag|sequential`, instructions and an
optional owner-selected `max_parallel`. DAG scheduling uses dependencies and disjoint write
ownership. Sequential scheduling orders siblings. A parent waits for its children. Cycles,
unknown dependencies/parents and unordered overlapping write sets are errors.

`unit … next` returns ready units as JSON; `unit … <U#> context` returns a full JSON worker brief.
`dispatch --agent` records the executor and writes `brief.json`. A self unit belongs to the item
executor. State is `todo → dispatched → returned → accepted | rejected`; `rework` redispatches
with new instructions. Every declared unit must be accepted or explicitly rejected before its
item completes, including units never started. Python reports work and stores results; a provider
orchestrator is responsible for launching it and performing checks.

## Context, views and delivery

`context --stdout` returns the full plan/brief, phase and item, applicable decisions and knowledge,
upstream results, selected supporting sections, friction history, units and readiness. `start`
writes the same JSON under `context/`. There is no read count, inline cap, lesson truncation,
phase-size quota or spending gate. Supporting code/docs can be read when needed.

`check` validates JSON schemas, references, graph invariants and recorded state. It never reads
human Markdown and does not depend on view freshness. `render --check` separately detects stale
human views. Templates produce overview, roadmap, status, handoff, questions and complete
brief/phase/item/unit/decision/knowledge views. No plan-local `AGENTS.md` or `CLAUDE.md` is created.

Missing required reads warn once the item's dependencies are terminal. Terminal items and
externally gated items do not warn about retired or externally controlled inputs. Dependency
`task_files`, output artifacts and output directories count as planned producers; wildcard
and brace-pattern reads are excluded from this advisory existence check.

Search/index ignores exclude plan Markdown, `views/` and generated `context/`; Serena provisioning applies
these exclusions even when gitignored files are indexed. Harness guards protect generated
views, JSON packs and worker briefs from hand edits. References from reads/examples into
human views or any plan-local Markdown are rejected. Design and review prose belongs in JSON;
historical Markdown receipts may remain immutable evidence for people.

The Task marketplace plugin delivers `skills/plan-protocol` with the engine, schemas, templates
and provider commands. The protocol is explicitly invoked and shares the same installed package
as its API. Temporary migration tooling has been removed from the active package tree;
source-format conversion is not a runtime compatibility layer.
