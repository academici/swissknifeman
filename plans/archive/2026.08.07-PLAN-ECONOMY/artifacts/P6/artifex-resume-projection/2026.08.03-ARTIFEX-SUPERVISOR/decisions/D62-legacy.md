---
id: D62
date: 2026-08-03
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

`[POSSIBLE-DEFECT]` Until plan-protocol adds a semantic `plan-design finish` Next form, the P6 handoff uses the linter-legal `manual: frontier/high` carrier and keeps the exact Codex finish command in the mandatory code block. RAG:— (repo-grounded: `packages/task/lib/task/plan_lint.py` accepts Pn/Pn.m but not `finish`; plan-design mode 5 requires `finish`).

## Почему

This preserves an executable next step without falsely repeating P6 or skipping directly to audit; owning protocol code is outside this design pass.
