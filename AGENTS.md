<!-- swissknifeman:instructions:root:codex:common:begin -->
<!-- semantic:root.module-folders -->
<!-- instruction:root.module-folders -->
## root.module-folders
Every `packages/<id>/` folder is an independent module described by its `unit.json`. A module imports only its own `lib/<id>/` and the foundation it declares in `requires` (`aicore`; `core/` until it is removed), and reaches other modules only through bridges (`bridges/`) or events, never by import or path. Modules with `destination: own-repo` will move to their own repositories. Check boundaries with `python3 scripts/ecosystem-units.py check`.
<!-- swissknifeman:instructions:root:codex:common:end -->
<!-- swissknifeman:instructions:root:codex:extension:begin -->
<!-- semantic:root.codex.bootstrap -->
<!-- semantic:root.codex.launch-and-hook-integrity -->
<!-- semantic:root.codex.fresh-agent-execution -->
<!-- semantic:root.codex.package-scope-routing -->
<!-- instruction:root.codex.bootstrap -->
## root.codex.bootstrap
Treat `.agents/skills/*` as thin generated Codex bootstrap projections that are never the source of truth: canonical skill and command content stays under `packages/skiller/skills/` and `packages/planner/commands/`.
<!-- instruction:root.codex.launch-and-hook-integrity -->
## root.codex.launch-and-hook-integrity
For a Codex launch, name the intended cwd, routed model/effort, `-a never` and `-s danger-full-access`. Check cwd and working-tree state before edits. Run doctor, hook/settings integrity and maind health on installation, environment changes or symptoms, not every code task. Treat hook exit `127` as a path defect and repair its effective registration.
<!-- instruction:root.codex.fresh-agent-execution -->
## root.codex.fresh-agent-execution
Continue in the current session when context and capabilities suffice. Respect a separately requested design/review boundary. Planner workflow instructions load only after explicit owner invocation; an existing plan or handoff does not activate them.
<!-- instruction:root.codex.package-scope-routing -->
## root.codex.package-scope-routing
Project docs are read root→cwd and never past the repository root. Start package-scoped work with the intended cwd for native discovery. During an authorized cross-package task, explicitly read each applicable package guide in the current session; directory changes alone do not require restart.
<!-- swissknifeman:instructions:root:codex:extension:end -->
