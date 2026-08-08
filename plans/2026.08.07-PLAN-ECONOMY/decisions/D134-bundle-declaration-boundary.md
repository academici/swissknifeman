---
id: D134
date: 2026-08-08
status: accepted
item: P3.4
items: [P3.4]
supersedes: []
superseded_by: null
---
## Решение

**Bundle v1 consumes only candidates declared by the item author.** Candidates that
`plan_weight.path_candidates()` marks `declared=False` remain measurement heuristics and cannot
become bundle entries or fail bundle materialization. RAG:— (repo-grounded:
`packages/task/lib/task/plan_weight.py`; `packages/task/lib/task/plan_bundle.py`;
owner-grounded: `brief/01-refinements.md`, 2026-08-08).

## Почему

An explanatory phrase such as `verified Codex event/flags` may look path-like but does not
declare a required input. Treating it as a Bundle entry makes a valid backticked declaration
unbuildable before P3.4 can distinguish a genuine unresolved declaration.

## Consequences

The builder retains fail-closed `unresolvable_entry` for every declared path and requires no
schema change. The measured read graph remains owned by `plan_weight` and keeps its heuristic
diagnostics unchanged.
