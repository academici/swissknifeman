<!-- swissknifeman:instructions:planner:claude-code:common:begin -->
<!-- semantic:planner.identity -->
<!-- semantic:planner.command-catalog -->
<!-- semantic:planner.plan-protocol -->
<!-- semantic:planner.plan-files -->
<!-- semantic:planner.layout -->
<!-- semantic:planner.schema-ownership -->
<!-- semantic:planner.engineering-invariants -->
<!-- semantic:planner.configuration -->
<!-- semantic:planner.events-and-extensions -->
<!-- semantic:planner.validation-release -->
<!-- instruction:planner.identity -->
## planner.identity
`planner` is the plugin package for intent commands and the executable plan protocol; its command line is `scripts/plan.py` (no `bin/` yet).
<!-- instruction:planner.command-catalog -->
## planner.command-catalog
Keep the intent and plan command catalog in `commands/`; each intent command declares its routed model class and effort.
<!-- instruction:planner.plan-protocol -->
## planner.plan-protocol
Keep executable plans in `plans/<PLAN-ID>/`; `plan-run` inherits the owner session route. The plans store comes from the project marker `.swissknifeman/project.json`: `<project>/plans` without a marker or with `plans_store: legacy`, `<workspace>/projects/<project_id>/plans/` with `workspace`.
<!-- instruction:planner.plan-files -->
## planner.plan-files
Planner plans `plans/<ID>/` with `plan.json`: JSON is the source of truth; use `python3 <planner>/scripts/plan.py` and read JSON context/worker briefs. Human Markdown lives in `views/`: never read, edit or index it, and never use it as an agent input. Get state with `plan.py next|show|context`; plan directories contain no AGENTS.md/CLAUDE.md carriers. Resolve the plans folder with `swissknifeman project context --json` (`plans_root`, `plans_store`), never by assuming `<project>/plans`.
<!-- instruction:planner.layout -->
## planner.layout
Keep command Markdown in `commands/`, the plan engine in `lib/planner/plan/`, its launcher in `scripts/plan.py`, and isolated tests in `tests/`.
<!-- instruction:planner.schema-ownership -->
## planner.schema-ownership
Treat `schemas/plan/v1/` and the `plan-protocol` skill as synchronized sources of the plan schema; validate with `scripts/plan.py check` and change both when the schema changes.
<!-- instruction:planner.engineering-invariants -->
## planner.engineering-invariants
Keep `lib/planner/plan/` stdlib-only and runnable without aicore; import aicore only in `lib/planner/integration/` and the projection renderer; keep English diagnostics.
<!-- instruction:planner.configuration -->
## planner.configuration
Read planner settings only through `planner.plan.settings` (schema defaults, machine, project, `plan.settings`, environment, `--config`); change keys in `configs/config.schema.json` and regenerate `config.example.toml` with `aicore config example`.
<!-- instruction:planner.events-and-extensions -->
## planner.events-and-extensions
Emit `planner.*` events only after the plan lock is released, through `planner.integration.events`, with data that follow `schemas/event-data/v1`; overlay slots and the `planner:check` point are declared in `unit.json`.
<!-- instruction:planner.validation-release -->
## planner.validation-release
Before release run `bash packages/planner/scripts/validate.sh` and `python3 scripts/ecosystem-units.py standalone planner`, and use Russian Conventional Commit messages.
<!-- swissknifeman:instructions:planner:claude-code:common:end -->

<!-- swissknifeman:instructions:planner:claude-code:extension:begin -->
<!-- semantic:planner.claude-code.slash-projection -->
<!-- semantic:planner.claude-code.model-pins -->
<!-- instruction:planner.claude-code.slash-projection -->
## planner.claude-code.slash-projection
Claude Code projects the planner command catalog as `/planner:*` commands.
<!-- instruction:planner.claude-code.model-pins -->
## planner.claude-code.model-pins
Claude Code command frontmatter pins routes; do not change those pins without explicit intent. `plan-run` inherits the owner session route.
<!-- swissknifeman:instructions:planner:claude-code:extension:end -->
