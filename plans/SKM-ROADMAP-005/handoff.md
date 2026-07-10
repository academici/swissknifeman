# HANDOFF — 2026-07-10 — after P1.6

**Next:** /task:plan-exec SKM-ROADMAP-005 P2.1

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | medium |
| Context | fresh session |
| Суть | Исполнение возобновляется с P2.1 (фазы P2 и P3 развёрнуты из скелетов, но НЕ исполнены; phase-first: P2 закрывается до P3). Начать с P2.1 — защищённый парсер transcript-директории workflow-прогона |

````
/task:plan-exec SKM-ROADMAP-005 P2.1 — исполнить первый item фазы P2 (wf-status) строго по ТЗ:
защищённый stdlib-only парсер одной transcript-директории `wf_<id>/` (journal.jsonl + agent-*.meta.json
+ sibling-скрипт `export const meta`) → dict статуса; degraded-флаг вместо трейсбека. Дом движка —
harness (D17). Cold-start reads: plans/SKM-ROADMAP-005/phases/P2.md (ТЗ P2.1, Required Reads) ·
plans/SKM-ROADMAP-005/findings/P2-workflow-transcript-format.md (формат — источник истины, не доки) ·
packages/harness/lib/harness/settings_audit.py (стиль защищённого чтения .claude/*.json).
````

**Done:** Фаза P1 (`settings-doctor`) закрыта 6/6 🟢 (движок в harness, D10). Фазы **P2**
(`wf-status`, 5 items) и **P3** (`workflow-craft`, 5 items) РАЗВЁРНУТЫ из скелетов до полных ТЗ,
DoR пройден — но обе ещё НЕ исполнены (0/5 каждая). P3: скилл-указатель `workflow-craft` в бакете
`general` skiller (D20), команда-гейт `/task:make-workflow` (opus/high, D22) + выходной статический
ревьюер (RED блокирует выдачу), SSOT две-типа-матрицы = сам скилл (D21), разведение design-only vs dev
+ cross-ref на два эталона vault Brain.

**Remaining:** Исполнить P2 (5) → затем P3 (5), phase-first последовательно. Развернуть из скелетов
`/task:plan-design SKM-ROADMAP-005 Pn` ДО `plan-exec`: P4 канон планов (6) · P5 changelog-discipline
(3) · P6 ecosystem-glossary (4) · P7 ephemeral + закрытие пакета (2).

**Sources of truth:** plans/SKM-ROADMAP-005/plan.md (Meta, Routing, D-лог D1–D22) ·
plans/SKM-ROADMAP-005/phases/P1.md (закрыт — образец Phase Handoff) · phases/P2.md · phases/P3.md
(развёрнуты) · roadmap/workflow-craft.md (спека P3) · packages/task/workflows/README.md (конструктор,
SSOT инвариантов для ревьюера P3.4) · packages/skiller/skills/general/spec-interview/SKILL.md (механика
интервью P3.3) · packages/skiller/skills/general/plan-protocol/SKILL.md (SSOT протокола) ·
packages/task/lib/task/plan_lint.py (валидатор схемы)

**Open risks:**
- P1.4 Pending Work: проверка №5 даёт ложный `error` на хук-командах с интерпретатор-префиксом
  (`bash …`, `python3 …`). Вне scope P1.
- P1.6 Pending Work: `maind doctor --audit all` падает на измерении `core` (`_present_skills`) на
  части флота. `--audit settings` в изоляции не задет.
- D16 (канон имён планов `ГГГГ.ММ.ДД-КОДОВОЕ-ИМЯ`) внедряется в P4 — этот план НЕ переименовывается.
- P3 эталоны (`wf-design-fleet.js`, `wf-agentools-drive.js`) — в vault Brain, НЕ в репо: cross-ref по
  пути, не вендорим (P3.5). На исполняющей машине без vault → пометка «эталон в vault Brain», не падать.

**Workarounds/Deferred/Open questions:**
- workarounds: семантика слияния `permissions.additionalDirectories` неизвестна → проверка №8
  per-layer (D15); полнота списка hook-событий не подтверждена → неизвестное событие даёт `info`.
- deferred: opt-in `UserPromptSubmit`-хук settings-doctor (D12) и активации workflow-craft (не в спеке);
  авто-починка `--fix`; часть 2 `workflow-craft` fleet-синтез (D1); `skill-rules-sidecar`, остаток
  `self-learning-memory`, default-on `mcp-config-example-emit` (D1); P1.4/P1.6 Pending Work.
- open_questions: содержание «ephemeral-дисциплины» — снимается интервью владельца в P7.1 (D7).
