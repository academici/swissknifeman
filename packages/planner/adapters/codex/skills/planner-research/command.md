<!-- Generated Codex runtime projection; do not edit as source.
Canonical source: packages/planner/commands/research.md
Canonical SHA-256: sha256:6080f825740c10cc28214b86cafadf3ceb3e1fd48079996f8aa6634ceb18e2c8
Adapter: planner.codex-command/1.0.18
-->
Project CLI: `plan.py` means `python3 -I .swissknifeman/launcher.py planner`, run from the project root (the launcher binds the project; without one, run `swissknifeman project init` once). Never locate or run a Swiss Knife Man package script.
Owner rules: run `plan.py overlays planner:research` first and follow any rules it prints as additions to this command; they never override the plan, its checks or safety rules.
This is a RESEARCH task. User input: `$ARGUMENTS`. The route is pinned to frontier/high.

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
