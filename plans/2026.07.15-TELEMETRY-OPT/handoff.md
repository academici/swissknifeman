# HANDOFF — 2026-07-15 — after P2.2

**Next:**

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | high — §3 Routing: детализация фазы (архитектурное решение), MANDATORY |
| Context | NEW SESSION — шаг-не-item |
| Суть | Детализировать фазу P3 (model-routing аудит) — сейчас скелет; выбрать гранулярность аудита (Обсуждение §1: task-команды vs phase-токены, см. OQ-1) и расписать items |

```
/task:plan-design 2026.07.15-TELEMETRY-OPT P3
```

**Done:** P2.2 закрыт (item-коммит `54eb431`) — CORE-скилл `general/anti-drift` получил
подсекцию «Файловая гигиена операций» (RU-источник + регенерённый EN, `version` 0.2.1→0.3.0):
read-before-edit (нативный гейт всё равно отклонит попытку без Read этой сессии), якорь-гигиена
(`old_string` дословно из свежего Read, крупный уникальный контекст, `replace_all` для повторов),
анти-reread (не перечитывать без Edit/Write третьей стороной с последнего Read) — якорь на
реальный драйвер P2.1 (reread 342 vs edit-fail 55), без имён проектов (анти-bloat).
`check-translations.sh --stamp` + `skiller registry` (идемпотентно) + `validate.sh` (216 skills,
66 warnings — унаследованный долг, не anti-drift) прогнаны. Память: `mem_mrlsx29c_6cf4c82bd422`.
**Фаза P2 терминальна** (2/2 🟢 Done).
**Remaining:** P3 (model-routing аудит, скелет) → P4 (permission-friction, скелет) —
детализация через `/task:plan-design`. P5 (discovery) уже детализирован, независим от P3/P4
(может исполняться параллельно по решению Owner, порядок фаз D2 рекомендует P3→P4, не жёсткий
блок для P5).
**Sources of truth:** plans/2026.07.15-TELEMETRY-OPT/plan.md · phases/P2.md ·
findings/P2-churn-inventory.md · packages/skiller/skills/general/anti-drift/SKILL.ru.md ·
packages/skiller/skills/general/anti-drift/SKILL.md.
**Open risks:** нет новых.
**Workarounds/Deferred/Open questions:**
- workarounds: —
- deferred: как в P1 (детекция релончей между сессиями, разбор кейсов baseline построчно,
  чтение `<task-notification>` в run-report) — не изменилось.
- open_questions: OQ-1 (гранулярность P3-аудита — task-команды vs phase-токены, `Обсуждение §1`)
  ждёт детализации P3, решается в ней. OQ-2/OQ-3 — закрыты (D7/Resolved).
