<!-- instruction:root.codex.bootstrap -->
## root.codex.bootstrap
Treat `.agents/skills/*` as thin Codex adapters, keep canonical skill and command content under `packages/skiller/skills/` and `packages/task/commands/`, use worktree-local package CLIs for writes, and preserve Claude Code compatibility.
<!-- instruction:root.codex.launch-and-hook-integrity -->
## root.codex.launch-and-hook-integrity
For this trusted repository, a Codex launch names the repository cwd, routed model and effort, `-a never`, and `-s danger-full-access`; preflight checks `pwd`, `git status --short`, `codex doctor --json`, hook integrity, `maind health --cwd`, and applicable plan lint. Treat hook exit `127` as a path defect and repair its effective registration.
<!-- instruction:root.codex.fresh-agent-execution -->
## root.codex.fresh-agent-execution
For an active executable plan, delegate each next executable item from its committed handoff; fix audit regressions forward through the owning item and escalate only an authority or frozen-contract change.
