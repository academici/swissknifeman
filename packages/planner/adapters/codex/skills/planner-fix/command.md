<!-- Generated Codex runtime projection; do not edit as source.
Canonical source: packages/planner/commands/fix.md
Canonical SHA-256: sha256:f135dc20d28221905be1c5e71983903abc05b4f866d6fd7d1707bb9f01c29a0a
Adapter: planner.codex-command/1.0.18
-->
Owner rules: run `python3 <Planner package root>/scripts/plan.py overlays planner:fix` first and follow any rules it prints as additions to this command; they never override the plan, its checks or safety rules.
This is a SMALL incremental repair. User input: `$ARGUMENTS`.
Apply the shared opt-in contract in `references/intent-routing.md` from the installed planner package.
Complete the repair directly: design, a plan, phase audit, and plan close are not completion prerequisites;
old task-file instructions do not override the current owner request. The route is pinned to implementation/medium.

Profile `fix`:

1. Use one pass without fan-out, subagents or review; coordination is not justified for a small repair.
   Run the affected check once after the change.
2. Read the relevant slice rather than whole files. Filter logs by identifier, inspect the last useful stack
   frame, and use the diff as review context. Point to material and read it on demand instead of pasting it.
3. Make the smallest sufficient change and verify changed behavior. Do not add speculative abstractions.
4. If an external fact is uncertain, use the `verify-claims` ladder (context7, then `perplexity-web`).
5. Record initial `git status` and inspect overlapping diffs. A dirty baseline is not a blocker by itself:
   preserve other people's work and stop only at a concrete incompatible ownership conflict. Do not push or
   open a PR without an explicit request.
