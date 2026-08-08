---
id: D129
date: 2026-08-08
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

**Точечные unittest-команды P2.1 запускаются с явным `PYTHONPATH=lib:tests:../..`, как и пакетный launcher.** Это делает импорты `task`, legacy top-level `fixtures` и shared `core` воспроизводимыми без изменения runtime или тестовой семантики. **Consequences:** Validation P2.1 уточнена execution note; package `validate.sh` остаётся итоговым регрессионным гейтом.

## Почему

Голый `python3 -m unittest tests.test_task_contract tests.test_review_policy` из `packages/task/` падает до исполнения теста, потому что package layout не является установленным distribution и `core` расположен в корне монорепо. Явный путь воспроизводит launcher и дал зелёные 80 тестов task_contract. RAG:— (repo-grounded acceptance evidence 2026-08-08).
