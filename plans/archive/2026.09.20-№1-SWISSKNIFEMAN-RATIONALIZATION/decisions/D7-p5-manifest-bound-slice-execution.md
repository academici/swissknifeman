---
id: D7
date: 2026-09-20
status: accepted
item: P5.1
items: [P5.1]
supersedes: []
superseded_by: null
---
# D7 — Manifest-bound, one-slice P5 execution

**Actor:** gpt-5.6-sol/high
**Evidence:** RAG:✅ 2026-09-20 Perplexity `search_advanced(web, academic)` + ordinary web with Google SRE primary page opened; RAG:— D2, D3, D6 and the P4/P5 contracts.

## Решение

P5 не создаёт собственный portfolio и не закрепляет заранее неизвестные product paths.
Она потребляет только nonempty, digest-bound P4 GO manifest. Каждый row выполняется
последовательно как единственный minimal reversible slice: exact Files/dependencies,
validation, provider-parity guardrail, threshold, rollback и post-measurement должны
разрешиться до первой записи. Первый red guardrail, boundary breach, rollback failure или
неподтверждённый practical effect откатывает current slice и останавливает P5; следующий
row автоматически не запускается.

## Почему

P4 уже владеет hard gates и P5-ready contract. Второй selector или статический список
future paths превратил бы evidence-gated work в speculative implementation. Малый
self-contained change, comparison с неизменным control и rollback on adverse divergence
— полезная методическая аналогия для локального measurement; production rollout не
авторизован и пороги не заимствуются из внешнего источника.

## Consequences

До terminal P1–P4 и GREEN global design audit P5.1 остаётся `dependency-not-ready`.
Пустой GO-set по-прежнему требует отдельного owner D# по D6. P5 может закончиться
с rollback evidence после первого non-GREEN slice; это честный результат, а не причина
изменять manifest или продолжать с другим candidate.
