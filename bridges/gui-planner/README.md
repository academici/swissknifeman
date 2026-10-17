# gui-planner

Bridge between the GUI host (`gui`) and the planner: the plans of a project in human form — list, overview, phases,
board, dependency graph, items with their evidence, decisions, timeline and raw documents. It is a hub unit
(`unit.json`, kind `bridge`) that contributes `gui.json` (`contribution/v1`) and answers through the aicore plugin
protocol (`extension.json`, points `gui:query` and `gui:command`). It has the queries, the edit forms and the commands
(item and phase edits, decisions, reopen, grant, log).

The bridge only calls the planner command line (`$SKM_UMBRELLA planner --output json ...`, else `swissknifeman` on
`PATH`, working folder = the project) and moves fields of its JSON into `view-data/v1`; it imports no module. It
computes no progress, status or dependency: progress is the one of `planner plans`; the only logic is the layout of
items into board columns by `status` and the map of a planner status to a view status (`done`,
`done_with_deviations`, `skipped` → `ok`; `in_progress` → `warn`; `blocked` → `fail`; `todo` and anything else →
`unknown`). Every string of a plan is text (control and ANSI characters removed); markdown goes to the host sanitizer.

| Query | Scope | Planner command | View |
| --- | --- | --- | --- |
| `gui-planner.plans` | project | `plans` | `resource-list`: name, status, progress (integer percent of items done), phases closed |
| `gui-planner.overview` | plan | `show --json`, `get plan`, `plans` | `resource-detail`: plan, status, goal, progress, next; sections goal, context, rules |
| `gui-planner.phases` | plan | `show --json` | `resource-list`: design, result, progress (integer percent), items done per phase |
| `gui-planner.board` | plan | `list item [--phase]` | `board`: a column per status (`todo`, `in_progress`, `blocked`, `done`, `done_with_deviations`, `skipped`), `other` only for a status the planner does not define |
| `gui-planner.graph` | plan | `list item [--phase]`, `get` per item | `dependency-graph`: `depends_on` → `blocks` (dependency → dependent), `related` → `related`; an edge to an item outside the selection is dropped |
| `gui-planner.item` | item | `get Pn.m` | `resource-detail`: title, status, phase, route, review, authority, depends on; sections summary, why, result |
| `gui-planner.decisions` | plan | `list decision`, `get D#` | `resource-list`: id, title, status, date |
| `gui-planner.evidence` | item | `get Pn.m` | `resource-list`: recorded checks, artifacts and evidence paths (an empty list when there are none) |
| `gui-planner.timeline` | plan | `events --limit 200 [--item]` | `timeline`, newest first |
| `gui-planner.raw` | plan | `get <ref>` | `markdown`: the file path and the document in a fenced `json` block; `ref` is `plan`, `brief`, `Pn`, `Pn.m` or `D#` |

Form queries and the model picker:

| Query | Scope | Source | View |
| --- | --- | --- | --- |
| `gui-planner.item-form` | item | `get Pn.m` | `schema-form`: form `gui-planner.item`, the document and its revision |
| `gui-planner.phase-form` | plan | `get Pn` | `schema-form`: form `gui-planner.phase` |
| `gui-planner.models` | project | aicore `load_model_catalog()` | `resource-list` of `provider/model` rows (provider, model, default of class, roles); `MODEL_CATALOG_UNAVAILABLE` when aicore or its catalog cannot be read |

The route `plans/:plan_id/items/:item_id/edit` shows `gui-planner.item-form` in the `schema-form` view; the item page links to it
(an "Edit" section, built from the project id of the context) and saving runs `gui-planner.item-set`.

A model already written in an item but absent from the list is shown as it is (the UI marks it `drift`); nothing
replaces it. `gui.json` `forms[]` (`gui-planner.item`, `.phase`, `.decision`) annotate the planner schemas by JSON
pointer (groups, widgets, readonly lifecycle fields); the host does not load the planner schema.
`tests/fixtures/plan-enums.json` is the enum table (route class/effort, review mode/class/effort, authority kind, rag
need/status) read from `planner schema item`; the frontend checks its own table against it. Regenerate it with
`SKM_REGENERATE_FIXTURES=1 bash scripts/test.sh`.

Commands (all `exec: invoke`, effect `plan.write`; the adapter builds the planner argv from checked values, each
element a literal or one value, free text as `--flag=value`, so a value that starts with `-` is never an option):

| Command | Risk / confirmation | Planner call |
| --- | --- | --- |
| `gui-planner.item-set` | medium / risk-based | `get --fields status` (refused with `ITEM_IN_PROGRESS`), `set <item> --json <patch> --expected-revision=<rev>`, `get` (new revision), `check --json` → `{revision, check: {errors, warnings}}` |
| `gui-planner.phase-set` | medium / risk-based | `set <phase> --json <patch> --expected-revision=<rev>` |
| `gui-planner.decision-decide` | medium / risk-based | `decide <D#> --accept= --rationale= --by= --actor=gui/browser` |
| `gui-planner.item-reopen` | high / always | `reopen <item> --reason= --actor=gui/browser` |
| `gui-planner.grant` | high / always | `grant <gate> --note= --actor=gui/browser` |
| `gui-planner.log-note` | low / none | `log <Pn[.m]> --type= --summary= --actor=gui/browser` |

`patch` is a JSON object (first character `{`); its top-level keys must be in `ALLOW_ITEM` (`title`, `summary`, `why`,
`scope`, `depends_on`, `related`, `decisions`, `skills`, `reads`, `task_files`, `rules`, `guidance`, `examples`,
`validation`, `deliverables`, `route`, `review`, `authority`, `rag`, `orchestration`) or `ALLOW_PHASE` (`title`,
`goal`, `context`, `scope`, `depends_on`, `deliverables`, `validation`), else `FIELD_NOT_EDITABLE` and nothing is
called. `expected_revision` (`sha256:<hex>` of the document the form was built on) is required; the planner compares
it under its plan lock, so a changed document is `PLAN_REVISION_CONFLICT`, and `FIELD_OWNED`, `SCHEMA_INVALID` and
`PLAN_LOCKED` pass as they are. `start` and `finish` are not published: they record execution facts only an executor
can confirm.

Routes (`plans`, `plans/:plan_id`, `…/phases`, `…/board`, `…/graph`, `…/decisions`, `…/timeline`, `…/raw/:ref`,
`…/items/:item_id`, `…/items/:item_id/evidence`) and the dashboard widget `gui-planner.plans` are in `gui.json`. The
plan and the item come from the context (`plan_id`, `item_id`) or, failing that, from the query parameters of the
same name; the path parameters of a route are declared as query parameters.

Failures: a refusal of the planner keeps its code (`PLAN_NOT_FOUND`, `REF_UNKNOWN`, ...); `PLANNER_UNAVAILABLE` (no
hub command line), `PLANNER_CLI_FAILED` (exit other than 0 without an envelope, or not JSON, or a timeout) and
`PLANNER_CONTEXT_MISSING` (no project, plan or item, or a malformed `phase`/`ref`) are the bridge's own. Messages
pass through `safe_text`. A plan whose `plan.json` cannot be read is a row `<id> (unreadable: <code>)` of the list.

## Tests

```bash
bash scripts/test.sh
```

The tests use a fake `swissknifeman` (`tests/fixtures/umbrella-*`, data in `tests/fixtures/fake.py`). The GUI host and
the foundation are found by `SKM_GUI_ROOT` and `AICORE_ROOT`, else in the hub registry (`swissknifeman units list
--json`).
