# HANDOFF — 2026-07-27 — after P5.3

**P5.3 эскалирован 🔴 Blocked ДО правки `config.json`** (замер сделан, мутация НЕ начата).
Детерминированный скан флота (`artifacts/P5.3/scan_serena_pin.py --json`, снимок
`artifacts/P5.3/serena-pin-drift.json`, 2026-07-27) прошёл все 15 проектов с `mcp.code:true`:
10 несут живую запись `serena` в `.mcp.json` (все непиннованы, все резолвят одинаково — `Serena
1.6.2.dev0`, все `unmanaged-target` на `maind sync --only mcp --dry-run` — дефект уже адресован
P10.4/D106, тир 1 структурно недостижим, находка не новая); 5 без живой записи `serena`
(`azguard`/`botkit`/`dterema`/`dterema-app`/`sibintek-insiders`) — переносить пин пока некуда.
**Находка, требующая владельца:** RAG-проверка (`perplexity-web`, 2026-07-27) показала, что
последний СТАБИЛЬНЫЙ тег `oraios/serena` — `v1.6.1` (2026-07-21), что новее объявленного в
постановке item'а пина `v1.5.3`, а фактически резолвящаяся версия `1.6.2.dev0` новее даже
`v1.6.1` (dev-сборка main после тега). Implementation Rules item'а прямо запрещают выбирать
версию пина молча в этом случае («если она НОВЕЕ — это откат флота, решение владельца») —
сработало буквально. Детали, обе версии и их цена — `phases/P5.md` P5.3 Completion Notes +
`findings/P5.3-serena-pin-and-provider-gate.md` §3.

**Next:** `/task:plan-design 2026.07.25-ECO-OPT P5.3`

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | high — owner-гейт по выбору версии пина, требует D#-записи и правки ТЗ item'а |
| Context | NEW SESSION — шаг-не-item |
| Суть | Владелец выбирает версию пина Serena (`v1.5.3` объявленный дефолт vs `v1.6.1` последний стабильный тег) по факту `findings/P5.3-serena-pin-and-provider-gate.md` §3; `plan-design` фиксирует D#, синхронизирует Scope Included/Implementation Rules P5.3 с решением; затем `/task:plan-run 2026.07.25-ECO-OPT P5.3` продолжает правку `config.json` |

```
/task:plan-design 2026.07.25-ECO-OPT P5.3
```

**Done:** design-конвейер (3/3 паса + design-аудит RED + закрытие всех находок) · **P10.1**
(гейт кодов границ) · **P10.2** (гейт ссылок-доказательств) · **P10.3** (резолвинг пути плана) ·
**P10.4** (усыновление unmanaged-target тиром 1, D106) — все 4 items фазы P10 терминальны
(3🟢+1🟠), первая такая фаза этого плана; `plan.md` § «Phase Index» держит её строку `🟡 In
progress» НАРОЧНО — переход в терминальный статус доски делает `plan-close`, не эта команда ·
**P8.1** (отчёт закрытия фазы) · **P8.2** (`Consequences` + словарь зрелости) · **P8.3**
(`CHECKPOINTED`) · **P9.1** (`review-gate` с содержанием) · **P2.1** (Brain model-notes) ·
**P3.2** (maind MCP tool-result trimming) · **P1.2** (канон D3 + бэкфилл) — **11/40 items
закрыто**, P10 терминальна, 5 фаз в работе (P8 — 3/9 терминальны факт., P9 — 1/4, P2 — 1/3,
P3 — 1/6, P1 — 1/2). P5.3 — измерение сделано, мутация заблокирована owner-гейтом (не
засчитывается в закрытые).

**Remaining:** 29/40 items (P5.3 — в работе, заблокирован). Волна 1 (девять оставшихся items
без гейтов, свободный порядок — P5.3 временно снят из свободного выбора до ответа владельца)
продолжается; далее волны 2–5 по карте `roadmap.md`. **P10 готова к `/task:plan-close
2026.07.25-ECO-OPT P10`** когда владелец сочтёт нужным. P2.3 — ПОСЛЕ P8.1/P8.2/P8.3 и P6.3
(D93). P6.1 — ПОСЛЕ P9.1 (условие снято). P4.2 — ПОСЛЕ P3.2 (условие снято).

**Sources of truth:** `plan.md` (§2 Execution Rules; §3 Routing; §5 D1–D106; §7 Contracts;
Обсуждение 1–19; `## Audit design`) · `phases/P5.md` (P5.3 — эскалация, Completion Notes,
Pending Work, Возобновление) · `findings/P5.3-serena-pin-and-provider-gate.md` (карта дрейфа
+ обоснование эскалации, обе версии на столе) · `artifacts/P5.3/scan_serena_pin.py` +
`serena-pin-drift.json` (снимок ДО) · `phases/P10.md` (P10.1–P10.4 Completion Notes, фаза
терминальна) · `roadmap.md` (волна 1) · `open-questions.md` · машинные гейты
`plans/cross-plan-files.py`, `plans/verify-citations.py`, `packages/task/scripts/plan-lint.py` ·
канон `packages/skiller/skills/general/plan-protocol/SKILL.ru.md` §§6, 8, 9.

