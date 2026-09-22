---
id: D1
date: 2026-09-22
status: accepted
item: P1.1
items: [P1.1, P2.1, P3.1, P4.1, P5.1, P6.1]
supersedes: []
superseded_by: null
---
# D1 — Шесть verified iterations и field-only acceptance для non-code

**Actor:** repository-owner + plan-designer/frontier/high
**Evidence:** RAG:— `brief/00-owner-brief.md`, `audits/2026-09-22-perplexity.md`, current repository topology

## Решение

Выполнить работу шестью строго последовательными отдельно запускаемыми
итерациями P1–P6. До implementation каждый N-01…N-17 получает local,
Perplexity и ordinary-search evidence. Prompt/docs/policy change допускается
только при доказанной causal chain и получает behavioral acceptance на
парных прогонах реальных задач реальных consumer-проектов.

## Почему

Группировка по trust seams даёт каждой итерации один проверяемый
интеграционный результат, но не смешивает в одном PR authority, journal и
privacy. Отдельный P1 не даёт внешнему аудиту стать самоисполняющимся
ТЗ. Синтетические prompt tests проверяют форму, но не доказывают
поведение в реальном repository context, поэтому P6 использует real-project runs.

## Consequences

- P2–P5 потребляют frozen verified matrix P1 и не чинят отклонённый claim.
- P6 может закрыться с `no non-code candidate`, если causal chain не найдена; это не понижает качество.
- Consumer repositories используются как isolated field environments и не получают committed writes из этого плана.
