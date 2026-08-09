---
id: D150
date: 2026-08-09
status: accepted
item: P6.7
items: [P6.7, P6.8]
supersedes: []
superseded_by: null
---

## Решение

По явному owner gate `acceptance-protocol` получает версию 1.1.0 со stage-aware adjudication
из frozen `read-budget` v1.1.0: `ready` hard-gated; `historical-pre-v2` — evidence-only с
`null` gates и без переписывания specs; `pending-producer` — `deferred` и запрещает final pass.
Приоритет результата: ready failure → `fail`, иначе pending producer → `deferred`, иначе все
ready green → `pass`. Порог `100000`, qualified unit, scope traversal, arms и четыре exact
ветви session canary не меняются. v1.0.0 и его RED сохраняются через report+hash provenance.
RAG:— (owner/repo-grounded: `brief/01-refinements.md` от 2026-08-09;
`findings/P6.7-stage-aware-admission-2026-08-09.md`;
`research/25-p6.7-stage-aware-acceptance-redesign-2026-08-09.md`).

## Почему

Arm A показал 29 ready items без hard failure; максимум `101744` принадлежит
`historical-pre-v2` P2.1, три unresolved — historical, четвёртый — валидный pending producer P6.9.
v1.0.0 агрегировал эти `null`/deferred состояния как hard failure вопреки донорскому контракту.
Instance repair ради pass нарушил бы запрет переписывать historical specs, а threshold/exclusion
tuning после результата уничтожил бы preregistration.

## Consequences

P6.7 возвращается в исполнение и обязан заморозить v1.1.0 отдельным коммитом до нового P6.8 run;
P6.8 остаётся 🔴 до повторной приёмки, P6.9 запрещён. Цена — новая contract version и повтор arms/
canary; прежний RED не повышается до pass и остаётся первым attempt. D126 сохраняет canary и owner
intent, D131 сохраняет stage-aware admission; ни одно из решений не отменяется.
