---
id: D2
date: 2026-08-10
status: accepted
item: P0.2
items: [P0.2, P1.1]
supersedes: []
superseded_by: null
actor: repository-owner (accepted via brief/00-brief.md)
model: gpt-5.6-sol/high (authored; actual effort not independently attested)
evidence: RAG:✅ 2026-08-10 findings/02-external-rag.md + research/01-target-operating-model.md
---

## Решение

Мелкий обратимый дефект в scope исправляется в той же owning-сессии. Повтор одного failure
fingerprint вызывает смену тактики и максимум один scoped review; остановка обязательна только
на material/authority boundary или при подтверждённом no-progress.

## Почему

Фиксированный лимит итераций сам создаёт ложные блокировки; ограничивать нужно повтор без
нового evidence, а не полезный прогресс. RAG:✅ 2026-08-10 (`findings/02-external-rag.md`;
synthesis `research/01-target-operating-model.md`).
