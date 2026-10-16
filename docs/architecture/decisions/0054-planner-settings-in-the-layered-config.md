# ADR 0054: Planner settings live in the layered `[planner]` configuration

## Status

Accepted

## Context

Thresholds, defaults for new plans and loop limits were constants in the engine and numbers in command texts
([ADR 0012](0012-planner-configuration.md) decided they become configuration). The layered configuration of
aicore ([ADR 0034](0034-layered-config-semantics.md)) now exists.

## Decision

- **Schema.** `configs/config.schema.json` (`urn:swissknifeman:planner:config:v1`) declares the section `[planner]`:
  `context.*`, `check.heavy_text_kb`, `refs.max_chain`, `lock.timeout_seconds`, `new_plan.*`, `new_item.*`,
  `policy.*`, `views.templates_dir`, `orchestration.*`, `events.enabled` and `checks.*`. Every leaf has a default and
  a description, every object is closed. `config.example.toml` is generated with `aicore config example`.
- **Layers.** Schema defaults, machine file, project file, `plan.settings`, environment, `--config`, flags. The
  `plan.settings` layer carries only `context_budget_kb`, mapped to `context.budget_kb`; the other settings of a
  plan stay properties of the plan, and `new_plan.*` supplies their defaults for new plans. No field was added to
  `plan.settings`.
- **Limits.** Loop policies have a lower bound of 1 in the schema (`policy.review_rounds_max` 1–3,
  `policy.corrections_max` 1–2), so a loop cannot be switched off. Command texts refer to the values instead of
  quoting numbers.
- **Stays in code.** Format and contract constants: ids, URNs, statuses, the order of classes and efforts, file
  names, error codes and verbs.
- **Access.** Code reads settings only through `planner.plan.settings`; `plan.py config show|explain` prints the
  result and where each value comes from.

## Alternatives considered

- Making statuses, ids and file names configurable: rejected, it breaks the plan format and old plans.
- One `plan.settings` field per configuration key: rejected, it grows `plan/v1` without a consumer.

## Consequences

- A new key is one schema change plus a regenerated example; the drift check of the unit tooling catches a stale one.
- Without aicore only the defaults and the `plan.settings` layer apply ([ADR 0053](0053-planner-engine-without-hard-aicore-dependency.md)).

## Supersedes

None. Applies [ADR 0012](0012-planner-configuration.md).
