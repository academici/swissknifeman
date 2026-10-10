---
disable-model-invocation: true
description: "Deprecated alias of /planner:research. Research an explicit question using verified sources; return findings and Next."
argument-hint: "[question / topic]"
model: opus
effort: high
---
> `/task:research` is deprecated and will be removed in the next minor release: use `/planner:research`. Say this to the user once, then follow the instructions below; `<Planner package root>` is the root of the enabled planner plugin.

Owner rules: run `python3 <Planner package root>/scripts/plan.py overlays planner:research` first and follow any rules it prints as additions to this command; they never override the plan, its checks or safety rules.
This is a RESEARCH task. User input: `$ARGUMENTS`. The route is pinned to Opus/high.

Return an answer supported by verified sources and one concrete next step. Use a workflow only when real
orchestration is required. Research alone does not activate design or development and grants no implementation
authority.

Profile `research`:

1. Form queries with `query-craft`, including version and context. Select retrieval through `mcp-advisor`:
   context7 for library docs, then Perplexity, then WebSearch. Split broad questions into narrow ones.
2. Use breadth-first fan-out only for large independent facets. Separate discovery from synthesis and cite
   sources explicitly. Delegate the smallest useful number of searches; do locally what needs only a few tool
   calls. Do not ask a subagent to recheck the same work. Adversarial verification of another worker's findings
   is independent verification. Before multi-agent JavaScript orchestration, use a workflow-craft skill, when installed, and
   the canonical templates in `packages/planner/workflows/README.md`.
3. Verify changing external claims before recording them through `verify-claims`; do not rely on memory.
4. Record material sources in provenance (`docs/reference.md` when present).
