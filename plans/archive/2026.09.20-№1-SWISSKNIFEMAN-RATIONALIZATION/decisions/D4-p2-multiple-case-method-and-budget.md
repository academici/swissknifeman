---
id: D4
date: 2026-09-20
status: accepted
item: P2.1
items: [P2.1]
supersedes: []
superseded_by: null
---
# D4 — Separate-case field method and bounded evidence budget for P2

**Actor:** gpt-5.6-sol/high
**Evidence:** RAG:✅ 2026-09-20 Perplexity `search_advanced(web, academic)` + ordinary web search with primary sources opened; RAG:— `findings/p2-design-method.md`, topology/registry and three consumer git baselines

## Решение

P2 использует multiple-case observational design: corex, agentools и edufy — три
самостоятельных case с одинаковой rubric и отдельными findings; cross-case
synthesis начинается только после их заморозки и не добавляет новые raw claims.
Каждый case ограничен 24 commit-bound tracked content-reads и 6 trusted completed
task/run-report pairs; наблюдаемые dimensions не сводятся к activity proxy. Нехватка
доверенных данных заканчивается `coverage-gap|unassessable`, а не расширением выборки
или выводом об отсутствии ценности.

## Почему

Единый mining pass был отклонён: он смешивает три разных контекста и даёт крупным
или лучше инструментированным проектам незаслуженный вес. Полный user study/benchmark также
отклонён как выходящий за owner scope и противоречащий D2. RAG:✅ Runeson/Höst разделяют
case по context, требуют planned multi-source evidence/validity threats и не приравнивают case study к
controlled causal experiment. RAG:✅ SPACE прямо отвергает single-metric developer productivity.

## Consequences

P2.1 должен произвести три case files и один synthesis без consumer writes. P3/P4 могут
использовать только прозрачные evidence rows с denominator/coverage. Лимиты не могут быть
тихо увеличены в execution; новая выборка требует новой measured hypothesis, а не обычного repair.