**Open risks:**
- **P5.3 заблокирован owner-гейтом версии пина Serena** (новое, этот заход): `v1.5.3`
  (объявленный) vs `v1.6.1` (последний стабильный тег, RAG-подтверждено) — фактически крутится
  ещё новее (`1.6.2.dev0`). До ответа владельца `config.json`/`.mcp.json` флота НЕ правятся.
- **Дефект рендерера `.mcp.json` — системный, не заведён отдельным item'ом** (P10.4 Pending
  Work, D106): тир 1 D92 корректен, но недостижим, пока конвенция не сведена. Кандидат
  `roadmap.md`.
- **Остаточный failing-тест `test_local_skills_reference_on_demand_model`** (P3.2 Pending
  Work) — краснит `packages/maind/scripts/test.sh`/`validate.sh` для любого следующего item'а
  пакета `maind`.
- **`packages/task/lib/task/plan_lint.py` несёт 8 нерезолвящихся бэйр-ссылок `P0.3 рек#N`**
  (P1.2 Pending Work) — источник неясен.
- **`plans/verify-citations.py` первым прогоном нашёл 39 находок на этом же плане** (P10.2
  Pending Work) — follow-up item не заведён.
- **Файл `plans/verify-citations-known-exceptions.json` не заведён** (P10.2 Known Deviation 2).
- **`README.md:122` ссылается на несуществующий `roadmap/self-learning-memory.md`** (P10.3
  Pending Work).
- **`research/11` §2 частично отменён D103, файл не переписан** — сверить при детализации P8.5.
- **Гейт `Consequences` в день внедрения ловит ноль записей** (forward-only, D103).
- **Протокол закрытия молчит до первой терминальной фазы — она наступила (P10).**
- **Гейт кодов границ активен И бинарен независимо от статуса** (`_lint_write_site_codes_44`).
- **Двенадцать внутриплановых связок держатся ТЕКСТОМ и машине невидимы** (§2 плана).
- Prior-риски в силе (не повторяются дословно): P3.1 нельзя закрыть без оператора · P3.5 —
  самая «дальнобойная» правка · корневой `CLAUDE.md`/`AGENTS.md` — три писателя (P1.2/P3.6/P6.3,
  D79) · P8 держит шесть оставшихся items на горячем hotspot'е · P9 не параллелится · P7.1
  работает на живых items · LAN-стадия памяти: секрет — единственный предохранитель ·
  pressure-eval P6.3 по построению слаб.

**Workarounds/Deferred/Open questions:**
- **workarounds:** двенадцать связок «порядок вместо инструмента»; `STALE_SOURCE`/`UPDATE` для
  тира 1 усыновления (P10.4); пересечения по корневым файлам — чтением; человеческий арбитраж
  вместо LLM-judge (D71); правило активации плагина Codex — текстом (D84); `## 7. Contracts` —
  каталог, не машинная сверка (D97); собственный файловый счётчик петли review-gate (P9.1);
  короткие ссылки-доказательства без каталога сознательно НЕ резолвятся (P10.2); резолвер
  `core.resolve_plan_dir` не экспортирован через `core/__init__.py` (P10.3).
- **deferred:** всё из `roadmap.md` § «Отложенное» + починка системного расхождения рендерера
  `.mcp.json` (P10.4, D106) + follow-up на 39 находок `verify-citations.py` (P10.2) +
  `verify-citations-known-exceptions.json` (P10.2) + битая ссылка `README.md:122` (P10.3).
- **open_questions:** без изменений этим заходом (OQ-9 уже закрыта P10.4/D106). Новый
  owner-вопрос (версия пина Serena) живёт в `phases/P5.md` P5.3 Pending Work/blockquote и
  `findings/P5.3-…`, НЕ дублируется в `open-questions.md` — это решение владельца по факту
  Implementation Rules item'а, формализуется через D# в `plan-design`, а не отдельным пунктом
  реестра открытых вопросов.
