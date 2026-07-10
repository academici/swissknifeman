# HANDOFF — 2026-07-11 — after P3.5

**Next:** /task:plan-exec SKM-ROADMAP-005 P4.1

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | medium |
| Context | fresh session |
| Суть | Исполнение возобновляется с P4.1 (канон планов — репо-дом по умолчанию, имена с `supersedes`, дом workflow-скриптов `plans/<ID>/workflows/`; правит `plan_lint`/`plan-protocol`, в т.ч. часть 1.6 `workflow-craft`, D2) |

````
/task:plan-exec SKM-ROADMAP-005 P4.1 — исполнить первый item фазы P4 (канон планов) строго по ТЗ.
Cold-start reads: plans/SKM-ROADMAP-005/phases/P4.md (ТЗ P4.1, Required Reads) ·
plans/SKM-ROADMAP-005/plan.md (§5 Decision Log D2/D16/D24+ — канон имён/мест) ·
packages/skiller/skills/general/plan-protocol/SKILL.md (SSOT протокола) ·
packages/task/lib/task/plan_lint.py (валидатор схемы) · phases/P3.md (закрыта — часть 1.6
конструктора workflow-скриптов уходит сюда, D2).
````

**Done:** Фазы **P1** (`settings-doctor`, 6/6 🟢) и **P2** (`wf-status`, 4/5 🟢+🟠) закрыты ранее.
Фаза **P3** (`workflow-craft`) закрыта 5/5 🟢: скилл-указатель `general/workflow-craft`
(двуязычный, SSOT-матрица design vs dev + explicit «не смешивать» + cross-ref на 2 полевых
эталона vault Brain, D20/D21); прошивка ссылки на конструктор в 4 команды (`dev`/`design`/
`research`/`review` — `fix`/`plan-exec` осознанно пропущены, repo-grounded); команда-гейт
`/task:make-workflow` (opus/high, D22) с интервью по `spec-interview`; выходной статический
ревьюер (13-пунктовый чеклист, зеркало README конструктора, RED блокирует выдачу).
`roadmap/README.md`: `workflow-craft` ч.1 → 🟢 внедрено (SKM-ROADMAP-005 P3); ч.2 (fleet-синтез)
осталась ⬜ — вне scope плана (D1, критерий не сработал).

**Remaining:** Исполнить P4 канон планов (6 items) → P5 changelog-discipline (3) → P6
ecosystem-glossary (4) → P7 ephemeral-дисциплина + закрытие пакета (2), phase-first
последовательно. Все четыре фазы уже развёрнуты из скелетов до полных ТЗ (design-workflow
P4→P6, rest-exec P3→P6) — исполнение, не проектирование.

**Sources of truth:** plans/SKM-ROADMAP-005/plan.md (Meta, Routing, D-лог D1–D43+) ·
plans/SKM-ROADMAP-005/phases/P1.md (закрыт — образец Phase Handoff) · phases/P3.md (закрыта,
эталон свежего Phase Handoff) · phases/P4.md · phases/P5.md · phases/P6.md · phases/P7.md
(развёрнуты) · packages/skiller/skills/general/plan-protocol/SKILL.md (SSOT протокола) ·
packages/task/lib/task/plan_lint.py (валидатор схемы)

**Open risks:**
- P1.4 Pending Work: проверка №5 даёт ложный `error` на хук-командах с интерпретатор-префиксом
  (`bash …`, `python3 …`). Вне scope P1.
- P1.6 Pending Work: `maind doctor --audit all` падает на измерении `core` (`_present_skills`) на
  части флота. `--audit settings` в изоляции не задет.
- P3: пять CHANGELOG-строк items (P3.1–P3.5) НЕ внесены — путь `CHANGELOG.md` заблокирован
  permission-deny этой среды (прецедент P2.4); формулировки на будущее зафиксированы в Pending
  Work каждого item'а phases/P3.md — внести при первой сессии со свободным доступом к файлу.
- D16 (канон имён планов `ГГГГ.ММ.ДД-КОДОВОЕ-ИМЯ`) внедряется в P4 — этот план НЕ переименовывается.

**Workarounds/Deferred/Open questions:**
- workarounds: семантика слияния `permissions.additionalDirectories` неизвестна → проверка №8
  per-layer (D15); полнота списка hook-событий не подтверждена → неизвестное событие даёт `info`.
- deferred: opt-in `UserPromptSubmit`-хук settings-doctor (D12) и активации workflow-craft (не в
  спеке); авто-починка `--fix`; часть 2 `workflow-craft` fleet-синтез (D1); часть 1.6 конструктора
  (канон места/имён скриптов) — уходит в P4 (D2); `skill-rules-sidecar`, остаток
  `self-learning-memory`, default-on `mcp-config-example-emit` (D1); P1.4/P1.6 Pending Work;
  пять CHANGELOG-строк P3 (permission-deny).
- open_questions: содержание «ephemeral-дисциплины» — снимается интервью владельца в P7.1 (D7).
