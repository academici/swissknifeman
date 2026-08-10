---
id: D41
date: 2026-08-03
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

P3 preflight records two non-green Hook/Harness facts without repair: relative `--target .` raises explicit-root `ValueError`, while absolute target still reports lifecycle hooks/handler `stale-source`; syntax, doctor and mAInd health are green. RAG:— (direct local observation; `findings/07-p3-provider-runtime-recon-2026-08-03.md`).

## Почему

Validation trust must distinguish a CLI-normalization defect, actual source drift and unrelated green checks; this design pass does not capture foreign dirty scope.
