# plan-regen

`PostToolUse` hook for `Edit|Write|MultiEdit` on `*.json`. Finds the nearest ancestor with `plan.json`, runs
`python3 <task>/scripts/plan.py check <dir> --json`; on errors (stale views excepted — render repairs them) it returns the first 5 issues (exit 2) and does not render,
otherwise it runs `plan.py render <dir>`. `plan.py` is `$TASK_PLAN_CLI` or `<project>/packages/planner/scripts/plan.py`;
when neither exists the hook does nothing. Enable: `harness hooks --target . --plan-regen on`.
