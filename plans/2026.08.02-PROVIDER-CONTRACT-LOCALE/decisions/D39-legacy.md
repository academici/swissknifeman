---
id: D39
date: 2026-08-03
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

Every multi-package item uses the package-cwd protocol in `roadmap.md`: one root coordinator owns integration, the shared manifest and item closure; every package mutation runs from a fresh `codex -C packages/<name>` session under that package's rules and emits a package-scoped evidence record before integration. RAG:— (repo-grounded: root `AGENTS.md` package-scope-routing and affected item `Files`).

## Почему

Keeps the existing 30 item identities while making package rules, ownership, commits and validation evidence explicit across cold sessions.
