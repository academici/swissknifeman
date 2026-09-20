---
id: D6
date: 2026-09-20
status: accepted
item: P4.1
items: [P4.1, P5.1]
supersedes: []
superseded_by: null
---
# D6 — Hard gates and four-experiment cap for P4

**Actor:** gpt-5.6-sol/high
**Evidence:** RAG:✅ 2026-09-20 Perplexity `search_advanced(web, academic)` + ordinary web with Google SRE/NIST primary pages opened; RAG:— `findings/p4-design-method.md` and P1–P3 contracts

## Решение

P4 строит полный candidate intake, но запускает не более четырёх experiments. Отбор идёт
короткими hard gates — observed pain, isolatable mechanism, existing measurement,
reversibility, bounded dependencies и P1-sized practical effect — без weighted score.
На experiment разрешены ровно две valid matched pairs и максимум одна заранее допустимая
infrastructure-invalid replacement; затем обязательный stop.

`go` требует обеих pairs, P1 threshold, GREEN guardrails/provider parity и bounded P5
validation/rollback contract. Mixed или under-covered evidence даёт `defer`; приемлемый
baseline без material gain — `keep`; falsified, harmful или dominated candidate — `reject`.
Если GO-set пуст, P4 не создаёт фиктивный producer-readiness: empty set требует отдельного
owner D#.

## Почему

Weighted portfolio framework добавил бы ровно ту orchestration surface, которую план проверяет
на избыточность. Без cap исходные рекомендации могли бы развернуться в повтор P1–P3 или
полноценную test programme. Две matched pairs сохраняют возможность увидеть повторяемый
practical effect при малой стоимости; ambiguous outcome безопасно завершается `defer`.

## Consequences

P4 может закончить GREEN с маленьким portfolio или без GO-slices. P5 получает только
traceable GO manifest; остальные идеи не превращаются в backlog без явного re-open trigger.
