# HANDOFF — 2026-07-27 — after P8.1

**P8.1 закрыт 🟠 Done with deviations** (item-коммит `5f5dfa73`, bookkeeping — следом).
Введён машиночитаемый отчёт закрытия фазы `plans/<ID>/closure/<Pn>.json` (схема v1) с классом
свидетельства `real`/`synthetic`/`baseline_pending`: «нет числа» теперь выражается ЗАПИСЬЮ с
причиной, а не отсутствием ключа. Активация — opt-in поле `## 0. Meta` → `Closure Protocol | v1`
(включено на ЭТОМ плане; иное значение = ERROR). Писатель — `plan-close` (режим `Pn`, новый шаг
4a, сборка механически из полей items); потребители названы и оба исполняются: `plan_lint.py`
(пять проверок) и `plan-audit` (отчёт — ПЕРВЫЙ вход ступени 1). Наш `evidence_class` разведён
одной строкой канона с закрытым перечнем классов доказательства
`recomputed`/`cross-checked`/`pinned-not-recomputable`/`unknown` (реконсайл D86, п. 2).
11 новых тестов `TestClosureReports81`, 8 из них прогнаны красными на пред-патч коде (D79).
Отклонение — дифф вне `Files` item'а (fixtures.py · version-first бампы · snippets/index.json),
детали и обоснование — `phases/P8.md` P8.1 Known Deviations.

**Next:** exec-items: task:plan-exec 2026.07.25-ECO-OPT P8.2 P8.3

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | medium |
| Capabilities | — |
| Context | `same-session — item`: батч B4a, item-by-item exec |
| Гейт | ПОСЛЕ P8.1 — **снят, P8.1 терминальна**; порядок ВНУТРИ батча обязателен: P8.2 → P8.3 |
| Суть | `Consequences` в D-записи + словарь зрелости возможности · строка `Возобновление:` в `Pending Work` (седьмого статуса НЕ вводится) |

```
/task:plan-exec 2026.07.25-ECO-OPT P8.2 P8.3
```

**Done:** design-конвейер (3/3 паса + design-аудит RED + закрытие всех находок) · **P10.1**
(гейт кодов границ) · **P8.1** (эта сессия) — 2/40 items, 2/10 фаз в работе (P10 — 1/4, P8 — 1/9).

**Remaining:** 38/40 items. Волна 0: **P8.2/P8.3** (следующий шаг, батч B4a, `plan-exec`) →
**P9.1** (manual, идёт перед P6.1). Далее волна 1 (одиннадцать items без гейтов, свободный
порядок) → волны 2–5 по карте `roadmap.md`. Долги P10 (B1'): P10.3 → P1.2 → P10.2; P10.4 —
отдельной manual-сессией. P2.3 — ПОСЛЕ P8.1/P8.2/P8.3 и P6.3 (D93).

**Sources of truth:** `plan.md` (§2 Execution Rules — двенадцать связок, правило печати кодов
границ; §3 Routing — 40 записей; §5 D1–D102; §7 Contracts; Обсуждение 1–19; блок `## Audit
design — 2026-07-27`) · `phases/P1.md`–`phases/P10.md` (P10.1 и P8.1 закрыты, детали — в их
Completion Notes) · `roadmap.md` (волны 0–5, launch-block'и, отложенное) · `brief/00-brief.md` +
`brief/01-refinements.md` · `research/22-reconcile-2026-07-26.md` · `research/11-P8-target-design.md`
(§1 — схема closure v1) · `findings/` и `research/01–21` · `open-questions.md` · машинные гейты
`plans/cross-plan-files.py` и `packages/task/scripts/plan-lint.py` · канон
`packages/skiller/skills/general/plan-protocol/SKILL.ru.md` §8 + `snippets/closure-template.md`.

**Open risks:**
- **Протокол закрытия включён на ЭТОМ плане и молчит до первой терминальной фазы.** Гейт «фаза
  терминальна, а файла нет» сработает на первом же `plan-close <ID> Pn` — закрывающая сессия
  ОБЯЗАНА собрать `closure/<Pn>.json` (шаг 4a `plan-close.md`), иначе закрытие покраснеет.
  У двух других живых планов протокол НЕ включён (решение владельца, см. Pending Work P8.1).
- **Отчёт может выродиться в ритуал** (pre-mortem `research/11` §11.1): защита — машинный
  потребитель (`real` без evidence = ERROR) плюс перепрогон команд аудитом; если `plan-audit`
  начнёт принимать `evidence` на веру, приём теряет смысл.
- **Дифф вне `Files` повторился дважды подряд** (P10.1 — производные, P8.1 — fixtures.py +
  version-first бампы): ТЗ items, правящих канон скилла, систематически не перечисляет
  `publication-versions.json`/`package.json`/`fixtures.py`. Кандидат в правило `plan-design`
  (или в чеклист DoR), а не в вечное отклонение исполнителя.
- **Гейт кодов границ активен**: каждый item, закрываемый с `Updated ≥ 2026-07-27`, обязан нести
  каноническую строку `write-site:` с обоими `allow` (P8.1 её несёт).
- **Двенадцать внутриплановых связок держатся ТЕКСТОМ и машине невидимы** (см. §2 плана);
  `plans/cross-plan-files.py --strict` — «живых пересечений: 0», связки он не проверяет.
- Prior-риски в силе (не повторяются дословно): P3.1 нельзя закрыть без оператора · P3.5 — самая
  «дальнобойная» правка · корневой `CLAUDE.md`/`AGENTS.md` — многописательские · P8 держит пять
  оставшихся items на горячем hotspot'е · P9 не параллелится · P7.1 работает на живых items ·
  LAN-стадия памяти: секрет — единственный предохранитель · pressure-eval P6.3 по построению слаб.

**Workarounds/Deferred/Open questions:**
- **workarounds:** двенадцать связок «порядок вместо инструмента» (D32/D46/D60/D62/D68/D76/D81/
  D89/D93/D94/D100); пересечения по корневым файлам — чтением (`cross-plan-files.py` отбрасывает
  токены без `/`); человеческий арбитраж вместо LLM-judge (D71); правило активации плагина Codex —
  текстом (D84); `## 7. Contracts` — каталог, не машинная сверка (D97); сужение профилей не
  доставляется на флот (D96); **новое:** миграция `Closure Protocol` на планы с терминальными
  фазами — ручная дописка closure-файлов, машинного конвертера нет (осознанно, D42).
- **deferred:** всё из `roadmap.md` § «Отложенное» (без изменений этим заходом).
- **open_questions:** без изменений этим заходом; новых не заведено.
