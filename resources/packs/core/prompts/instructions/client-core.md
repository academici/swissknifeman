+++
schema = "urn:skm:extensions:prompt-block:v1"
block_type = "repo_instructions"
variables = []
+++
## Swiss Knife Man

This repository is managed with SKM. Rules for coding agents working here:

- Plans, decisions and progress live in SKM (`skm plan …`, `skm run …`), not in ad-hoc files of the repository.
- Files under `.claude/skills/` and `.claude/agents/` and every block between `skm:begin` and `skm:end` markers are generated: edit the source, then run `skm integrations apply`.
- Run the project checks before you finish a change.
- If the checkout has a `.codegraph/` directory, use `codegraph_explore` with `projectPath` set to the checkout root to find related symbols, source, and call paths. If the MCP tool is unavailable, run `codegraph explore` from the checkout root.
- The `skm` MCP server gives short-lived project memory (`memory_search`, `memory_remember`) and the project graph (`graph_neighbors`, `graph_path`); check `freshness` and `completeness` of a graph answer before relying on it.
