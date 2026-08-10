---
id: D93
date: 2026-08-04
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

D90's generator boundary is executable only as `instructions plan` with exact action-set verification → `instructions apply --authorize <exact ordered generated targets>` → `instructions check`. P3.8 authorizes `packages/artifex/AGENTS.md,packages/artifex/CLAUDE.md`; P6.2 authorizes `AGENTS.md,CLAUDE.md`. The shared lock is an owner-scoped deterministic apply output, never an `--authorize` target. After P3.8 stage 1 is clean and committed, continuation uses the full byte-for-byte command stored in `phases/P3.md` P3.8 Implementation Rules; its fixed launch prefix is `codex -C /home/vostrikov/projects/packages/swissknifeman/packages/artifex -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access`, followed by a literal single-quoted `NEW SESSION: Continue ... P3.8 at stage 2 only` prompt containing the absolute plan path, P3.8/generated-guide reads, stage-1 commit/check gate, exact remaining scope and close protocol. RAG:— (repo-grounded: Harness CLI/apply implementation, `core/provider/lock.py`, Codex launch/package-scope canon, exact phase carrier and `research/29-audit8-authority-generator-reconcile.md`).

## Почему

Bare `harness instructions` is a false-green help path; an ambient `codex -C packages/artifex` loses route, safety flags and continuation scope. Exact action ordering and cold reads make both generations fail closed without hand-editing projections.
