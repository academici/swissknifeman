# HANDOFF — 2026-07-13 — after P2.7

**Next:** `/task:plan-exec 2026.07.13-PLAN-PROTOCOL-GAP P2.8`

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | high — §3 Routing: `P2.8 \| opus/high \| manual` (терминальный item фазы: canon-authoring — регенерация EN-канона промт-генератором + сверка, что все правила доехали) |
| Context | NEW SESSION — item закрывает фазу, свежий контекст под ручную проверку регенерации |
| Суть | Терминальный item фазы P2: `version: 2.3.0 → 2.4.0` (D25), регенерация `SKILL.md` из `SKILL.ru.md`, `check-translations.sh --stamp`, `skiller registry`, обязателен ПОЛНОСТЬЮ зелёный `packages/skiller/scripts/validate.sh` (правило фазовой когерентности §6/D17) |

```
ЗАПУСК ВРУЧНУЮ (Exec=manual, §9 SSOT-канона plan-protocol): /task:plan-exec ПИНИТ sonnet/medium
и по собственному routing-гейту (P2.1) обязан отклонить P2.8 (Routing = opus/high). Запусти
под /model opus + /effort high (или /task:plan-run 2026.07.13-PLAN-PROTOCOL-GAP P2.8, D18).

Исполни item P2.8 плана 2026.07.13-PLAN-PROTOCOL-GAP (репо swissknifeman) строго по ТЗ:
plans/2026.07.13-PLAN-PROTOCOL-GAP/phases/P2.md, раздел «### P2.8 — version 2.4.0 + регенерация
EN-канона + registry (терминальный)» — все 16 полей. Правила плана: plan.md §2 Execution Rules,
§5 D25, §6 SSOT-канона (`SKILL.ru.md`) после P2.5/P2.6 (коммит-гигиена, фазовая когерентность).
```

**Done:** P1 терминальна (`4c03715`, `b45cd51`). Фаза P2 — **6/8 🟢** (P2.4 понижен до 🟠,
P2.7 закрыт 🟢):
`38954ab` P2.1 §9 routing-гейт · `cd749ab` P2.2 §6 status-rule · `1451ed9` P2.3 §4/§11 Contracts +
линтер · `365079c` P2.4 snippets + EN-канон 2.3.0 (**переоценён P2.7: 🟢 → 🟠 Done with
deviations** — 6-й material-триггер §6, D21/D22) · `c90b5fb` реопен P2 по RED-аудиту (D21–D25) ·
`4a4af60` P2.5 §6 коммит-гигиена + 6-й material-триггер (D22) · `9f3ec28` P2.6 §3/§4 носитель
развилок (D23) · **P2.7 — ремедиация плана по аудиту**.

Что даёт P2.7: (1) статус P2.4 приведён к предикату §6 — коммит `365079c` нёс
`packages/skiller/lib/skiller/integrate.py` (bypass-дефолт auto-approve) вне `Files`/`Scope`;
правка признана НАМЕРЕННЫМ решением владельца (D21), код НЕ откатывается, `365079c` НЕ
переписывается — переоценён только статус и Known Deviations P2.4 (провенанс: D21/D22 +
Update Log; CHANGELOG — P4.3); (2) 4 развилки `plan.md` `## Обсуждение` получили
`**Статус:** Resolved → D#` (п.1→D1/D3 · п.2→D5/D6/D11 · п.3→D10 · п.4→D9), `open-questions.md`
НЕ заведён (незакрытых развилок нет, правило §3 после P2.6); (3) F4: Completion Notes P2.1 —
«23 попадания» заменено на фактические **21** (прогон команды из Validation P2.1). Блок
`## Audit P2` в `phases/P2.md` НЕ трогался (append-only) — три его строки по-прежнему цитируют
«23 попадания» как факт находки, это ожидаемо (Known Deviation ниже).

**Remaining:** P2.8 (терминальный: version 2.4.0 + регенерация EN-канона + `skiller registry`,
opus/manual — СЛЕДУЮЩИЙ) → повторный аудит P2 → P3 (5 items) → P4 (3 items).

**Sources of truth:** `plans/2026.07.13-PLAN-PROTOCOL-GAP/plan.md` (Meta, §2 Execution Rules,
§3 Routing, §5 D-лог D1–D25, `## Обсуждение` — теперь со статусами) · `phases/P2.md` (ТЗ P2.8 +
Completion Notes P2.1–P2.7 + append-only блок `## Audit P2`) · `phases/P3.md`, `phases/P4.md` (ТЗ
следующих фаз) · SSOT канона: `packages/skiller/skills/general/plan-protocol/` (`SKILL.ru.md` —
источник, версия ещё 2.3.0 до P2.8; `SKILL.md` — EN-канон, ещё не регенерирован; `snippets/`) ·
`packages/task/lib/task/plan_lint.py`.

**Open risks:**
- **Два производных гейта скилла остаются красными** (`packages/skiller/scripts/validate.sh`):
  `check-translations` (EN-канон протух с P2.5/P2.6) И `registry --check` (дрейф `skills.json` +
  `docs/guide/budget.md` от `snippets/plan-template.md`, P2.6). Оба снимает P2.8 (терминальный
  item, уже в его Scope/Files — план менять не нужно). Легально по §6/D17 только потому, что
  терминальный item назван; P2.7 сам их не касался (Scope Excluded — правка SSOT-канона уже
  сделана к моменту P2.7).
- **Правила уже в SSOT, но команды `/task:plan-*` их ещё не исполняют** (фаза P3): routing-гейт,
  status-rule, коммит-гигиену и носитель развилок применяет только читающий человек/агент.
- P4.2 правит ЧУЖОЙ репозиторий (Brain-vault, план REGHUB) — коммит там отдельный.

**Workarounds/Deferred/Open questions:**
- workarounds: `check-translations.sh --stamp` ДОПИСЫВАЕТ второй маркер `ru-source-sha256`
  вместо замены плейсхолдера `PENDING` — строку-заглушку удалять вручную (P2.4 Known Deviations);
  понадобится снова в P2.8. Validation-команды ТЗ P2.7 п.2/п.3 (`grep -c "Статус:\*\* Resolved →
  D"` / `grep -n "23 попадания"`) буквально ловят и append-only блок `## Audit P2` + описательную
  прозу самого P2.7 (Why/Scope/Validation его же ТЗ), давая 6/5 вместо ожидаемых 4/0 — целевые
  правки (4 строки статуса в `## Обсуждение`, число в P2.1 Completion Notes) сделаны верно и
  подтверждены прицельным grep по номерам строк; расхождение — известное несовершенство самой
  Validation-команды ТЗ, не дефект исполнения (process, см. Known Deviations item'а).
- deferred: фикс `check-translations.sh --stamp` (дефект skiller, отдельный item вне плана);
  миграция §3 Routing / `## Обсуждение` живых планов на канон-форму (back-compat); заполнение
  `## 7. Contracts` в живых планах (REGHUB — P4.2); кросс-репо push-уведомление (роадмап).
- open_questions: развилки `plan.md` `## Обсуждение` — все четыре теперь несут
  `**Статус:** Resolved → D#` явной строкой. Незакрытых развилок нет →
  `open-questions.md` плану не заводится (правило §3 после P2.6).
