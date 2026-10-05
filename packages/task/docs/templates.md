# Templates Task plans - reference

Markdown views of a plan are not written by hand: `scripts/plan.py render` (and every mutating verb)
renders them from JSON through templates in `packages/task/templates/plan/`. This page says which template
is for what; content is NOT duplicated here.

| Template | Output | For what |
|:--|:--|:--|
| `index.md` | `index.md` | what each carrier is, phases with links, how to change the plan |
| `plan.md` | `plan.md` | Meta table (Plan ID, Short ID, Layout `v3`, status, owner), Goal, Context, Rules, phases and decisions tables |
| `roadmap.md` | `roadmap.md` | execution sheet: one row per batch with the `task:plan-run` command, route and state |
| `status.md` | `status.md` | totals and per-phase item tables |
| `handoff.md` | `handoff.md` | Next (from `plan.py next`), launch lines, last finished items, open friction |
| `open-questions.md` | `open-questions.md` | open decisions and blocked items with escalation |
| `agents.md` | `AGENTS.md`, `CLAUDE.md` | plan-local guard: JSON is the source of truth, generated files are not read or edited |
| `context.md` | `context/<item>.md` | the executor's context pack |
| `_*.md` | partials | table rows and blocks (`_meta-row`, `_phase-row`, `_item-row`, `_batch-row`, `_decision-row`, `_question`, `_event-row`, `_read`, `_lesson`, `_check`, `_upstream`, `_decision`) |

## Syntax (Mustache subset, `lib/task/plan/templating.py`)

`{{name}}` / `{{a.b}}` lookup through the context stack; `{{.}}` the current value; `{{#x}}…{{/x}}` iterate a
list or render once for a truthy value; `{{^x}}…{{/x}}` render when empty; `{{>name}}` partial
`templates/plan/_name.md`; `{{! comment}}`. A missing key renders as an empty string; unknown tag syntax is
a `TemplateError`. A line holding only a section or partial tag is removed with its newline, so table rows
do not leave blank lines. No escaping and no logic: all formatting (emoji status, `|` escaping, dates)
happens in the view-model (`lib/task/plan/views.py`).

## How to change a template

Edit the template, run `PYTHONPATH=packages/task/lib python3 -m unittest discover -s packages/task/tests/engine`
and update the golden views in `tests/engine/fixtures/demo-views/` only deliberately (the test prints a
unified diff). Rendering is deterministic: no generation dates, only values from JSON.

Field schemas - [Plan structure](./plan-structure) and `packages/task/schemas/plan/v1/`.
