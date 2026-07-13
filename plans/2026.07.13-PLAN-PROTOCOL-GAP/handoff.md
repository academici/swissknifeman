# HANDOFF — 2026-07-13 — after P2.8

**Next:** `/task:plan-audit 2026.07.13-PLAN-PROTOCOL-GAP P2`

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | xhigh — фаза несёт material Known Deviations (P2.4, D21/D22) и уже прошла один RED-аудит; повторный аудит перед стартом P3 обязателен |
| Context | fresh session — handoff свежий, рекомендован /clear |
| Суть | Прогнать adversarial-аудит фазы P2 (8/8 терминальны, статус `🟠 Done with deviations`): сверить 🟢/🟠 items с git-фактами, убедиться, что ремедиация P2.5–P2.8 закрыла прежние F1–F4, no-op/scope-drift не проникли |

```
/task:plan-audit 2026.07.13-PLAN-PROTOCOL-GAP P2
```

**Done:** P1 терминальна (`4c03715`, `b45cd51`). Фаза P2 закрыта — **8/8 items терминальны**
(7 🟢 + P2.4 🟠), статус фазы `🟡 → 🟠 Done with deviations`:
`38954ab` P2.1 §9 routing-гейт · `cd749ab` P2.2 §6 status-rule · `1451ed9` P2.3 §4/§11 Contracts +
линтер · `365079c` P2.4 snippets + EN-канон 2.3.0 (🟠, D21/D22) · `c90b5fb` реопен P2 по
RED-аудиту (D21–D25) · `4a4af60` P2.5 §6 коммит-гигиена + 6-й material-триггер (D22) ·
`9f3ec28` P2.6 §3/§4 носитель развилок (D23) · `6501ea8`/`4cb9b77`/`d17ad8c` P2.7 ремедиация
плана · `bef52c7` P2.8 — EN-канон 2.4.0 + реестр (терминальный). Этой сессией: Status Board
`plan.md` (`7/8 🟡 → 8/8 🟠`) и `## Phase Handoff` в `phases/P2.md` перезаписаны (сняты
устаревшая врезка «4/4 🟢» и D24-реопен-заметка, добавлен агрегат Known Deviations фазы).

Что даёт P2.8: SSOT-канон `plan-protocol` **2.4.0** (D25) — `SKILL.ru.md` (RU-источник) и
регенерированный из него `SKILL.md` (EN-канон, 620 → 650 строк; ТОЛЬКО его грузит агент)
несут ОБА новых правила фазы: (а) коммит-гигиена item'а — `git add` по явным путям, `git add -A`
запрещён, чужой дифф НАЗЫВАЮТ, а не трогают + 6-й material-триггер «дифф вне `Files`» → 🟠;
(б) носитель развилок — секция `## Обсуждение` (провенанс, статус у каждой развилки) vs
`open-questions.md` (трекер незакрытого) + переписанный пункт DoR-чеклиста §7. Реестр
(`skills.json`, `docs/guide/budget.md`) перегенерён `skiller registry`; CORE-резидент не вырос
(694 ток / 750 — `description` не менялся).

**Remaining:** повторный аудит P2 (Next, СЛЕДУЮЩИЙ) → P3 (5 items: перенос правил канона в
сами команды `/task:plan-*`) → P4 (3 items: регресс по флоту, закрытие эскалации REGHUB, доки).

**Sources of truth:** `plans/2026.07.13-PLAN-PROTOCOL-GAP/plan.md` (Meta, §2 Execution Rules,
§3 Routing, §5 D-лог D1–D25, `## Обсуждение` со статусами) · `phases/P2.md` (Completion Notes
P2.1–P2.8 + append-only блок `## Audit P2` + свежий `## Phase Handoff`) · `phases/P3.md`,
`phases/P4.md` (ТЗ следующих фаз) · SSOT канона:
`packages/skiller/skills/general/plan-protocol/` (`SKILL.ru.md` 2.4.0 — источник; `SKILL.md` —
EN-канон, свежий; `snippets/`) · `packages/task/lib/task/plan_lint.py`.

**Open risks:**
- **Оба производных гейта скилла ЗЕЛЁНЫЕ** (`packages/skiller/scripts/validate.sh` — exit 0):
  риск фазовой некогерентности §6/D17 закрыт, отдельного действия не требует.
- **Правила уже в SSOT, но команды `/task:plan-*` их ещё не исполняют** (фаза P3): routing-гейт,
  status-rule, коммит-гигиену и носитель развилок применяет только читающий человек/агент.
- Фаза P2 закрыта **🟠**, не 🟢: material-отклонение P2.4 (D21/D22) сохраняется в статусе —
  закрыть 🟢 значило бы воспроизвести F2 на уровне фазы.
- P4.2 правит ЧУЖОЙ репозиторий (Brain-vault, план REGHUB) — коммит там отдельный.

**Workarounds/Deferred/Open questions:**
- workarounds: `check-translations.sh --stamp` ДОПИСЫВАЕТ второй маркер `ru-source-sha256`
  вместо замены плейсхолдера `PENDING` — строку-заглушку удаляли вручную (P2.4, снова P2.8);
  файл корректен (ровно один маркер), обходка живёт в процессе, не в артефакте.
- deferred: фикс `check-translations.sh --stamp` (дефект skiller, отдельный item вне плана);
  миграция §3 Routing / `## Обсуждение` живых планов на канон-форму (back-compat); заполнение
  `## 7. Contracts` в живых планах (REGHUB — P4.2); кросс-репо push-уведомление (роадмап).
- open_questions: все четыре развилки `plan.md` `## Обсуждение` несут `**Статус:** Resolved → D#`
  → незакрытых нет, `open-questions.md` плану не заводится (правило §3).
</content>
