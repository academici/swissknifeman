---
id: D125
date: 2026-08-08
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

**Root-session continuity, свежесть reviewer-контекста и model/effort — три ортогональные оси.** `isolated-review` — bounded child/tool call существующего reader `auditor`, а не handoff владения: минимальный capsule исключает transcript/chain-of-thought/self-evaluation/unrelated history, reviewer actor отличается от executor, его route выбирается независимо, schema-valid verdict возвращается прежнему root run. Новая root-сессия — только измеренный context boundary, отсутствие nested/resume capability, неразрешённая owner-пауза либо whole-plan audit. **Consequences:** `supersedes D16/D30` только в проектируемой P6.5 семантике автоматического cold-start для любого plan-step; P1.5 уточняет профили читателя, P4.3–P4.6 — triage/capsule, P5.4 — durable resume, P6.1–P6.8 — команды/канон/canary. Provider без nested/resume обязан честно выбрать `cold-start-root` и записать capability defect, а не симулировать continuity.

## Почему

Manager pattern и agents-as-tools позволяют центральному run сохранить управление при отдельном specialist context; nested agent не обязан наследовать весь parent transcript. RAG:✅ 2026-08-08 (`findings/19-session-continuity-and-adaptive-review-2026-08-08.md` R23–R24; `research/17-…` §3–§5).
