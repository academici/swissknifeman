<!-- instruction:task.identity -->
## task.identity
`task` is the plugin-only package for task-intent commands and executable plan protocol; it has no `bin/`, standalone CLI, or installer.
<!-- instruction:task.command-catalog -->
## task.command-catalog
Keep the intent and plan command catalog in `commands/`; each intent command declares its routed model class and effort.
<!-- instruction:task.plan-protocol -->
## task.plan-protocol
Keep executable plans in `plans/<PLAN-ID>/`; `plan-run` inherits the owner session route.
<!-- instruction:task.plan-files -->
## task.plan-files
Task plans `plans/<ID>/` with `plan.json`: JSON is the source of truth; use `python3 <task>/scripts/plan.py` and read JSON context/worker briefs. Human Markdown lives in `views/`: never read, edit or index it, and never use it as an agent input. Get state with `plan.py next|show|context`; plan directories contain no AGENTS.md/CLAUDE.md carriers.
<!-- instruction:task.layout -->
## task.layout
Keep command Markdown in `commands/`, the plan engine in `lib/task/plan/`, its launcher in `scripts/plan.py`, and isolated tests in `tests/`.
<!-- instruction:task.schema-ownership -->
## task.schema-ownership
Treat `schemas/plan/v1/` and the `plan-protocol` skill as synchronized sources of the plan schema; validate with `scripts/plan.py check` and change both when the schema changes.
<!-- instruction:task.engineering-invariants -->
## task.engineering-invariants
Keep `lib/task/` stdlib-only, retain deliberate plugin-only delivery outside root CLI routing, and use English diagnostics.
<!-- instruction:task.validation-release -->
## task.validation-release
Before release run `bash packages/task/scripts/validate.sh` and use Russian Conventional Commit messages.
