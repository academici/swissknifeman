# Configuration

Planner reads the table `[planner]` of the layered configuration. Every key has a default in
`configs/config.schema.json`, so nothing needs to be set; `config.example.toml` lists all keys with their defaults and
is generated from the schema with `aicore config example`.

## Layers

From the lowest to the highest priority:

1. schema defaults;
2. the machine file (`config.toml` in the swissknifeman configuration folder, `~/.config/swissknifeman` by default);
3. the project file (`.swissknifeman/config.toml`);
4. `plan.settings` of the plan (only `context_budget_kb`, which sets `context.budget_kb`);
5. environment variables named `SKM_PLANNER_<TABLE>__<KEY>` in capitals, for example `SKM_PLANNER_CONTEXT__BUDGET_KB=512`;
6. the file given with `--config`;
7. command flags.

`views.templates_dir` is read only from the project file and `--config`, because rendered views are committed with the
plan. Without `aicore` only the schema defaults and the `plan.settings` layer apply, and `--config` is refused with
`AICORE_REQUIRED`.

## Reading the result

```bash
python3 scripts/plan.py config show                 # effective values and whether aicore is available
python3 scripts/plan.py config explain context      # where each value of a key or table comes from
python3 scripts/plan.py config show --plan PLAN1    # add the plan.settings layer of one plan
```

Add `--json` for machine-readable output. Code reads settings only through `planner.plan.settings`.

## Keys

| Key | Type and bounds | Default | Meaning |
|:--|:--|:--|:--|
| `context.budget_kb` | integer 1–4096 | 256 | size threshold of a context pack, KB |
| `context.top_sources` | integer 1–50 | 5 | sources listed in the budget report |
| `check.heavy_text_kb` | integer 1–1024 | 16 | size of a text that `check` calls heavy, KB |
| `refs.max_chain` | integer 1–64 | 8 | depth of the chain of successor plans |
| `lock.timeout_seconds` | integer 1–600 | 30 | how long a command waits for the plan lock |
| `new_plan.design_audit` | `none`, `required` | `none` | `settings.design_audit` of a new plan |
| `new_plan.scout` | `off`, `auto` | `off` | `settings.scout` of a new plan |
| `new_plan.context_pack` | `legacy`, `scoped` | `scoped` | `settings.context_pack` of a new plan |
| `new_plan.evidence` | `optional`, `required` | `optional` | `settings.evidence`; written only when `required` |
| `new_plan.language` | string | empty | `settings.language`; empty is not written |
| `new_plan.commit_scope` | lowercase words with `-`, or empty | empty | `settings.commit.scope`; empty is not written |
| `new_item.route_class` | `economy`, `implementation`, `frontier` | `implementation` | `route.class` of a new item |
| `new_item.route_effort` | `low`, `medium`, `high`, `xhigh`, `max`, `ultra` | `high` | `route.effort` of a new item |
| `new_item.review_mode` | `none`, `self`, `requested` | `none` | `review.mode` of a new item |
| `policy.review_rounds_max` | integer 1–3 | 2 | finished review rounds per item |
| `policy.corrections_max` | integer 1–2 | 1 | corrections by the owner for review findings |
| `views.templates_dir` | string (project file and `--config` only) | empty | folder of view templates that replace the built-in ones by file name; a relative path starts at the file of its layer and `~` is expanded |
| `orchestration.default_scenario` | name `^[a-z][a-z0-9-]*$` | `solo` | execution scenario when nothing more specific is set |
| `orchestration.by_class.economy`, `.implementation`, `.frontier` | name or empty | empty | scenario for a route class; empty means `default_scenario` |
| `events.enabled` | boolean | `true` | emit `planner.*` events |
| `checks.external` | boolean | `true` | call the plugins of the `planner:check` point |
| `checks.external_failure` | `warn`, `error` | `warn` | severity of a plugin that fails, times out or answers invalidly |

The review and correction limits have a lower bound of 1, so a loop cannot be switched off; command texts refer to
these values instead of quoting numbers. Format constants (ids, URNs, statuses, file names, error codes, verbs) are not
configurable. A view template named in `views.templates_dir` that the planner does not know gives a warning.

## Execution scenario

The scenario of an item is the first of: `orchestration.scenario` of the item, of its phase, of the plan,
`orchestration.by_class.<route class>`, `orchestration.default_scenario`. The context pack reports it as
`orchestration.scenario` with `orchestration.scenario_source`. Planner does not check the name against the profiles of
an execution engine.
