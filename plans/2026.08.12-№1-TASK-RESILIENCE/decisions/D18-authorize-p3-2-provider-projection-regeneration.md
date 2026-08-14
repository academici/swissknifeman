---
id: D18
date: 2026-08-12
status: accepted
item: P3.2
items: [P3.2]
supersedes: []
superseded_by: null
---
## Решение

Владелец разрешил P3.2 регенерировать ровно те provider projections, Claude golden fixtures
и operator reference, которые детерминированно изменяет
`packages/task/scripts/render-provider-commands.py` после canonical continue-first изменения.
Разрешение зафиксировано response `P3.2-provider-projection-scope-2026-08-12` в
`decisions/queue.jsonl`; оно не распространяется на иные generated assets или изменения
provider semantics. RAG:— (owner/repo-grounded: durable owner response and
`findings/P3.2-provider-projection-scope-conflict.md`).

## Почему

P3.2 требует green `bash packages/task/scripts/validate.sh`, а validation доказуемо сравнивает
canonical command bytes с этими owned projections. Оставление их stale не сохраняет границу,
а делает declared acceptance невыполнимым. Регенерация через owner tool и последующий `--check`
сохраняют единственный источник истины.
