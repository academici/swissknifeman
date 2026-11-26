# Demo service (Codex)

Notes written by people stay here: skm never changes text outside its own blocks.

<!-- skm:begin id=instructions.core digest=e3fb55041b67 -->
## Swiss Knife Man

This repository is managed with SKM. Rules for coding agents working here:

- Plans, decisions and progress live in SKM (`skm plan …`, `skm run …`), not in ad-hoc files of the repository.
- Files under `.claude/skills/` and `.claude/agents/` and every block between `skm:begin` and `skm:end` markers are
  generated: edit the source, then run `skm integrations apply`.
- Run the project checks before you finish a change.
- The `skm` MCP server gives short-lived project memory (`memory_search`, `memory_remember`) and the project graph
  (`graph_neighbors`, `graph_path`); check `freshness` and `completeness` of a graph answer before relying on it.
<!-- skm:end id=instructions.core -->
<!-- skm:begin id=instructions.project digest=f653a6dc80fb -->
## Project rules

- Python 3.12; run `uv run pytest -q` and `uv run ruff check` before every commit.
- A change of the public HTTP API needs an ADR in `docs/adr/`.
<!-- skm:end id=instructions.project -->
