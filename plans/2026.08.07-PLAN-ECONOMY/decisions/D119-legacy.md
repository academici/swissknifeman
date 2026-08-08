---
id: D119
date: 2026-08-08
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

**Весь план принимает модель `shared contract + independent provider certification`.** Общие схемы, reducers, gates и canonical commands не содержат raw provider fields/UI/auth; provider-specific adapter/projection аддитивен и имеет собственные lock/tests/evidence. Автор текущего среза обязан довести до `verified` только активный Codex row. Отсутствующий Claude row получает честный `pending-provider`: не блокирует shared core/Codex rollout, но не считается green/parity; при подключении Claude проверяет и чинит собственную часть без перепроектирования core. **Consequences:** P0, модельные швы P4/P5 и проекции P6 хранят provider/model provenance как данные, но не ветвят shared policy по бренду; изменение shared contract после provider feedback требует D#, adapter-local fix — нет. Отвергнуты exhaustive cross-provider gate до первой поставки и speculative Claude code.

## Почему

Прямое уточнение владельца 2026-08-08; repo-grounded provider parity и generated projection/lock архитектура. RAG:— (`brief/01-refinements.md`; `research/16-multiprovider-field-loop-2026-08-08.md`; root.provider-parity).
