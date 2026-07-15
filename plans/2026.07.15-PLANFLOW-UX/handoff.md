# HANDOFF — 2026-07-15 — after P3

**Next:** /task:plan-design 2026.07.15-PLANFLOW-UX P4

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | high — детализация фазы (contract-first дизайн-флоу, новая архитектурная поверхность) |
| Context | NEW SESSION — шаг-не-item |
| Суть | Детализировать скелет P4 (contract-first дизайн-флоу + глобальный exec-план + батчинг + адаптивная глубина ревью) в исполняемые item'ы |

```
/task:plan-design 2026.07.15-PLANFLOW-UX P4
```

**Done:** Фаза P3 закрыта (🟠 Done with deviations, 5/5 items терминальны: P3.1🟠 P3.2🟠 P3.3🟢
P3.4🟠 P3.5🟢). Сдано: рекалибровка ревьюера `make-workflow` (3 ложных-RED сняты) · хардненинг 4
канон-шаблонов + эталоны §2.1 · `plan-lint` энфорс имя/место плановых workflow · harness dev-loop
embed-or-guard `SLICES` (no-slices fix) · budget-квантификация доставки гейта `workflow-craft`
(742/750 `--check-core` проекция, рекомендация канала A=CORE_SKILLS, OQ-3 обновлён — Decision
pending за Owner). `Phase Handoff` заполнен в `phases/P3.md` (агрегат Known Deviations всех 5
items). `## 4. Phase Index & Status Board` (`plan.md`) синхронизирован: P3 → 🟠 Done with
deviations.

**Remaining:** P4 (contract-first дизайн-флоу + глобальный exec-план + батчинг + адаптивная
глубина ревью, D5/OQ-1) → P5 (fix-стратегия plan-design + архитектурный апгрейд скиллов/сниппетов,
ось B).

**Sources of truth:** `phases/P3.md` (`## Phase Handoff`, P3.1–P3.5 Completion Notes) · `plan.md`
(§4 Status Board P3 🟠, §6 Update Log, §5 D9–D11) · `findings/P3-delivery-budget.md` (числа
доставки, git-якорь) · `open-questions.md` OQ-3 (рекомендация канала, Decision pending).

**Open risks:**
- **Rollout доставки гейта делегирован (НЕ выполнен в P3 — контракт):** правка
  `CORE_SKILLS`/`core-policy.json` (вариант A) ЛИБО onboard-required flag (вариант B) — только
  ПОСЛЕ резолва OQ-3 Owner'ом, исполнитель — skiller/maind. НЕ вход downstream-item'а плана.
- Вариант A заполняет CORE под потолок (742/750, 8 ток headroom) → рост CORE потребует подъёма
  target (750→800) отдельным решением.
- Наследованные P3.1/P3.2/P3.4 deviations (registry-артефакты вне `Files`; `node --check`
  Validation-пункт структурно недостижим для файлов с санкционированным top-level `return`) —
  дословный агрегат в `phases/P3.md` `## Phase Handoff`.

**Workarounds/Deferred/Open questions:**
- workarounds: —
- deferred: rollout доставки гейта (пост-резолв OQ-3, deleg skiller/maind); детализация P4–P5
  (contract-first, just-in-time, D5); launch-block вне `plan-*` (OQ-2); правило «registry-артефакты
  в Files» (P3.1 fix-предложение); правило «async-обёртка вместо буквального node --check» для
  Validation-пунктов над `dev-loop.js`/канон-шаблонами (P3.4 fix-предложение).
- open_questions: **OQ-1** (артефакт exec-плана, P4) · **OQ-2** (launch-block в `dev.md`/`fix.md`) ·
  **OQ-3** (канал доставки гейта — квантифицирован P3.5, рекомендация A=CORE_SKILLS; ждёт решения
  Owner Dmitry Vostrikov, статус Decision pending).

**Context:** handoff свежий — рекомендован /clear перед следующим шагом.
