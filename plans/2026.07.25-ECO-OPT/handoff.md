# HANDOFF — 2026-07-27 — after P3.2

**P2.1 закрыт 🟢** (Brain-коммит `16e1ec6`, swissknifeman item-коммит `8b88d8fd`). Две
рабочие ноты в Brain по форме `fable-5-prompting.md`: `opus-5-prompting.md` (over-verification/
scope-расширение, thinking-disabled артефакты) и `sonnet-5-prompting.md` (буквальность
инструкций, effort-мэппинг S5 medium≈S4.6 high / S5 high≈S4.6 max, confidence-level на
находку в code review, +30% токенайзер). Указатели добавлены в `prompting.md`, две карточки —
в `docs/reference.md` (Sonnet 5 гайд + отдельный Effort-док). Validation зелёная (grep-пороги
first-party ссылок ≥3/3, оба указателя на месте, `git status` в Brain пуст после коммита).
Deviations нет.

**P3.2 закрыт 🟠** (item-коммит `03c529ba`). Живой замер 11 инструментов maind MCP на узле
`project:swissknifeman` (`findings/P3.2-maind-tool-result-sizes.md`) показал: `maind_projects_list`
переступал целевой потолок 10 000 токенов консервативной оценкой (10 593 chars/2.5) ДО правки.
Реализована единая воронка `_content()` (`packages/maind/lib/maind/mcp.py`): рычаг (1) — снятие
`indent=2` над порогом — закрыл наблюдаемый избыток целиком (крупнейший ответ ушёл до ~8 276
оцен. токенов); рычаг (3) — потолок + PARTIAL-receipt (`truncated`/`returned_count`/
`total_count`/`hint`) на крупнейшем топ-уровневом списке, генерически (без ветвления по имени
инструмента), бинарным спуском — реализован и покрыт 6 синтетическими тестами
(`TestContentTrimming`), но на живом узле не наблюдался «в бою» (честно отмечено в Completion
Notes и findings). Description-cap 2KB — все 11 инструментов в пределах, отдельный тест
добавлен. **Единственное отклонение (делает статус `🟠`):** `bash packages/maind/scripts/
test.sh`/`validate.sh` несут один пре-существующий failing-тест (`test_local_skills_reference_
on_demand_model`, `test_p13_cross_project_memory_docs.py` — подтверждено `git stash` на дереве
ДО этого item'а), вне `Files` P3.2 — фикс-предложение в Pending Work `phases/P3.md` P3.2.
Детали — `findings/P3.2-maind-tool-result-sizes.md`; закрытие — `phases/P3.md` P3.2 Completion
Notes.

**Next:** волна 1 продолжается (свободный порядок) — следующий готовый solo-item батча B1.

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | medium — Routing B1 (`implementation/medium`, `plan-exec`) |
| Context | continue (/clear) — ручной item |
| Суть | P1.2: канон «полный PLAN-ID в код-ссылках» (D3) + бэкфилл голых `Pn.m`-ссылок в lib-коде пакетов; независим от P2.1/P3.2 (свои Files, roadmap-порядков не делит) |

```
/task:plan-exec 2026.07.25-ECO-OPT P1.2
```

**Done:** design-конвейер (3/3 паса + design-аудит RED + закрытие всех находок) · **P10.1**
(гейт кодов границ) · **P8.1** (отчёт закрытия фазы) · **P8.2** (`Consequences` + словарь
зрелости) · **P8.3** (`CHECKPOINTED`) · **P9.1** (`review-gate` с содержанием) · **P2.1**
(Brain model-notes Opus 5/Sonnet 5) · **P3.2** (maind MCP tool-result trimming) — 7/40 items
закрыто, 3/10 фаз в работе (P10 — 1/4, P8 — 1/9 по `Items 🟢/всего` (фактически 3/9
терминальны), P9 — 0/4 (фактически 1/4 терминален), P2 — 1/3, P3 — 0/6 по счётчику 🟢
(фактически 1/6 терминален: P3.2 🟠)). **Волна 0 (субстрат автоматизации, D93) полностью
закрыта.**

**Remaining:** 33/40 items. Волна 1 (девять оставшихся items без гейтов, свободный порядок) —
следующая; далее волны 2–5 по карте `roadmap.md`. Долги P10 (B1'): P10.3 → P1.2 → P10.2;
P10.4 — отдельной manual-сессией. P2.3 — ПОСЛЕ P8.1/P8.2/P8.3 и P6.3 (D93). P6.1 — ПОСЛЕ
P9.1 (условие снято закрытием P9.1). P4.2 — ПОСЛЕ P3.2 (условие снято этим закрытием — D32,
общий носитель `packages/maind/lib/maind/mcp.py`).

**Sources of truth:** `plan.md` (§2 Execution Rules — двенадцать связок, правило печати
кодов границ; §3 Routing — строки P2.1/P3.2; §5 D1–D105; §7 Contracts; Обсуждение 1–19; блок
`## Audit design — 2026-07-27`) · `phases/P2.md` (P2.1 Completion Notes, фаза остаётся 🟡 —
P2.2/P2.3 ещё не стартовали) · `phases/P3.md` (P3.2 Completion Notes, фаза остаётся 🟡 —
P3.1/P3.3/P3.4/P3.5/P3.6 ещё не стартовали) · `findings/P3.2-maind-tool-result-sizes.md`
(живой замер до/после, воспроизводимая команда) · `roadmap.md` (волны 0–5 — волна 0 закрыта,
волна 1 в работе) · `brief/00-brief.md` + `brief/01-refinements.md` ·
`research/22-reconcile-2026-07-26.md` · `findings/` и `research/01–21` · `open-questions.md` ·
машинные гейты `plans/cross-plan-files.py` и `packages/task/scripts/plan-lint.py` · канон
`packages/skiller/skills/general/plan-protocol/SKILL.ru.md` §§6, 8, 9.

**Open risks:**
- **Остаточный failing-тест `test_local_skills_reference_on_demand_model`** (см. P3.2 Pending
  Work выше) — не блокирует `plan-lint`/закрытие (вне `Files` P3.2), но краснит
  `packages/maind/scripts/test.sh`/`validate.sh` целиком для любого следующего item'а пакета
  `maind`, который прогонит эти команды как Validation; фикс-предложение задокументировано,
  не исполнено (не в Scope P3.2).
- **`research/11` §2 частично отменён D103, а сам файл не переписан** (слой 2 append-only):
  читатель, открывший спеку без `research/23` §1, возьмёт стем-лист, который ловит ноль.
  Ссылка-предупреждение стоит в `Required Reads` P8.2 первой строкой. **P8.5 читает ту же §2**
  (словарь зрелости) — при её детализации сверить.
- **Гейт `Consequences` в день внедрения ловит ноль записей** (forward-only) — названо честно
  в D103 и в докстринге/каноне; если формулировку потерять — приём выродится в галочку.
- **Протокол закрытия включён на ЭТОМ плане и молчит до первой терминальной фазы.** Гейт «фаза
  терминальна, а файла нет» сработает на первом же `plan-close <ID> Pn`. У двух других живых
  планов протокол НЕ включён (решение владельца, Pending Work P8.1).
- **Гейт кодов границ активен И бинарен независимо от статуса** (`_lint_write_site_codes_44`,
  D76): каждый item, закрываемый `🟢`/`🟠` с `Updated ≥ 2026-07-27`, обязан нести
  каноническую строку `write-site:` с ОБОИМИ `allow`.
- **Двенадцать внутриплановых связок держатся ТЕКСТОМ и машине невидимы** (§2 плана);
  `plans/cross-plan-files.py --strict` — «живых пересечений: 0», связки он не проверяет.
- **`stop_hook_active` теперь подтверждён живым payload'ом** (findings P9.1 §3.4) — будущий
  item может рассмотреть его как более дешёвую альтернативу файловому счётчику диспетчера;
  не решено, кандидат в roadmap.
- Prior-риски в силе (не повторяются дословно): P3.1 нельзя закрыть без оператора · P3.5 —
  самая «дальнобойная» правка · корневой `CLAUDE.md`/`AGENTS.md` — многописательские · P8
  держит шесть оставшихся items на горячем hotspot'е · P9 не параллелится (P9.2/P9.3/P9.4
  остаются в строгой цепочке волны 5) · P7.1 работает на живых items · LAN-стадия памяти:
  секрет — единственный предохранитель · pressure-eval P6.3 по построению слаб.

**Workarounds/Deferred/Open questions:**
- **workarounds:** двенадцать связок «порядок вместо инструмента» (D32/D46/D60/D62/D68/D76/
  D81/D89/D93/D94/D100); пересечения по корневым файлам — чтением (`cross-plan-files.py`
  отбрасывает токены без `/`); человеческий арбитраж вместо LLM-judge (D71); правило активации
  плагина Codex — текстом (D84); `## 7. Contracts` — каталог, не машинная сверка (D97); сужение
  профилей не доставляется на флот (D96); миграция `Closure Protocol` на планы с терминальными
  фазами — ручная дописка closure-файлов (D42); отмена части спеки `research/11` §2 держится
  ссылкой в `Required Reads`, а не правкой файла слоя 2 (append-only, D103); собственный
  файловый счётчик петли review-gate держится РЯДОМ с `stop_hook_active` рантайма (P9.1,
  страховка); оценка токенов в `mcp.py` — grep-эвристика (chars/N), не реальный токенайзер
  (P3.2, stdlib-окружение без токенайзера).
- **deferred:** всё из `roadmap.md` § «Отложенное» (без изменений этим заходом).
- **open_questions:** без изменений этим заходом; новых не заведено.
