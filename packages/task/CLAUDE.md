<!-- swissknifeman:instructions:task:claude-code:common:begin -->
<!-- semantic:task.identity -->
<!-- semantic:task.command-catalog -->
<!-- semantic:task.plan-protocol -->
<!-- semantic:task.layout -->
<!-- semantic:task.schema-ownership -->
<!-- semantic:task.engineering-invariants -->
<!-- semantic:task.validation-release -->
<!-- instruction:task.identity -->
## task.identity
`task` is the plugin-only package for task-intent commands and executable plan protocol; it has no `bin/`, standalone CLI, or installer.
<!-- instruction:task.command-catalog -->
## task.command-catalog
Keep the intent command catalog `design`, `dev`, `fix`, `research`, and `review` alongside `plan-design`, `plan-exec`, `plan-run`, `plan-close`, and `plan-audit`. Also, each intent command declares its routed model class and effort.
<!-- instruction:task.plan-protocol -->
## task.plan-protocol
Keep executable plans in `plans/<PLAN-ID>/`; plan-design, plan-exec, plan-close, and plan-audit remain the protocol’s authoring, execution, closure, and independent-review layers. Also, `plan-run` inherits the owner session route.
<!-- instruction:task.layout -->
## task.layout
Keep command Markdown in `commands/`, the deterministic plan linter in `lib/task/plan_lint.py`, its launcher in `scripts/plan-lint.py`, and isolated tests in `tests/`.
<!-- instruction:task.schema-ownership -->
## task.schema-ownership
Treat `plan_lint.py` and the `plan-protocol` skill as synchronized sources of the plan schema; change both when the schema changes.
<!-- instruction:task.engineering-invariants -->
## task.engineering-invariants
Keep `lib/task/` stdlib-only, retain deliberate plugin-only delivery outside root CLI routing, and use Russian diagnostics.
<!-- instruction:task.validation-release -->
## task.validation-release
Before release run `bash packages/task/scripts/validate.sh` and use Russian Conventional Commit messages.
<!-- swissknifeman:instructions:task:claude-code:common:end -->
<!-- swissknifeman:instructions:task:claude-code:extension:begin -->
<!-- semantic:task.claude-code.slash-projection -->
<!-- semantic:task.claude-code.model-pins -->
<!-- instruction:task.claude-code.slash-projection -->
## task.claude-code.slash-projection
Claude Code exposes the catalog as `/task:design`, `/task:dev`, `/task:fix`, `/task:research`, `/task:review`, `/task:plan-design`, `/task:plan-exec`, `/task:plan-run`, `/task:plan-close`, and `/task:plan-audit`.
<!-- instruction:task.claude-code.model-pins -->
## task.claude-code.model-pins
Claude Code command frontmatter pins model and effort for each task type; do not change those pins without explicit intent, while `plan-run` inherits the owner session route.
<!-- swissknifeman:instructions:task:claude-code:extension:end -->
