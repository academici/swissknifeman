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
