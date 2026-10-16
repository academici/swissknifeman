---
name: plan-protocol
bucket: general
version: 4.0.0
description: "Use when an explicitly invoked planner plan command needs a plan layout, status or verb reference."
when_to_use: "Only after explicit planner invocation, when a named plan schema detail is needed."
disable-model-invocation: true
risk: write
persona: oss-dev
tags: [workflow, planning, handoff, routing, multi-model]
requires: []
produces_for: [session-handoff, complex-task-orchestrator]
outputs: ["plans/<PLAN-ID>/plan.json", "plans/<PLAN-ID>/phases/", "plans/<PLAN-ID>/log.jsonl"]
snippets: []
adapters: [claude, codex, cursor, grok]
sha256: ""
---

# Plan Protocol

Canon version: `plan-protocol-v4`. Read and change plan data only through the `plan.py` API
(the project CLI `python3 -I .swissknifeman/launcher.py planner`). Python validates every change and regenerates the
human Markdown views under `views/`. Never read these views, use them as inputs or index them.
The installed marketplace plugin owns this skill and the API together. Activate only for an explicit `planner:plan-design`, `planner:plan-run`, `planner:plan-close`
or `planner:plan-audit` invocation; ordinary work never needs a plan.

## 1. Layout

```text
plans/<YYYY.MM.DD-№N-CODENAME>/
  plan.json  brief.json  log.jsonl  .gitignore          # sources
  phases/<Pn>/phase.json  phases/<Pn>/<Pn.m>.json       # sources
  phases/<Pn>/<Pn.m>/<U#>.json                          # units (optional)
  decisions/<D#>.json                                   # sources
  research/  artifacts/                                 # raw evidence, not Markdown execution contracts
  knowledge/<id>.json                                   # design, runbooks, evidence sections
  views/{index,plan,roadmap,status,handoff,open-questions}.md  # human views; git-ignored, excluded from agent reads/indexing
  context/<Pn.m>.json                                     # generated context packs (git-ignored)
```

Never open or edit plan source files directly; generated human views are not read for work.
Get state with `plan.py next|context --stdout` and the read queries below.
Schemas: `plan.py schema <kind>` (`urn:swissknifeman:task:plan:<kind>:v1`).
`plan.py check` validates JSON. `plan.py render --check` checks human-view freshness separately.

## 2. Identity and references

- Directory id `YYYY.MM.DD-№N-CODENAME`, title `Plan №N — …`, Short ID `PLAN<N>`: allocated by
  `plan.py new`, never guessed, never recycled; archived plans keep theirs.
- Local ids: phase `P<n>`, item `P<n>.<m>`, decision `D<n>`, unit `P<n>.<m>/U<k>`.
- Knowledge and artifact refs: `knowledge/<id>[#section]`, `artifact/<id>`; `plan` and `brief`
  are whole-document query selectors. Prefer `reads[].ref` for local plan data; exactly one of `ref`
  or `path` is required. Optional artifact ids name unique output declarations; inputs cite them.
- Outside the plan directory qualify ids: `PLAN<N>.P2.3`, `PLAN<N>.D4`; across repositories
  `<repo>:PLAN<N>.D4`. Details: [references/work-references.md](references/work-references.md).
- Paths in plan JSON are repository-relative or `@plan/…` (inside the plan directory).

## 3. Statuses

Item `status` (EXACTLY these six): `todo`, `in_progress`, `done`, `done_with_deviations`, `blocked`,
`skipped`. Terminal: the last four. Satisfying a dependency: `done`, `done_with_deviations`, `skipped`.
Phase `design`: `skeleton` → `detailed` (`plan.py design-done`); phase `closed` is written by
`finish` when its last item ends (worst-of result). Plan `status`: `active` → `done` → `archived`.
Decisions: `open` → `accepted` (`plan.py decide`) or `superseded`.
`status`, `result`, `design`, `closed` and identity fields are lifecycle-owned: authoring verbs refuse
them with `FIELD_OWNED`.

## 4. Routing

