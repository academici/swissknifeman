<!-- Generated Codex runtime projection; do not edit as source.
Canonical source: packages/task/commands/research.md
Canonical SHA-256: sha256:15244d61160ef438c2348d5796eec28a5c9dd8666502243475608fe1e1c60f8d
Adapter: task.codex-command/1.0.18
-->
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
   the canonical templates in `packages/task/workflows/README.md`.
3. Verify changing external claims before recording them through `verify-claims`; do not rely on memory.
4. Record material sources in provenance (`docs/reference.md` when present).
