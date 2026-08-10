---
id: D8
date: 2026-08-03
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

Дефолт — последовательный one-writer scheduler. Parallel max 2 разрешён только по доказанной независимости: read-only fan-out либо отдельные worktrees; merge/integration всегда сериализован. RAG:✅ OpenAI caution for write-heavy parallel work; Maestro/Superset worktree patterns.

## Почему

Предотвращает конфликтный fan-out и стоимость повторной интеграции.
