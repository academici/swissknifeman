# HANDOFF — 2026-07-16 — after P4.2

**Next:** ЗАПУСК ВРУЧНУЮ: sonnet/high

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | high — канон fleet-facing (классификация риск→глубина ревью) |
| Context | continue (/clear) — ручной item |
| Суть | P4.3 — наполнить enum `Review` (full/light/none) классификацией риска среза + D6-инвариант |

```
Исполни item P4.3 плана 2026.07.15-PLANFLOW-UX (Exec=manual, sonnet/high).
Прочитай: plans/2026.07.15-PLANFLOW-UX/plan.md (Context, §2 Execution Rules, §3 Routing,
Status Board) → plans/2026.07.15-PLANFLOW-UX/handoff.md → plans/2026.07.15-PLANFLOW-UX/phases/P4.md
(Phase Context + item P4.3 целиком, включая P4.2 Completion Notes) → Required Reads P4.3 по порядку.
Добавь подраздел «Адаптивная глубина ревью» в SKILL.ru.md (§9, после «Батчинг подфаз»):
классификация риск-среза → глубина (`full`/`light`/`none`), дефолт `full`, `light`/`none` только с
обоснованием, сомнение → `full` (fail-safe); D6-инвариант (full-классы всегда full); батч наследует
глубину = МАКСИМУМ риска (ссылка на «Батчинг подфаз» P4.2, не переопределять) → регенерация SKILL.md
(генератор prompts/generate/claude-canon-from-ru.md) → check-translations.sh --stamp → skiller
registry; заметка в plan-exec.md (глубина reviewer-стадии следует колонке `Review`) — строго по
Scope/Rules P4.3. НЕ трогать plan_lint.py (§3 не парсится), НЕ править код dev-loop.js паков
(канонизация принципа, scope excluded). Закрой item по протоколу (§8): item-коммит по Files →
bookkeeping → перезапись handoff → lint (--baseline HEAD).
```

**Done:** P4.2 закрыт 🟠 (регенерённые skills.json/budget.md вне Files — паттерн P2.1/P3.1/P3.2/P4.1,
5-й раз). Канон-форма §3 Routing расширена двумя ОПЦИОНАЛЬНЫМИ колонками — `Batch` (id группы подфаз
одной сессии) и `Review` (глубина `full`|`light`|`none`, дефолт `full`) — в §9 `SKILL.ru.md` (SSOT)
+ регенерён `SKILL.md`; легаси-форма `| Items | Model/effort | Exec | Почему |` явно валидна
(back-compat). Подраздел **«Батчинг подфаз»** в §9 (RU+EN): критерий слияния (низкий coupling +
совместимые Model/Exec + совместимая глубина Review), «каждая подфаза несёт свою команду → отвал в
manual», инвариант «результат > экономии» (батч = МАКСИМУМ риска, `Review=full` не сливать под
«пропуск подтверждения»). Заметки в `plan-design.md` (§3 форма) и `plan-exec.md` (серия батча +
глубина = максимум риска). `plan_lint.py` не тронут (§3 не парсится, back-compat подтверждён 0 новых
ERROR/WARN на легаси-§3 этого плана). OQ-1 закрыт D12. Item-коммит `8a0f2f6`.

**Remaining:** P4.3 (адаптивная глубина ревью — наполняет enum `Review` классификацией риск→глубина,
sonnet/high manual, D14) — последний item фазы P4; после него P4 терминальна → `/task:plan-close P4`
→ `/task:plan-audit P4`. Далее P5 (fix-стратегия plan-design + архитектурный апгрейд, скелет,
детализируется `/task:plan-design ... P5`).

**Sources of truth:** `phases/P4.md` (Phase Context + P4.2 Completion Notes/Known Deviations + P4.3
ТЗ) · `plan.md` (§3 Routing P4.3, §4 Status Board P4 🟡 0/3 — два 🟠 не в счёте 🟢, §5 D12–D14, §6
Update Log) · `packages/skiller/skills/general/plan-protocol/SKILL.ru.md` §9 (форма §3 Routing
+Batch/Review + «Батчинг подфаз» — предпосылка P4.3: enum `Review` уже введён) · `findings/P1-recon.md`
(§4 dev-loop risk-adaptive, §5-P4, §6 RAG judge-panel high-stakes only).

**Open risks:**
- **P4.3 после P4.2:** общий файл `SKILL.ru.md` — P4.3 наполняет классификацией enum `Review`,
  введённый P4.2 в §9; строит ПОВЕРХ «Батчинг подфаз» (ссылается на батч-инвариант дословно, не
  переопределяет). Конфликта нет (соседние подразделы §9), но регенерация EN + `skiller registry`
  обязательны (иначе дрейф `skills.json`/`budget.md`).
- **Files skill-item'ов не несут реестровые артефакты** (5-й повтор): P4.3 закроется тем же 🟠, пока
  plan-design не внесёт `skills.json`/`budget.md`/`marketplace.json` в Files skill-правящих item'ов.
  Кандидат в канон (P4.1/P4.2 Known Deviations).

**Workarounds/Deferred/Open questions:**
- workarounds: —
- deferred: P5 детализация (fix-стратегия + архитектурный апгрейд, ось B); rollout доставки гейта
  `workflow-craft` (пост-OQ-3, deleg skiller/maind); launch-block вне `plan-*` (OQ-2).
- open_questions: **OQ-2** (launch-block в `dev.md`/`fix.md` — pending) · **OQ-3** (канал доставки
  гейта — квантифицирован P3.5, рекомендация A=CORE_SKILLS, pending за Owner). OQ-1 — Resolved→D12.

**Context:** handoff свежий — рекомендован /clear перед следующим item.