An item's `route` (`class`: `economy|implementation|frontier`, `effort`: `low|medium|high|xhigh|max|ultra`) is the
minimum. The executor runs under its own session route and declares it with `start --actor
<provider>/<model>/<effort>`; a weaker route is refused (`ROUTE_UNDERSHOOT`), a stronger one is
allowed. The declaration must be the observed session model and effort (runtime settings or environment),
never inferred from prompt text or defaults; when a value cannot be observed, ask the owner. Optional `provider`, `model` and native JSON `settings` select the execution route for
an item or unit; dispatch refuses a different explicit provider/model. Provider model pools
live in `configs/command-routing.json`. A batch runs at the maximum route of its members and
requires compatible explicit selections. `plan-run` itself has no fixed model.

One session owns the attempt of an item: `start` of an `in_progress` item by another session (both
`result.executor` and `--actor` carry a `session`) is refused with `ITEM_OWNED`; resume it from the owning
session or hand it over with `start --take-over` (the `start` event records `data.take_over.previous`).
Without a session on either side `start` resumes as before, and `finish` never checks the owner, so a bridge
can register another session's result with `--executed-by`.

## 5. API verbs

For query shapes, typed links, write rules and parser-derived discovery, read [references/api.md](references/api.md).

| Purpose | Verbs |
|:--|:--|
| author | `new`, `set`, `push`, `apply`, `add-phase`, `add-item`, `add-decision`, `add-document`, `batches`, `design-done` |
| query | `get`, `list`, `events`, `artifact`, `links`, `neighborhood`, `schema [<kind> \| --verbs]` |
| link | `link`, `unlink`, `add-artifact` (validated mutations; exact repeats are no-ops) |
| inspect | `show [<ref>] [--json]`, `next [--json]`, `next <plan> --parallel N [--json]`, `context <item> [--stdout]`, `check [--json]`, `render [--check]` |
| execute | `reconcile` (integrator only), `start <items…> --actor … [--registrar P/M/E] [--take-over]`, `log <ref> --type …`, `finish <item> --status … --check V#=<exit> [--executed-by P/M/E] [--attempt-id ID] [--evidence V#=PATH]` |
| git | `commit <Pn.m\|Pn.m/U#> --role executor\|reviewer\|fix [--path P] [--leave-outside] [--dry-run]`, `commits [<ref>]` |
| bridge | `bridge list`, `bridge <name> <verb> [args…]` |
| owner | `decide`, `supersede`, `grant <GATE> --note …`, `reopen`, `archive` |
| transfer | `export`, `import --file <current-format-snapshot.json> [--replace]` |

Parallel work uses `plan.py next <plan> --parallel N`; lanes never share `task_files` or a dependency path; the integrator alone runs `plan.py reconcile <plan>`.
`next` returns exactly one semantic step: `design-phase`, `run-items` (a ready batch with its
route), `waiting` (dependency, gate, open decision, blocked item), `archive`, or `terminal`.
`start` writes `context/<item>.json`: goal, scope, context, decisions, upstream results, reads (as JSON with complete sections), files, lessons, rules and done-when — the executor's whole input.
`finish --status done` needs every acceptance check recorded with exit 0.
Every operation ends with one scoped `plan.py commit … --role executor|reviewer|fix` (never `git add -A`,
`--no-verify`, amend or push); trailers link commits to the plan and `plan.py commits` lists them.
`settings.evidence: required` makes `finish` demand check evidence (field contract: `schema check-evidence`); a repeated `--attempt-id` with matching status/checks/evidence is a no-op.
Friction (`log --type deviation|blocker|difficulty|assumption|note`) is written only when reality
changes the plan, an assumption or a blocker; it feeds the next items' Lessons.
Queries and `schema` always return `{ok,data|error}`; other verbs use `--output json` for it.
Exit codes: 0 ok, 1 refusal or check errors (text mode: `CODE: message` on stderr), 2 usage.

## 6. Design rules

- A detailed item has summary, why, scope include, inputs (`reads`, `task_files`, inline
  `guidance` or `sections`), at least one acceptance check with an exact command, and
  deliverables (`check` enforces this). Self-contained items need no external reads.
