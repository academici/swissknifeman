---
id: D13
date: 2026-08-12
status: accepted
item: P1.1
items: [P1.1]
supersedes: []
superseded_by: null
---
## Решение

P1.1 сохраняет обе исходные executable Validation-команды, но JSON-проверка
больше не подавляет stdout через `>/dev/null`. Это делает acceptance carrier
публично наблюдаемым, не меняя проверяемый JSON или scope item'а.
RAG:— (repo-grounded: `phases/P1/P1.1.md`, `journal.jsonl`,
`packages/task/lib/task/task_contract.py`).

## Почему

Предыдущий terminal block воспроизводился только из-за классификации shell-redirection
как internal evidence; исполнительные артефакты и их проверки уже были зелёными.
Изменение обратимо, не затрагивает public/frozen runtime contract и оставляет
оба исходных acceptance checks в P1.1. RAG:— (repo-grounded:
`handoff.md`, `phases/P1/P1.1.state.md`).
