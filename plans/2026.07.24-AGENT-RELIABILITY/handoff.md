# HANDOFF — 2026-07-26 — after P4.2

**Next:** design-item: task:plan-design 2026.07.24-AGENT-RELIABILITY P4.2

| Параметр | Значение |
|:--|:--|
| Model class | `frontier` |
| Effort | `high` |
| Capabilities | — |
| Model | `opus` |
| Thinking | `high` |
| Context | `НОВАЯ сессия` |
| Суть | Разобрать причину расхождения plan-protocol на P4.2: код скоупа реализован и закоммичен (`1e9006f4`), но item не закрыт — Status числился `⬜ Not started`, Completion Notes пустые, коды границ `pre_mutation`/`pre_final` не напечатаны, journal.jsonl/handoff.md не несли записи. Решить судьбу item'а (докрутка bookkeeping как `plan-exec` или иное) ПЕРЕД тем, как D90-порядок продолжится к P4.3 |

```
task:plan-design 2026.07.24-AGENT-RELIABILITY P4.2
```

**РЕЖИМ / ВХОД / СКОУП / НЕ ТРОГАТЬ (payload для запуска design-item):**

- **РЕЖИМ:** разбор остановки (не продолжение исполнения). Прогон фазы P4 остановлен на P4.2
  по строгому порядку D90 (`P4.4 → P4.5 → P4.1 → P4.2 → P4.3`); P4.3 не стартует, пока P4.2 не
  закрыт по plan-protocol.
- **ВХОД:**
  - `phases/P4.md` § `### P4.2` — Status `🔴 Blocked`, Escalation Needed `yes` + причина,
    Pending Work с sha частичного коммита `1e9006f4` (полная реализация Files-скоупа) и
    зафиксированным `git status --porcelain` (`?? .swissknife/`, посторонний, не тронут).
  - Коммит `1e9006f4` («feat(skiller): read-only composed effective-source doctor (P4.2)») —
    независимая read-only проверка (следующий по D90 заход) подтвердила: код/тесты/docs/
    CHANGELOG соответствуют Files/Scope Included/Implementation Rules P4.2. Расхождение —
    ТОЛЬКО в bookkeeping-слое (Status/Completion Notes/коды границ/journal/handoff), не в
    продукте.
  - Причина остановки дословно (см. `phases/P4.md` P4.2 Known Deviations/Escalation Needed):
    класс дефекта Ф2 (отсутствие напечатанных кодов у закрытого item'а), воспроизведённый на
    следующем по D90-порядку item'е внутри той же фазы — item формально не «закрыт», а лишь
    реализован кодом.
- **СКОУП РАЗБОРА:**
  1. Установить, почему `1e9006f4` не сопровождался plan-close (сессионный разрыв? пропущенный
     шаг ритуала?) — репо-грунтованный вывод, не догадка.
  2. Решить: закрывать P4.2 докруткой bookkeeping'а (`plan-close`/`plan-exec` над теми же
     файлами кода без новых мутаций `packages/**`) — печать `pre_mutation`/`pre_final` для
     `1e9006f4`, перезапуск Validation-команд item'а (юнит-тест, `validate.sh`, no-write
     git-diff-до/после, `plan-lint`), Status → `🟢`/`🟠` по факту.
  3. Либо иной путь, если разбор найдёт основание не принимать `1e9006f4` как есть (например,
     новый дефект, обнаруженный при перезапуске Validation).
  4. После решения — `plan-close P4.2` актуализирует `phases/P4.md`/`plan.md`/`journal.jsonl`/
     `handoff.md`, и ТОЛЬКО ТОГДА D90-порядок продолжается к P4.3.
- **НЕ ТРОГАТЬ:**
  - `plans/2026.07.18-FOREMAN`, `plans/2026.07.25-ECO-OPT` — чужие планы.
  - `git push`/`git tag`/релиз/раскатка на флот — вне полномочий любого агента этого плана; G1
    остаётся за Владельцем после packet'а P4.3.
  - Замороженные P0.3-контракты/банк, floors фазы P3 (D88) — не повышаются и не правятся.
  - P4.3 (Owner packet) — НЕ СТАРТУЕТ, пока P4.2 не закрыт по plan-protocol.

**Done:**

