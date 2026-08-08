---
id: D32
date: 2026-08-03
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

P2 compiler consumes the worktree-local `harness run --dry-run --json` queue plus canonical `task.task_contract build` output through subprocesses; it cross-checks them and adds only `slice-manifest-v1` semantics. It neither imports private parsers nor parses Markdown. RAG:— (repo-grounded: `findings/06-p2-runtime-recon-2026-08-03.md`).

## Почему

Reuses the live reader/route owners without binding the experiment to their private Python seams or creating a third status/parser SSOT.
