---
id: D124
date: 2026-08-08
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

**Адаптивная лестница возврата фиксирована по durable fingerprint:** первая локальная воспроизводимая ошибка внутри Scope/Files без protected/frozen/public-contract, security, destructive, irreversible, cross-package, rule-conflict, unclear-architecture или unclear-acceptance триггера → `local-fix` в текущей root-сессии; второе появление ТОГО ЖЕ отпечатка или любой названный риск/неясность → ровно один `isolated-review`; третье появление при `same_return_max = 2` → существующий owner gate. Отсутствие суждения легально; audit не является дефолтом первого сбоя.

## Почему

Внешние источники рекомендуют manager+specialist и выборочную сложность, а не subagent для простой тесно связанной правки; точный численный порог переиспользует существующий контракт этого плана, не выводится из внешнего текста. RAG:✅ 2026-08-08 (`findings/19-session-continuity-and-adaptive-review-2026-08-08.md` R23–R25; синтез `research/17-…` §2).