- Long reasoning, algorithms and worked examples live in JSON `sections` or schema-backed
  `knowledge/<id>.json`; JSON context includes full selected sections. Plan Markdown never
  supplies agent input, including historical handwritten carriers. Repository code/docs remain usable.
- Batches group items that share files or context; `mode: required` only for an atomic group.
- Owner gates: `authority: {kind: owner_gate, gate: X}`; `start` refuses until `plan.py grant X`
  records the owner's message.
- Context scope: a knowledge document or accepted decision reaches an item's pack only through `applies_to`
  (item or phase) or `global: true`; `settings.context_pack: scoped` (default for new plans) drops unbound
  content, `legacy` still sends it everywhere. Bind with `plan.py link <plan> knowledge/<id> <Pn|Pn.m> --kind applies_to`.
  Keep phase records out of `brief` and stale projections out of `plan.sections`; `design-done` reports pack sizes.

## 7. Review and audit

Review is plan-controlled: `none` disables it, `self` names executor checks, and `requested`
declares independent review. New items default to `none`; preserve an existing owner-requested review. `--review` or an
explicit owner request adds one read-only review item at the end of the scope. `planner:plan-audit`
runs only on explicit owner invocation and writes a verdict file plus a `note` event.

## References

- [references/common-principles.md](references/common-principles.md) — shared rules for every plan command.
- [references/design-mode.md](references/design-mode.md), [references/execution-mode.md](references/execution-mode.md),
  [references/review-mode.md](references/review-mode.md) — per-command notes.
- [references/work-references.md](references/work-references.md) — Short IDs and qualified references.

Reviewer selection: see the planner package's references/reviewer-selection.md.

## JSON orchestration and snapshots

Use item `units` as the subtask graph. Each unit declares `kind` (`preparation`, `implementation`,
`review`, `verification`, `integration`, `command`), `depends_on`, optional `parent`, instructions,
owned `files` (empty for read-only work), checks, outputs and `route`. Route may select an explicit
`provider`, `model`, effort and provider-native JSON `settings`. No model is launched by the API.

Plan → phase → item `orchestration` sets `strategy: dag|sequential`, optional `max_parallel`,
instructions and an optional `scenario` (`^[a-z][a-z0-9-]*$`: the name of a run-policy profile of an execution engine, or
`solo` for the current session). The scenario of an item is the first one set on the item, its phase or the
plan, then the config key `orchestration.by_class.<route class>`, then `orchestration.default_scenario`
(`solo`); the context pack reports it as `orchestration.scenario` with `orchestration.scenario_source`
(`item|phase|plan|config:by_class|config:default`). The planner does not check that a profile of that
name exists. `unit <plan> <item> next` reports ready nodes as JSON; `unit … <U#> context` returns
the full JSON worker input. Dispatch writes `<U#>/brief.json`. All declared units must be accepted
or explicitly rejected before an item finishes. Children finish before their parent.

`add-document --file document.json` adds knowledge; `get/set … knowledge/<id>` reads or edits it.
`apply --file patches.json` validates coordinated `{ref, patch}` edits before writing.
`export` returns the complete current-format graph and event log; `import <directory> --file
snapshot.json` restores a validated graph, preserving historical state and supporting evidence.
`--replace` is required to restore an existing JSON plan. Import never interprets Markdown.
Bridges: `plan.py bridge list`; a bridge projects plan data for an external executor (see the bridge's README).
The planner finds bridges through the `bridges.roots` setting of its configuration.

`plan.py --output json <verb>` prints exactly one envelope for every verb, validated against
`schemas/plan/v1/envelope.schema.json` (kind `envelope`) before it is printed:
`{"ok": true, "data": <verb result>}` or `{"ok": false, "error": {"code", "message", "issues"?}}`.
Exit codes stay 0 / 1 (refusal) / 2 (usage). Input is validated by the API (ids, refs, paths, documents),
never by the caller; plan files are written only by `plan.py` verbs.

There is no read count, inline-section cap, lesson truncation, phase-size quota or spend gate.
Read supporting code/docs as necessary; keep the contract self-contained and add newly discovered
facts to JSON. Never generate plan-local `AGENTS.md`/`CLAUDE.md` instruction carriers.
