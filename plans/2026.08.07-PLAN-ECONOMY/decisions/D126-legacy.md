---
id: D126
date: 2026-08-08
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

**Владелец отклонил сдачу с RED-долгом и делегировал технический способ закрытия агенту; F4.1–F4.4 закрываются полностью в текущем owning root без пятого аудита.** P6.7 замораживает машинный `session_canary` с четырьмя branch ids и точными ожиданиями; P6.8 производит отдельный `session-canary-results.json` и сравнивает observed с frozen expected поле-в-поле. B1/B2 получают действующий `same-session — item`; DoR P1/P4/P5/P6 и roadmap реконсилируются с D123–D126/R23–R25, версия карты — v0.24.0. **Consequences:** вариант `🟠` из launch-block аудита отвергнут; D123–D125 не отменяются и новый audit-cap не открывается. Следующий шаг после машинной сверки плана — P1.5 в той же item-by-item continuity, а не ещё один `plan-audit design`.

## Почему

Прямое уточнение владельца: «хочу идеальный пакет», способ не важен, решение доверено агенту. Audit F4.1 доказал ложнозелёный путь canary, F4.2 — неисполняемые Context, F4.3/F4.4 — неполный reconcile. Выбран минимальный вариант, сохраняющий provenance и устраняющий все четыре класса без изменения уже замороженной лестницы. RAG:— (owner-grounded + repo-grounded: `brief/01-refinements.md`; `findings/13-design-audit-2026-08-07.md` заход 4; `research/18-audit-red-remediation-2026-08-08.md`).
