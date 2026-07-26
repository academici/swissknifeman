# HANDOFF — 2026-07-26 — after P3.8

**Next:** ЗАПУСК ВРУЧНУЮ: frontier/high (Exec = manual, `plan-exec` пинит sonnet/medium ниже предписанного и обязан отклонить этот item по гейту п. 2)

| Параметр | Значение |
|:--|:--|
| Model class | `frontier` |
| Effort | `high` |
| Capabilities | `command.subagents` |
| Plan context | `same-session — item` |
| Model | `opus`/`fable` (Claude) или `gpt-5.6-sol` (Codex) — по §3 Routing через checked mapping |
| Thinking | `high` — открытое проектирование карты наблюдения + доказательство свойства МНОЖЕСТВА (D51) |
| Context | `NEW SESSION — Workflow-оркестрован` |
| Суть | Харнес живого диспатча `run_live_bank.py` + декларативная карта `event-mapping-v1.json`, измеряющие детерминированно, у скольких из 31 кейса события вообще наблюдаемы из машинных артефактов; отчёт `findings/P3.9-mappability.md`. |

```
/model opus
/effort high
/task:plan-run 2026.07.24-AGENT-RELIABILITY P3.9
```

**Done:**

- **P3.8 закрыт 🟠 Done with deviations** (item-commit `9074edb8`) — честное F1 поверх
  доставленного P3.1 trace-seam'а: `case_trace_record_missing` больше не грепает литерал
  `trace_emitted` как символ пакета (он — имя события банка), а драйвит
  `analyst.trace.build_trace_record` над реальной committed trace-записью
  `artifacts/P3.4/canary-results.json::cases[0].traces[0]`.
  - **Измерено:** ложный провал снят — A1 (`event_present trace_emitted`) `false`→`true`.
    A2 (`required_fields_complete`) остаётся честно `false`: сама committed trace-запись
    несёт `completeness=0.667`, `missing=[contract_ref, finding_refs]` — все восемь
    committed записей P3.4 идентичны по этому полю (P3.4-харнес их не заполняет). F1
    (`critical_requirement_retention`) остаётся `0.96 not-met`, но по НОВОЙ, честной причине
    — не «пробел seam'а», а «пробел инструментовки живого диспатча».
  - Детерминизм подтверждён (два прогона в разные scratch-каталоги → идентичный sha256).
    Обе стороны банка переиграны (`run_bank.py verify`/`candidate`), провенанс sha256
    до/после всех трёх артефактов — `findings/P3.8-f1-recompute.md` § 3.
  - Известное отклонение (см. Known Deviations P3.8): остаток F1 передан как Pending Work
    — новый носитель (P3.9/P3.10 или отдельный item) должен научить P3.4-харнес заполнять
    `contract_ref`/`finding_refs`, если этот остаток нужно закрыть.
- **Items P3.1–P3.7 НЕ реопенены** — продукты пересчитаны P3.5, реконсилированы P3.6,
  P3.7 верифицирован read-only `--check`.

**Remaining:**

- **P3.9** ⬜ харнес живого диспатча + ИЗМЕРЕННОЕ множество наблюдаемых кейсов (`N/31`) —
  следующий шаг, `Exec = manual`, `frontier/high`.
- **P3.10** ⬜ парный живой layer-2 прогон на `PRE_PLAN_SHA 7479972f` → F6/F8/F9/F10.
- **P3.11** ⬜ терминальный аудит фазы, **заход 2/2** — последний из бюджета.
- **P4** ⬜ — **не стартует до GREEN**.

**Sources of truth:**

- `phases/P3.md` — `## Phase Status` (11 items), P3.8 Completion Notes/Known
  Deviations, ТЗ P3.9–P3.11, блок `## Audit P3 — 2026-07-26` (исторический отчёт
  захода 1, не правится).
- `findings/P3.8-f1-recompute.md` — полный отчёт этого захода (провенанс sha256,
  сравнение A1/A2 до/после, обзор всех восьми committed trace-записей).
