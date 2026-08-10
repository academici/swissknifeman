---
id: D13
date: 2026-08-02
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

A mid-session change of global Codex defaults is evidence, not permission to rewrite user configuration: P0.1 must capture configured defaults separately from the active runtime envelope and flag any mismatch. RAG:— (repo-grounded: `findings/04-authoring-environment-drift-2026-08-02.md`).

## Почему

Default model/sandbox changed after authoring started; conflating them with the running session would corrupt route provenance and trust claims.
