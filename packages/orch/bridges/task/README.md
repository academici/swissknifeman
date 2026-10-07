# Bridge orch ↔ Task

The only place where orch knows where Task lives. The orch core stays neutral; nothing here is imported by
the core, and Task knows nothing about orch. The bridge only locates files (it never imports Task code).

| Function | Returns |
| --- | --- |
| `task_root(start=None)` | root of the Task package |
| `plan_script(start=None)` | `<task root>/scripts/plan.py` |
| `routing_path(start=None)` | `<task root>/configs/command-routing.json` |
| `orch_root()` | root of this orch package |

## Discovery order

1. `SKM_TASK_ROOT` — a directory holding `scripts/plan.py` (an invalid value is skipped).
2. The `task` package next to this orch installation (`<orch root>/../task`).
3. The monorepo: the nearest ancestor of `start` (default: the current directory) holding
   `packages/task/scripts/plan.py`.
4. Otherwise `TaskUnavailable("TASK_UNAVAILABLE: …")` with a hint about `SKM_TASK_ROOT`.

The legacy `harness run` driver implements the same order in `harness/run/task_paths.py` (harness does not
import orch).
