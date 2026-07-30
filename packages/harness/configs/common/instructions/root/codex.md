<!-- instruction:root.codex.bootstrap -->
## root.codex.bootstrap
Treat `.agents/skills/*` as thin generated Codex bootstrap projections that are never the source of truth: canonical skill and command content stays under `packages/skiller/skills/` and `packages/task/commands/`.
<!-- instruction:root.codex.launch-and-hook-integrity -->
## root.codex.launch-and-hook-integrity
For this trusted repository, a Codex launch names the repository cwd, routed model and effort, `-a never`, and `-s danger-full-access`; preflight checks `pwd`, `git status --short`, `codex doctor --json`, hook integrity, `maind health --cwd`, and applicable plan lint. Treat hook exit `127` as a path defect and repair its effective registration. Every finished task and terminal handoff ends with a launch block, and for plan work the provider-neutral `plan-protocol` form is mandatory alongside the native table — never native-only.
<!-- instruction:root.codex.fresh-agent-execution -->
## root.codex.fresh-agent-execution
For an active executable plan, delegate each next executable item from its committed handoff; fix audit regressions forward through the owning item and escalate only an authority or frozen-contract change.
<!-- instruction:root.codex.package-scope-routing -->
## root.codex.package-scope-routing
Project docs are read root→cwd and never past the repository root; restart with `codex -C packages/<name>` to pick up package rules before working inside `packages/<name>/**`.
