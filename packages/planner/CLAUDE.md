<!-- swissknifeman:instructions:planner:claude-code:common:begin -->
<!-- semantic:planner.identity -->
<!-- semantic:planner.command-catalog -->
<!-- semantic:planner.plan-protocol -->
<!-- semantic:planner.plan-files -->
<!-- semantic:planner.layout -->
<!-- semantic:planner.schema-ownership -->
<!-- semantic:planner.engineering-invariants -->
<!-- semantic:planner.validation-release -->
<!-- instruction:planner.identity -->
## planner.identity
`planner` is the plugin-only package for task-intent commands and executable plan protocol; it has no `bin/`, standalone CLI, or installer.
<!-- instruction:planner.command-catalog -->
## planner.command-catalog
Keep the intent and plan command catalog in `commands/`; each intent command declares its routed model class and effort.
<!-- instruction:planner.plan-protocol -->
## planner.plan-protocol
Keep executable plans in `plans/<PLAN-ID>/`; `plan-run` inherits the owner session route.
<!-- instruction:planner.plan-files -->
## planner.plan-files
Planner plans `plans/<ID>/` with `plan.json`: JSON is the source of truth; use `python3 <planner>/scripts/plan.py` and read JSON context/worker briefs. Human Markdown lives in `views/`: never read, edit or index it, and never use it as an agent input. Get state with `plan.py next|show|context`; plan directories contain no AGENTS.md/CLAUDE.md carriers.
<!-- instruction:planner.layout -->
## planner.layout
Keep command Markdown in `commands/`, the plan engine in `lib/planner/plan/`, its launcher in `scripts/plan.py`, and isolated tests in `tests/`.
<!-- instruction:planner.schema-ownership -->
## planner.schema-ownership
Treat `schemas/plan/v1/` and the `plan-protocol` skill as synchronized sources of the plan schema; validate with `scripts/plan.py check` and change both when the schema changes.
<!-- instruction:planner.engineering-invariants -->
## planner.engineering-invariants
Keep `lib/planner/` stdlib-only, retain deliberate plugin-only delivery outside root CLI routing, and use English diagnostics.
<!-- instruction:planner.validation-release -->
## planner.validation-release
Before release run `bash packages/planner/scripts/validate.sh` and use Russian Conventional Commit messages.
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
