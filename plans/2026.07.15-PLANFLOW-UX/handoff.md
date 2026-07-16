# HANDOFF — 2026-07-16 — after P4.1

**Next:** ЗАПУСК ВРУЧНУЮ: opus/high

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | high — канон-схема §3 Routing (fleet-facing, back-compat флота) |
| Context | continue (/clear) — ручной item |
| Суть | P4.2 — расширить §3 Routing колонками Batch/Review (опц.) + подраздел «Батчинг подфаз» (D12/OQ-1) |

```
Исполни item P4.2 плана 2026.07.15-PLANFLOW-UX (Exec=manual, opus/high).
Прочитай: plans/2026.07.15-PLANFLOW-UX/plan.md (Context, §2 Execution Rules, §3 Routing,
Status Board) → plans/2026.07.15-PLANFLOW-UX/handoff.md → plans/2026.07.15-PLANFLOW-UX/phases/P4.md
(Phase Context + item P4.2 целиком, включая P4.1 Completion Notes) → Required Reads P4.2 по порядку.
Расширь канон-форму §3 Routing колонками Batch/Review (ОПЦИОНАЛЬНЫМИ, легаси-форма валидна) +
подраздел «Батчинг подфаз» с D6-инвариантом (батч наследует МАКСИМУМ риска, Review=full не сливать)
в SKILL.ru.md → регенерация SKILL.md (генератор prompts/generate/claude-canon-from-ru.md) →
check-translations.sh --stamp → skiller registry; заметки в plan-design.md/plan-exec.md — строго по
Scope/Rules P4.2. НЕ трогать plan_lint.py (§3 не парсится, back-compat). Закрой item по протоколу
(§8): item-коммит по Files → bookkeeping → перезапись handoff → lint (--baseline HEAD).
```

**Done:** P4.1 закрыт 🟠 (регенерённые skills.json/budget.md вне Files — паттерн P2.1/P3.1/P3.2,
4-й раз). Подраздел **«Contract-first дизайн-флоу»** кодифицирован в канон `plan-protocol` §5
(`SKILL.ru.md` SSOT + регенерён `SKILL.md`): опциональный режим авторинга (запечатать все фазы
скелетами + межфазовый контракт-блок `Потребляет · Производит · Границы`, детализировать
just-in-time) + reconcile-правило при детализации (дрейф → D#) + превентивное перечисление
coupling-поверхности. Опц. контракт-блок в `snippets/phase-template.md`; заметки режимов `new`/`Pn`
в `plan-design.md`. Машинный гейт НЕ введён, `plan_lint.py` не тронут, §5 скелет-маркер не переписан
(аддитив). Item-коммит `5b0bf0e`. Первая фаза P4 стартовала (Status Board P4 → 🟡, 1/3).

**Remaining:** P4.2 (глобальный exec-план — батчинг §3 Routing +Batch/+Review, sonnet/high manual,
D12/OQ-1) → P4.3 (адаптивная глубина ревью, наполняет enum `Review`, sonnet/high manual) — оба
manual/sequential (общий `SKILL.ru.md`) → P5 (fix-стратегия plan-design + архитектурный апгрейд,
скелет, детализируется `/task:plan-design ... P5`).

**Sources of truth:** `phases/P4.md` (Phase Context + P4.1 Completion Notes/Known Deviations +
P4.2/P4.3 ТЗ) · `plan.md` (§3 Routing P4.2/P4.3, §4 Status Board P4 🟡 1/3, §5 D12–D14, §6 Update
Log) · `packages/skiller/skills/general/plan-protocol/SKILL.ru.md` §5 (новый подраздел Contract-first —
предпосылка P4.2) · `findings/P1-recon.md` (§4 dev-loop risk-adaptive, §5-P4, §6 RAG).

**Open risks:**
- **P4.2 после P4.1:** общий файл `SKILL.ru.md` — P4.2 строит §9-форму §3 Routing ПОВЕРХ §5
  Contract-first; конфликта нет (разные секции), но регенерация EN + `skiller registry` обязательны
  (иначе дрейф `skills.json`/`budget.md`, как в P4.1).
- **Files skill-item'ов не несут реестровые артефакты** (4-й повтор): P4.2/P4.3 закроются тем же 🟠,
  пока plan-design не внесёт `skills.json`/`budget.md`/`marketplace.json` в Files skill-правящих
  item'ов. Кандидат в канон (см. P4.1 Known Deviations #1).
- **Незакоммиченный P4-design дифф** (`handoff.md`/`open-questions.md`/`plan.md`/`P4.md`, шаг
  plan-design «P4 детализирована») уехал в bookkeeping-коммит P4.1 — plan-файлы carve-out, назван
  в P4.1 Known Deviations #2. Дальнейших остатков нет.

**Workarounds/Deferred/Open questions:**
- workarounds: —
- deferred: P5 детализация (fix-стратегия + архитектурный апгрейд, ось B); rollout доставки гейта
  `workflow-craft` (пост-OQ-3, deleg skiller/maind); launch-block вне `plan-*` (OQ-2).
- open_questions: **OQ-2** (launch-block в `dev.md`/`fix.md` — pending) · **OQ-3** (канал доставки
  гейта — квантифицирован P3.5, рекомендация A=CORE_SKILLS, pending за Owner). OQ-1 — Resolved→D12.

**Context:** handoff свежий — рекомендован /clear перед следующим item.