- `findings/P3.5-terminal-audit.md` — источник значений F1–F8 захода 1.
- `research/09-p3-remediation-composition.md` § 5 — граница ремонта F1 (проба, не кейс).
- `plan.md` — §0 Meta (v1.19.3), §3 Routing, §4 Status Board (`3/11`), D80–D87, §6.

**Open risks:**

- **`contract_ref`/`finding_refs` не заполняются P3.4-харнесом** ни в одной из восьми
  committed trace-записей (новая находка P3.8) — если этот остаток нужно закрыть до GREEN,
  носитель не назван; кандидат для P3.9 (харнес живого диспатча) либо отдельного item'а.
- **GREEN может оказаться недостижим без правки контракта приёмки.** Если измеренное P3.9
  множество наблюдаемых кейсов окажется меньше `31/31`, floors F6/F8/F9/F10 получат
  `scope: declared-subset N/31` и не смогут быть объявлены `met`: D#-предложение формулирует
  P3.10, решение принимает P3.11. Тихое повышение `unknown` до `met` запрещено (D30).
- **Ловушка `event_absent`** (D83): 20 из 88 ассершенов банка — отрицательные и проходят
  тривиально там, где прибор не видит ничего. Ненаблюдаемый кейс исключается ЦЕЛИКОМ.
- **Живая цена P3.10** не экстраполируется с пробы в `/tmp` ($0.02 на haiku): реальный диспатч
  в репозитории с большим `CLAUDE.md`, MCP и хуками дороже на порядки. Бюджет и стоп-правило
  объявлены в ТЗ; превышение — стоп с записью, а не тихое усечение.
- **`verify_result_manifest.py` self-hash re-drift**: если P3.9/P3.10 (или любой будущий
  item) снова правит этот скрипт, `--check`/дефолтный режим против манифеста, запечатанного
  ДО той правки, повторно покажет РОВНО `files.verify_result_manifest.py` — это ожидаемо
  (D87), не новая находка, пока не появится второе расходящееся поле.
- **Остаточный lint вне диффа:** `plan-lint` — 0 ERROR при 1 WARN (строка Update Log P1.4,
  303 символа при пороге 300), открыт с предыдущих handoff'ов.
- **`analyst`/`harness` package-API minor bumps** (`0.1.0`→`0.2.0`, `0.3.0`→`0.4.0`) и
  CLI-подключение `analyst metrics` / `skiller eval` — долги с P3.1/P3.2/P3.3.
- **P0 phase-index row** (`task:plan-close … P0`) — все items P0 терминальны, строка доски
  остаётся `🟡`; открыто с ранних handoff'ов.

**Workarounds / Deferred / Open questions:**

- **Codex-сторона наблюдаемости не пробовалась** в этом заходе: acting provider — Claude
  (D33/D50), Codex-формы остаются recovery-проекциями; паритет провайдеров — предмет
  `provider_capability_matrix` P3.3, не этого захода.
- **Форма `tool_use`/`tool_result` на реальной рабочей задаче не измерялась** — гипотеза,
  которую измеряет P3.9.
- **Дрейф проб банка при `--strict-probes` — не находка**, а задокументированное
  самообнуление layer-1 после появления seam'а P2 (§ Correction procedure).
- **Репетиция отката P3.4 помечена `cross-checked`, а не `recomputed`** — переигровка
  потребовала бы создать worktree, то есть произвести ровно тот остаток, который вменяет F6
  (снятый P3.6).
- **`docs-sync` follow-up** (`packages/task/CLAUDE.md`, описание compiler/enforcement seam) —
  долг P3.1, не тронут.
- **Валидационная self-reference P3.6** (см. Known Deviations item'а) — предложенный фикс
  не сделан, чтобы не расширять правку сверх Scope; кандидат для будущей правки формы
  Validation этого класса items.
