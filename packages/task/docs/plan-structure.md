# Task plan structure - layout v3

A plan lives in `plans/<PLAN-ID>/` (`YYYY.MM.DD-№N-SLUG`, Short ID `PLAN<N>`, archived plans in
`plans/archive/`). JSON is the only source of truth; every JSON document validates against a schema in
`packages/task/schemas/plan/v1/` (Draft 2020-12, closed profile: `additionalProperties: false`, unknown
schema keywords are an error). Plans are changed only through `scripts/plan.py` - it validates, writes
canonical JSON atomically under a lock and regenerates the views.

## Layout

```text
plans/<ID>/
  plan.json              goal, context, rules, phase order, settings
  brief.json             owner messages (verbatim) and extracted requirements
  log.jsonl              append-only event log (lifecycle events + friction)
  decisions/<D#>.json    decisions and open questions
  phases/<Pn>/phase.json goal, scope, validation, batches, closure
  phases/<Pn>/<Pn.m>.json  one item: stable spec + volatile result
  phases/<Pn>/<Pn.m>/<U#>.json  optional work units; <U#>/ holds a generated brief.md and reports
  research/ artifacts/ findings/ backlog/   free-form supporting files (referenced as @plan/...)
  .gitignore             `context/` and `.lock`
  index.md plan.md roadmap.md status.md handoff.md open-questions.md AGENTS.md CLAUDE.md context/
                         generated - never edit, never read for work
```

## Schemas

| Schema | Document | Notable fields |
|:--|:--|:--|
| `plan` | `plan.json` | `id`, `short_id`, `status` (`active, paused, done, archived`), `goal`, `context`, `rules`, `phases`, `settings {design_audit, scout}` |
| `brief` | `brief.json` | `messages[]` (M#), `requirements[]` (B#, `source`, `owners`), `environment` |
| `phase` | `phase.json` | `design` (`skeleton, detailed`), `scope`, `depends_on`, `pitfalls`, `validation`, `items`, `batches`, `contract`, `assurance`, `closed` |
| `item` | `<Pn.m>.json` | `status`, `summary`, `why`, `scope`, `depends_on`, `reads`, `task_files`, `artifacts`, `rules`, `guidance`, `validation`, `route`, `review`, `authority`, `rag`, `units`, `result` |
| `decision` | `<D#>.json` | `status` (`open, accepted, rejected, superseded`), `question`/`options` or `decision`/`rationale`, `consequences`, `applies_to`, `evidence`, `actor` |
| `unit` | `<U#>.json` | owned `files`, `depends_on`, `checks`, `route`, `mode` (`self, delegate, either`), `status` |
| `log-event` | `log.jsonl` line | `type`, `item`/`phase`, `summary`, `impact`, `next`, `actor`, `data` |

`task_files` and `related` are hints, not limits. Paths are repository-relative; `@plan/` means relative to
the plan directory; `..` is rejected.

## Statuses

Item: `todo, in_progress, done, done_with_deviations, blocked, skipped`. `blocked` does not satisfy a
dependency; `skipped` does and needs an accepted decision. `status`, `result`, `phase.closed`,
`phase.design` and `plan.status` are owned by the lifecycle verbs; `set` refuses them (`FIELD_OWNED`).
A phase closes when all items are terminal, with the worst result (`blocked > done_with_deviations >
done`); the plan becomes `done` when all phases are closed.

## Batches and route

Each phase lists `batches` in execution order; each item is in exactly one. `recommended` batches may be
split; `required` ones run as one. `plan.py next` names the next batch with its route: the highest model
class (`economy < implementation < frontier`) and effort (`low < medium < high < xhigh`) of its members.
`start --actor <provider>/<model>[/<effort>]` is checked against the model pool in
`configs/command-routing.json`: undershoot is refused (`ROUTE_UNDERSHOOT`), an unknown model only warns.

## Lifecycle

`new → add-phase/add-item/add-decision/set/push/batches → check → design-done → start → (log) → finish
→ phase closes → … → archive`. Owner gates (`authority.kind=owner_gate`) need `plan.py grant` with the owner's
message quoted in `--note`. `finish --status done` needs every acceptance check recorded with exit 0.
`reopen` returns a finished item to `todo` with a reason; `archive` moves a done plan to `plans/archive/`.
Refusals print `CODE: message` and write nothing.

## Log and friction

`log.jsonl` is append-only. The API writes lifecycle events (`plan_created, design_done, start, finish,
phase_closed, gate_granted, decision, archived, migrated`); agents add only friction with
`plan.py log <plan> <item> --type deviation|blocker|difficulty|assumption|note --summary "…"` when the plan,
an assumption or a blocker changes. The next context pack replays the latest friction as Lessons.

## Context pack

`start` (and `plan.py context <plan> <item> [--stdout]`) writes `context/<item>.md` in a fixed order:
Task, Goal, Scope, Context, Decisions, Upstream results, Reads (sections of `.md` files inlined, others
listed with why), Files, Artifacts, Lessons, Rules, Done when and an optional Scout map. Empty sections
are omitted. Size is reported, not gated.

## Views and ignore rules

`index, plan, roadmap, status, handoff, open-questions` are rendered from JSON by `templates/plan/` after
every mutation; `plan.py render [--check]` rebuilds or detects stale files, and `check` reports `stale_view`.
Every provider is told to ignore generated files: the global instruction `task.plan-files`, the plan-local
`AGENTS.md`/`CLAUDE.md`, and harness hooks (`lifecycle.plan-guard` blocks writes to generated files,
`lifecycle.plan-regen` runs `check` and `render` after JSON edits).

## Work units (opt-in; verbs arrive with P4)

The schema lets an item be split into units in `phases/<Pn>/<Pn.m>/`: each unit owns disjoint `files`, has a minimum
route and a lifecycle `todo → dispatched → returned → accepted | reworked | rejected`. The item executor
stays the integrator: it reviews and tests every returned piece and alone finishes the item. `check`
enforces unique ids, acyclic `depends_on` and non-overlapping `files` of independent units.

## Contracts and portability

`plan.json.contracts` notifies other plans of exported/consumed contracts; cross-plan references use
`PLAN7.P2.3` or `repo:PLAN7.D4`. Plans in this repository are gitignored (`plans/`); product commits
contain only code and docs, plan bookkeeping stays local.
