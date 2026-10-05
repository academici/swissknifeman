# Human plan templates

Only human views use Markdown templates in `templates/plan/`. The plan API supplies agent context
and worker briefs as JSON; neither depends on template rendering.

| Template | Output under `views/` |
| --- | --- |
| index | carrier map and phase links |
| plan | goal, context, rules, phases, decisions, contracts |
| roadmap | ordered batches and next action |
| status | phase/item state tables |
| handoff | next action, completed work, friction |
| open-questions | open decisions and blockers |
| document | complete brief/phase/item/unit/decision/knowledge fields and sections |
| `_*.md` | shared human table/list fragments |

`plan.py render` regenerates changed views and removes orphaned views. `render --check` reports
staleness without writing. `plan.py check` validates JSON independently. Human views are never
agent input or indexed context. No plan-local agent instruction files are rendered.

The Mustache subset supports values, sections, inverted sections and partials; formatting happens
in `views.py`. Rendered output is deterministic and contains no generated clock timestamp.
Change templates in source and deliberately regenerate human golden fixtures. Test JSON input
contracts separately. See [Plan structure](./plan-structure).