- **Фаза P4 доведена до DoR** заходом `plan-design … P4` (Claude Opus 5/high). Входной гейт
  «P4 не стартует до GREEN» (D81) переопределён **D89**: принят measured-scope Owner packet;
  план НЕ терминируется на `🟠`. Приёмка объявлена формально НЕ выполненной. Состав фазы —
  5 items (D90, порядок `P4.4 → P4.5 → P4.1 → P4.2 → P4.3`); оркестрация объявлена (D93).
- **P4.4 закрыт 🟠 Done with deviations** (item-коммит `4ca7af67`) — машинный гейт `plan_lint`
  напечатанных кодов границ (ремонт Ф2), ревью ATTENTION: подтверждён Major/Minor дефект
  точности предиката `_lint_write_site_codes_44`.
- **P4.5 закрыт 🟢** (item-коммит `e45d0f8f`) — Contribution gate D23 оплачен: `analyst`
  `0.1.0 → 0.2.0`, `harness` `0.3.0 → 0.4.0`; `registry --check` — «артефакты актуальны».
- **P4.1 закрыт 🟠 Done with deviations** (item-коммит `a376a64e`) — code-grounded вердикт по
  16 несущим гипотезам: 3 accept (FP-1/FP-2/FP-3), 11 reject, 2 unknown (H15/H16). Ревью
  ATTENTION: H06 mis-cite несуществующего теста, гейт `verify_claim_verdicts.py` не проверяет
  символ после `::`, Minor — правило `observation_upheld` нарушено в H05 без проверки гейтом.
- **P4.2 — код реализован и закоммичен (`1e9006f4`), НО item НЕ ЗАКРЫТ по plan-protocol** —
  прогон фазы ОСТАНОВЛЕН здесь. Независимая read-only проверка (Files/Scope Included/
  Implementation Rules) подтверждает соответствие продукта ТЗ; расхождение — только в
  Status/Completion Notes/кодах границ/journal/handoff.

**Remaining:**

- **P4.2** — закрыть по plan-protocol (см. design-item выше) прежде, чем что-либо ещё в фазе
  продолжится.
- **P4.3** — не стартовала (`⬜`), заблокирована порядком D90 до закрытия P4.2.
- **Ремонт предиката `_lint_write_site_codes_44`** (находки ревью P4.4) — долг, ОБЯЗАН попасть
  в P4.3 Owner packet поимённо.
- **Ремонт гейта `verify_claim_verdicts.py`** (не проверяет символ после `::`) и **исправление
  цитаты H06** — долг, ОБЯЗАН попасть в P4.3 packet поимённо.
- **FP-1/FP-2/FP-3 и H15/H16** — обязаны попасть в P4.3 Owner packet поимённо с владельцами.
- **G1** — единственный действующий Owner-гейт, принимается ВЛАДЕЛЬЦЕМ после packet'а P4.3.
- **Строка доски P0** остаётся `🟡` при терминальных items — вне фазы P4, не тронута.

**Sources of truth:**

- `phases/P4.md` — `## Phase Status` (P4.2 `🔴 Blocked`), `### P4.2` Completion Notes/Pending
  Work/Known Deviations/Escalation Needed — полная запись причины остановки.
- `plan.md` — §4 Status Board (`P4 1/5, 🔴 Blocked (P4.2)`), §6 Update Log (строка остановки).
- `journal.jsonl` — последняя запись `item_id: "P4.2", result: "blocked"`.
- `research/10-p4-entry-gate-and-composition.md` — основание решений захода (D89–D93).

**Open risks:**

1. **Приёмка формально не выполнена и не будет выполнена этим планом** (D88/D89) — не меняется
   этой остановкой.
2. **P4.2 закрыт кодом, не процессом** — риск в том, что подобный разрыв (реализация без
   синхронного bookkeeping) мог повториться и на других items; design-item должен проверить
   P4.1/P4.4/P4.5 на тот же класс риска попутно (не расширяя их запись без основания).
3. **Гейт P4.4 не покрывает P4.1/P4.2/P4.3** (cutoff `2026-07-27` в будущем относительно даты
   закрытия `2026-07-26`, D91) — печать кодов границ остаётся ручной дисциплиной, что и привело
   к текущей остановке.
4. Долги без носителя (D92, полный список — предыдущий handoff) не изменились.

**Workarounds / Deferred / Open questions:**

- Посторонний untracked-каталог `.swissknife/` в рабочем дереве — не тронут этим заходом.
- `docs-sync` follow-up (`packages/task/CLAUDE.md`) — долг P3.1, ближайший носитель — P4.3.
- H15/H16 — недостающее доказательство названо поимённо в `hypothesis-verdicts.json`.
