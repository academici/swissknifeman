# Events and extensions

Planner offers three extension surfaces. All of them need the foundation `aicore`; without it they are quiet no-ops
(see [Configuration](./configuration)) and `plan.py config show` prints `aicore: unavailable`.

## Events

Planner writes events to the `aicore` journal after a change is stored and after the plan lock is released. A
subscriber that runs `plan.py` itself therefore never blocks. Emission is best effort: if the journal cannot be
written, the command still succeeds and prints one `PLANNER_EVENT_NOT_EMITTED` warning. Set `events.enabled = false`
to turn events off. Repeating `finish` with the same attempt id emits nothing.
The global `--config FILE` also applies to aicore event delivery, subscriptions and plugins, so the invocation
uses the delivery mode and subscribers declared in that file.

| Type | Emitted by | Data beyond the common fields |
|:--|:--|:--|
| `planner.plan.created` | `new` | optional `created` |
| `planner.plan.closed` | the last `finish`, `reconcile` | `status`; optional `goal`, `closed_at`, `phases`, `counts` |
| `planner.phase.closed` | `finish`, `reconcile` | `phase_id`, `result`, `closed_at`; optional `summary` |
| `planner.item.started` | `start` | `item_id`, `phase_id`, `executor`; optional `route`, `resumed`, `take_over` |
| `planner.item.finished` | `finish` | `item_id`, `phase_id`, `status`; optional `attempt_id`, `checks`, `commits`, `deviation_count` |
| `planner.decision.accepted` | `decide` | `decision_id`, `decision` (up to 4096 characters); optional `answered_by`, `applies_to` |

Every type also carries `plan_id` and `title`, and optionally `short_id` and `repository`. The `subject` of an event is
the plan id and `source` is `planner`. A plan that closes gives `item.finished`, then `phase.closed`, then
`plan.closed`, each caused by the previous one. Data never contain notes, deviation texts, rationales or secrets.

The data of each type follow a closed schema, `schemas/event-data/v1/<type>.schema.json`
(`urn:swissknifeman:planner:event-data:<type>:v1`). Consumers ignore fields they do not know, so new optional fields
are minor changes. The hub test `scripts/test-event-contracts.py` checks consumer fixtures against these schemas.

## Command overlays

Every command has one overlay slot, `planner:<command>`, declared in `unit.json` (`design`, `dev`, `fix`,
`make-workflow`, `plan-audit`, `plan-close`, `plan-design`, `plan-run`, `research`, `review`). The first line of a
command runs

```bash
python3 scripts/plan.py overlays planner:plan-run
```

and follows the rules it prints as additions. Overlay files are mapped to slots in the configuration
(`[aicore.overlays."planner:plan-run"]`), by a person for the machine or for a project. Overlays never override the
plan, its checks or safety rules, and they are resolved when the command runs, not written into the shared
projections. Without `aicore` the block is empty and the command is unchanged. `--strict` makes a missing overlay file
an error.

## External plan checks

The extension point `planner:check` lets a plugin add findings to `plan.py check`. A plugin is registered in the
machine configuration of `aicore` (`[aicore.plugins.<id>]`); planner registers none itself.

- **Input** (`schemas/check-plugin/v1/input.schema.json`): `plan_id`, `short_id`, `plan_dir`, `plans_root`,
  `project_root` (or null), `planner_version` and `schema_urn_prefix`. The plugin reads the plan itself from
  `plan_dir`, or with `plan.py export`.
- **Output** (`schemas/check-plugin/v1/output.schema.json`): `{"issues": [...]}` with at most 500 issues; each has
  `severity` (`error` or `warning`), `code` (`^[A-Z][A-Z0-9_]*$`), `message`, and optionally `ref` and `path`.

Only the `check` verb calls the point, after its own checks; the checks inside other verbs never do, so a plugin cannot
slow a mutation. The issues join the findings of `check` with the plugin id as prefix. A plugin that fails, times out
or answers with an invalid output gives one `EXTERNAL_CHECK_FAILED` finding whose severity is
`checks.external_failure`; it never stops the other plugins or the built-in checks. `plan.py check --no-external`
skips the point and `checks.external = false` disables it.
An enabled plugin registration with a missing or invalid manifest also produces one `EXTERNAL_CHECK_FAILED`
finding with the configured severity: its extension points cannot be determined. Disabled registrations are ignored,
and a broken registration does not stop other plugins from running.
