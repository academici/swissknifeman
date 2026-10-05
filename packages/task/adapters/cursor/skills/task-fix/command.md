<!-- Generated Cursor runtime projection; do not edit as source.
Canonical source: packages/task/commands/fix.md
Canonical SHA-256: sha256:81ca00ac6d2835bf262dc1b916b0ec71f9cd50f357bfed8d2e1a844fb5015009
Adapter: task.cursor-command/1.0.18
-->
---
disable-model-invocation: true
description: "Fix a scoped defect directly; preserve existing work and verify the change."
argument-hint: "[what to fix]"
model: sonnet
effort: medium
---
This is a SMALL incremental repair. User input: `$ARGUMENTS`.
Apply the shared opt-in contract in `references/intent-routing.md` from the installed Task package.
Complete the repair directly: design, a plan, phase audit, and plan close are not completion prerequisites;
old task-file instructions do not override the current owner request. The route is pinned to Sonnet/medium.

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
