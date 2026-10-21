<!-- swissknifeman:instructions:root:codex:common:begin -->
<!-- semantic:root.module-folders -->
<!-- semantic:root.product-philosophy -->
<!-- instruction:root.module-folders -->
## root.module-folders
Every `packages/<id>/` folder is an independent module described by its `unit.json`. A module imports only its own `lib/<id>/` and the foundation it declares in `requires` (`aicore`), and reaches other modules only through bridges (`bridges/`) or events, never by import or path. Modules with `destination: own-repo` will move to their own repositories. Check boundaries with `python3 scripts/ecosystem-units.py check`.
<!-- instruction:root.product-philosophy -->
## root.product-philosophy
Swiss Knife Man is a local, provider-neutral control layer: typed JSON plans (planner), a deterministic conductor that runs coding-agent CLIs as bounded roles (orch), and a reproducible developer environment (skiller, harness, aicore, workspace, maind). Follow `docs/philosophy.md`: code owns the lifecycle and models propose; every boundary JSON has a schema and is validated; fail closed on authority and degrade loudly; evidence over claims, repair never changes meaning; proportional assurance; bounded autonomy; neutral core with personal content in overlays.
<!-- swissknifeman:instructions:root:codex:common:end -->

<!-- dev-autonomy:begin (temporary: remove this block when PLAN9 closes, item P10.4) -->
## Development mode: agent-owned decisions
This package is under active restructuring in the stable worktree (`~/projects/packages/swissknifeman-next`, phase branches `stable/p<N>`). The plan and its direction are
already approved by the owner; the agent owns the implementation end to end.

- Make the architectural, design, fix and sequencing decisions yourself. Record them in the plan
  (`plan.py log`; an architectural choice becomes a plan decision) and go on to the result.
- Scope of the run is exactly the plan item(s) named in the invocation: each is done, verified and
  committed; then report and stop. A conductor run over several items is one invocation; between its
  items only the run mechanism (`packages/orch`, `bridges/`) may change, never the work of an item.
- Within the item, decide and finish; do not ask "which option".
- A defect met outside the item: fix it in the item only when it keeps the item's checks red;
  otherwise record it as a plan note that names the item or module owning it.
- Verify with the tests of what you changed (`python3 scripts/affected-tests.py --run`); the full
  pass (`--tier all`) belongs to the item that closes a phase (`phase.validation`).
- Ask the owner only for what only they can do (a command needing their terminal or credentials,
  changes to live machine state, pushes or publishing beyond the plan) or a truly irreversible
  product-level choice.
- Machine-specific rules (paths, pinned tooling) live in the untracked `CLAUDE.local.md` when present.
- Reports stay short: done, verified, next. No "decision for you" blocks.
<!-- dev-autonomy:end -->
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
