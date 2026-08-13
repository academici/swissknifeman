---
id: D28
date: 2026-08-13
status: accepted
item: P6.2
items: [P6.2]
supersedes: []
superseded_by: null
---

## Решение

`packages/task/adapters/codex/provider-artifacts.lock.json` входит в `Files`
P6.2 как обязательный owning-generator output того же
`render-provider-commands.py --write --repair-owned`, который обновляет
`publication-lock.json` и Codex plugin manifest. RAG:— (repo-grounded: generated
diff и `render-provider-commands.py --check`).

## Почему

D27 уже требует owning provider regeneration, но stable `Files` пропустил
один его lock-carrier. Сохранение generated drift или ручной откат
lock противоречат и ТЗ, и repository generated-artifact invariant. Это
уточнение уже авторизованного release output, а не расширение
product scope.

## Consequences

Item commit `3e24951ec643ad8826cba3018883fc93acaba51f` остаётся в
синхронизированном `Files`; provider renderer check может оставаться
fail-closed без material scope deviation.
