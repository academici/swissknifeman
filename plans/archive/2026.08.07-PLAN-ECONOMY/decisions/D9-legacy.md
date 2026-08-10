---
id: D9
date: 2026-08-07
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

Детекция «мы возвращаемся сюда по ТОЙ ЖЕ причине» строится в этом плане, а не берётся из фреймворка.

## Почему

Обследованы LangGraph (`recursion_limit`), AutoGen (условия завершения, `max_consecutive_auto_reply`), CrewAI (`max_iter`, `max_retry_limit`): все дают потолок шагов/итераций, ни один не сравнивает причину отказа. Отрицательный результат разведки, а не пробел в поиске. RAG:✅ 2026-08-07 (`findings/01-…` R5)
