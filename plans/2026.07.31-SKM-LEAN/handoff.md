# HANDOFF — 2026-07-31 — after P1

**Next:** `/task:plan-audit 2026.07.31-SKM-LEAN P1`

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | xhigh — фаза несёт `🟠`-item (P1.1), аудит перед продолжением на P2 |
| Context | NEW SESSION — шаг-не-item |
| Суть | Adversarial-аудит закрытой фазы P1: сверка 🟢/🟠 items с git-фактами, no-op/scope-drift, handoff |

```
/task:plan-audit 2026.07.31-SKM-LEAN P1
```

**Done:** **Фаза P1 закрыта: 🟠 Done with deviations.** Все 4 items терминальны — P1.1 `🟠`,
P1.2/P1.3/P1.4 `🟢`. Сверка `## Phase Status` (`phases/P1.md`) ↔ `## 4. Phase Index & Status
Board` (`plan.md`) без расхождений: `Items 🟢/всего` = `3/4`, статус фазы `🟠 Done with
deviations` (агрегат: хоть один `🟠`-item). `closure/P1.json` (Closure Protocol v1) собран
механически из полей items — 2 gates (`validate.sh:skiller`, `validate.sh:harness`) PASS,
`evidence_class: real` на всех items и метриках.

**Известные отклонения (собраны механически из Known Deviations items, дословно):**
- **P1.1 (material → `🟠`):** item-коммит `487e68d0` несёт правку
  `.swissknifeman/provider-artifacts.lock.json` сверх `Files` — детерминированный побочный
  продукт мандатного `harness instructions apply --authorize` (пробел ТЗ, не решение
  исполнителя).
- **P1.2 (process):** финальная запись `journal.jsonl` (`attempt: 2`) не несёт
  `friction: ["retry"]` — append-only журнал не допускает правку задним числом.
- **P1.3 (process, `🟢` по status-rule):** item закрыл OQ-4, не названный в `Scope Included`
  (только OQ-1) — снятие OQ-4 требовал `open-questions.md` ДО закрытия P1.3.
- **P1.4 (process):** порядок шагов нарушен — Pre-mutation Task Contract и пометка `🟡 In
  progress` выполнены после начала кодовой мутации; гейт всё равно пройден на фактическом
  маршруте, scope/validation не задело.

**Docs-sync (шаг 3, обязательный):** не требуется — доки фазы (`packages/skiller/docs/guide/
cli.md`, канон `root.claude-code.context-budget` во всех носителях) уже приведены к факту
собственными `Files` items P1.1/P1.3; аггрегированного `docs/`-контента фаза не заводит.

`plan-lint --baseline HEAD` (после перезаписи `handoff.md`): **0 ERROR / 1 WARN — новых от
закрытия фазы: K = 0** (WARN — латентное ложное срабатывание `ORCHESTRATION_MARKER_RE` на
цитате прежней DoR-формулировки в Completion Notes P1.1, известно с P1.1/P1.3, вне диффа
закрытия фазы). `verify-citations.py --strict` (на итоговом дереве, после перезаписи
`handoff.md`): **цитаты: 166 находок — новых от закрытия: K = 0** (обе находки —
`phases/P1.md:281`, `plan.md:223`, ссылка `root/claude-code.md:6` в тексте P1.3 — уже стояли
на коммите `58c60965`, до этого захода; остаточные 2 находки вне Scope закрытия фазы, адрес —
следующая правка ТЗ P1.3 или `plan-design`).

**Remaining:** `plan-audit P1` (гейт перед продолжением — фаза несёт `🟠`), затем **P2.1**
(solo, `Exec = manual`, frontier/high — диета канона инструкций, D59: P2 не зависит от исхода
OQ-4) и далее P2 → P3 → P4 → P5 → P6 → P7 по `roadmap.md`. Доска: P1 `3/4` (закрыта) · P2 `0/6`
· P3 `0/5` · P4 `0/6` · P5 `0/9` · P6 `0/3` · P7 `0/4`.

**Sources of truth:** `plans/2026.07.31-SKM-LEAN/plan.md` (§0 Meta v1.0.4, §4 доска P1
закрыта, §5 D1–D85, §6 Update Log — строка закрытия фазы P1) · `phases/P1.md` (`## Phase
Handoff` заполнен) · `closure/P1.json` · `findings/P1-fleet-baseline.md` ·
`packages/skiller/lib/skiller/budget.py:188–204` (пороги 16000/23000) · `open-questions.md`
(открытых пять: OQ-2 · OQ-3 · OQ-5 · OQ-6 · OQ-8) · `roadmap.md`.

**Open risks:** (прежние риски P1–P7 в силе, см. предыдущие handoff — правило двух SSOT) плюс:

- **Порог заморожен поверх модели стоимости MCP, которую P2.3 пере-издаст** (D84, осознанно) —
  P2.3 обязан ТЕМ ЖЕ item-коммитом пере-считать распределение флота и подтвердить/пере-издать
  `16 000/23 000`; выпадение этого шага из ТЗ P2.3 держит порог замороженным без гейта.
- **Числа порога средо-зависимы настолько, насколько средо-зависим baseline** (состав
  установленных плагинов — свойство машины владельца); `findings/P1-fleet-baseline.md` несёт
  якорь SHA+дату, побайтовая воспроизводимость не гарантирована.
- **`brain@brain` — сломанный плагин в чужом репозитории** (`~/Vaults/Brain/.claude-plugin/
  plugin.json`) — класс `broken` непуст у каждого проекта флота, пока манифест не починен вне
  периметра плана.
- **Диета P2/P3 имеет числовую цель, но не имеет гейта на неё** — «стало лучше» по-прежнему
  меряется сравнением с baseline вручную (P2.6), автогейта в `validate.sh` нет.
- **P1.1 material-отклонение (лок-файл вне `Files`) не устранено ретроактивно** (D82 —
  ретро-правки P1.1 нет, `🟠` остаётся закрытой записью); адрес для остальных canon-items
  (P1.3, P2.1, P5.4) — их собственный `Files` уже несёт лок-файл явно.

**Workarounds/Deferred/Open questions:** «—» / «—» / OQ-2 · OQ-3 · OQ-5 · OQ-6 · OQ-8 (пять
открытых; OQ-1 и OQ-4 закрыты предыдущим заходом — D83/D84), см. `open-questions.md`.
