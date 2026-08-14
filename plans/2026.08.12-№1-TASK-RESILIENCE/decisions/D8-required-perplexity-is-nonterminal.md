---
id: D8
date: 2026-08-12
status: accepted
item: P0.3
items: [P0.3, P4.1, P4.2]
supersedes: []
superseded_by: null
---
## Решение

Если ТЗ требует Perplexity Web, пустой/недоступный ответ проходит bounded retry и становится
nonterminal `rag-pending`. Context7/WebSearch разрешены как provisional cross-check, но не закрывают
этот item, phase audit или terminal block verdict. Закрытие разрешено только после успешного
Perplexity rerun с сохранённой выжимкой и source provenance. RAG:✅ 2026-08-12
(собственный воспроизведённый bridge defect + успешный basic/advanced/deep rerun; findings/02).

## Почему

Иначе обязательная проверка молча превращается в optional и план сообщает terminal completion при
неполном evidence. При этом недоступность research provider не должна стирать уже выполненную
локальную работу или превращать весь task в бездоказательный `Blocked`.
