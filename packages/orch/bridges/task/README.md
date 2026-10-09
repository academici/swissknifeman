# Bridge orch ↔ planner

The only place where orch knows where planner lives. The orch core stays neutral; nothing here is imported by
the core, and planner knows nothing about orch. The bridge only locates files (it never imports planner code).

| Function | Returns |
| --- | --- |
| `planner_root(start=None)` | root of the planner package |
| `plan_script(start=None)` | `<planner root>/scripts/plan.py` |
| `routing_path(start=None)` | `<planner root>/configs/command-routing.json` |
| `orch_root()` | root of this orch package |

## Discovery order

1. `PLANNER_ROOT` — a directory holding `scripts/plan.py` (an invalid value is skipped).
2. The `planner` package next to this orch installation (`<orch root>/../planner`).
3. The monorepo: the nearest ancestor of `start` (default: the current directory) holding
   `packages/planner/scripts/plan.py`.
4. Otherwise `PlannerUnavailable("PLANNER_UNAVAILABLE: …")` with a hint about `PLANNER_ROOT`.

The legacy `harness run` driver implements the same order in `harness/run/task_paths.py` (harness does not
import orch).
