---
id: D5
date: 2026-09-20
status: accepted
item: P3.1
items: [P3.1]
supersedes: []
superseded_by: null
---
# D5 — Coverage-first two-pair pilots for memory and codegraph

**Actor:** gpt-5.6-sol/high
**Evidence:** RAG:✅ 2026-09-20 Perplexity `search_advanced(web, academic)` + ordinary web with LongMemEval/RepoGraph primary pages opened; RAG:— `findings/p3-design-method.md` and current provider telemetry code/tests

## Решение

P3 сначала строит structural coverage/parity matrix для Claude Code, Codex и Cursor,
затем требует по одному known-result probe memory и codegraph на exact execution provider.
Если identity, exposure, relevant evidence и downstream acceptance не связываются,
value pilot не расширяется, а verdict ограничивается `defer`.

При GREEN probe memory и codegraph измеряются отдельно: ровно две valid A/B pairs
на mechanism с одним изменяемым фактором и не более одной replacement pair
для infrastructure-invalid run. Exact practical thresholds и `go|keep|defer|reject` reducer
берутся из P1. Mixed, incomplete или under-covered evidence даёт `defer`; combined verdict запрещён.

## Почему

Альтернатива 20–30 tasks из Perplexity synthesis отклонена как несоразмерная owner scope
и D2. Одна сводная memory+graph оценка тоже отклонена: она не покажет,
какой mechanism дал effect. Наконец, добавление telemetry до доказанного gap само
стало бы спекулятивной implementation.

## Consequences

P3.1 может закончиться двумя `defer` без pilot expansion, и это GREEN outcome при
честно зафиксированном coverage gap. P4 получает два независимых verdict и не имеет
права сводить их в автоматический rollout.
