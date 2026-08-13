---
id: D11
date: 2026-08-12
status: accepted
item: P3.3
items: [P3.3, P5.3]
supersedes: []
superseded_by: null
---
## Решение

Workflow requirement выводится одним line-scoped semantic predicate. `scriptPath` или явное
positive multi-agent/orchestration declaration включает его; явное отрицание в том же утверждении
не включает. Отрицание не гасит positive declaration на другой строке/в другом блоке. Правило одно
для обоих layout parser-path и canonical provider meaning. RAG:— (repo-grounded:
`roadmap/2026.08.12-task-orchestration-negation-lint.md`, current parser/tests).

## Почему

Keyword-only grep превращает точное требование «workflow не нужен» в противоположное и провоцирует
лишний workflow либо ложный DoR warning. Полное отключение marker ослабило бы genuine positive cases;
line scope сохраняет sensitivity без cross-line negation leakage.
