# HANDOFF — 2026-07-26 — after P3.6

**Next:** ЗАПУСК ВРУЧНУЮ: sonnet/high (Exec = manual, `plan-exec` пинит sonnet/medium ниже предписанного и обязан отклонить этот item по гейту п. 2)

| Параметр | Значение |
|:--|:--|
| Model class | `implementation` |
| Effort | `high` |
| Capabilities | `—` |
| Plan context | `same-session — item` |
| Model | `sonnet` (Claude) или `gpt-5.6-sol` (Codex) — по §3 Routing через checked mapping |
| Thinking | `high` |
| Context | `continue (/clear) — ручной item` |
| Суть | `--check`-режим для `verify_result_manifest.py` (F5) — снимает мутацию закоммиченного артефакта read-only проверкой; нужен ДО P3.8 и P3.11. |

```
/model sonnet
/effort high
/task:plan-run 2026.07.24-AGENT-RELIABILITY P3.7
```

**Done:**

- **P3.6 закрыт 🟠 Done with deviations** — реконсиляция записи фазы P3 по шести
  находкам аудита захода 1 (F2/F3/F4/F6/F7/F8), без единой мутации `packages/**`:
  - **F2** — P3.3 `Status` → `🟠 Done with deviations` + Known Deviations, называющая
    недоставленный paired-benchmark half и его носителя (P3.9/P3.10); продукт P3.3
    (адаптер/грейдеры/byte-identical кросс-сверка) НЕ переоткрыт.
  - **F3** — коды `pre_mutation: allow`/`pre_final: allow` (маршрут исполнителя,
    `capture_actual("implementation","high", source="self-attested", model="sonnet")`,
    D75) ретро-записаны в Known Deviations P3.1/P3.2/P3.3/P3.4 с атрибуцией
    «пересчитано P3.5» — история не переписана.
  - **F4** — заявленное вдвое больше факта число диспатчей/трасс P3.4 → факт «8
    headless turns, на `cfd0e4ba`: 4 single-attempt cases (01–04) + 2×2 (05/06)» в двух
    реальных носителях (`phases/P3.md` Completion Notes P3.4, `findings/P3.4-canary.md`);
    `handoff.md` уже был перезаписан целиком до этого числа, третьего носителя де-факто
    не осталось. Число `8` подтверждено `git show cfd0e4ba:…canary-results.json`
    ДО правки текста.
  - **F6** — `git worktree remove /tmp/skm-p3.4-debug.TAcgRY/worktree` выполнен
    успешно (хук не отклонил), `0` регистраций после; Known Deviations P3.4 приведена
    к факту (была «`git worktree list` … clean», стало явное признание находки).
  - **F7** — строка Known Deviations добавлена в P3.1 (журнал append-only, не правится).
  - **F8** — sha256 `canary-results.json` доказано не запинен ни в одном манифесте
    (`grep -r`); host-bound путь `/tmp/skm-agent-reliability-p3.4.kklYE4/…` заменён на
    worktree-относительный `$CANARY_WT/...` в `artifacts/P3.4/canary-results.json`.
  - `## Phase Status` (P3.3, P3.6), `plan.md` §4 (`4/11` → `3/11`, счёт 🟢 упал на
    один из-за F2) и §6 синхронизированы; `plan.md` Version `1.19.0` → `1.19.1`.
  - **Известное отклонение этого item'а:** Validation-команда P3.6 самоссылочна —
    её собственный текст цитирует искомые grep-паттерны, поэтому после фикса совпадает
    ровно одна строка (сама Validation-строка), не остаточная ложная претензия; три
    реальных носителя подтверждены `0`. Детали — `phases/P3.md` P3.6 Known Deviations.
- **Items P3.1–P3.5 НЕ реопенены** (кроме точечных полей `Status`/`Known Deviations`
  P3.1/P3.3, предписанных самим составом ремонта) — продукты пересчитаны P3.5 и зелены.

**Remaining:**

- **P3.7** ⬜ `--check` для `verify_result_manifest.py` (F5) — следующий шаг, `Exec = manual`.
- **P3.8** ⬜ честное F1: регенерация кандидатских транскриптов P2.5 поверх доставленного
  trace-seam'а; правится ПРОБА генератора, не кейс/грейдер (D85).
- **P3.9** ⬜ харнес живого диспатча + ИЗМЕРЕННОЕ множество наблюдаемых кейсов (`N/31`).
- **P3.10** ⬜ парный живой layer-2 прогон на `PRE_PLAN_SHA 7479972f` → F6/F8/F9/F10.
- **P3.11** ⬜ терминальный аудит фазы, **заход 2/2** — последний из бюджета.
- **P4** ⬜ — **не стартует до GREEN**.

**Sources of truth:**

- `phases/P3.md` — `## Phase Status` (11 items), P3.6 Completion Notes/Known Deviations,
  ТЗ P3.7–P3.11, блок `## Audit P3 — 2026-07-26` (исторический отчёт захода 1, не правится).
- `findings/P3.5-terminal-audit.md` — полный отчёт захода 1 (источник значений F2–F8).
- `research/09-p3-remediation-composition.md` — почему ремонт разложен именно так.
- `plan.md` — §0 Meta (v1.19.1), §3 Routing, §4 Status Board (`3/11`), D80–D86, §6.

**Open risks:**

- **GREEN может оказаться недостижим без правки контракта приёмки.** Если измеренное P3.9
  множество наблюдаемых кейсов окажется меньше `31/31`, floors F6/F8/F9/F10 получат
  `scope: declared-subset N/31` и не смогут быть объявлены `met`: D#-предложение формулирует
  P3.10, решение принимает P3.11. Тихое повышение `unknown` до `met` запрещено (D30).
- **Ловушка `event_absent`** (D83): 20 из 88 ассершенов банка — отрицательные и проходят
  тривиально там, где прибор не видит ничего. Ненаблюдаемый кейс исключается ЦЕЛИКОМ.
- **Живая цена P3.10** не экстраполируется с пробы в `/tmp` ($0.02 на haiku): реальный диспатч
  в репозитории с большим `CLAUDE.md`, MCP и хуками дороже на порядки. Бюджет и стоп-правило
  объявлены в ТЗ; превышение — стоп с записью, а не тихое усечение.
- **Оставшиеся находки аудита открыты до закрытия своих носителей**: F1 → P3.8/P3.9/P3.10;
  F5 → P3.7.
- **`verify_result_manifest.py` мутирует закоммиченный артефакт при каждом запуске** — до
  поставки P3.7 отменять `git checkout --` после любого прогона.
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
- **Дрейф 18 проб банка при `--strict-probes` — не находка**, а задокументированное
  самообнуление layer-1 после появления seam'а P2 (§ Correction procedure).
- **Репетиция отката P3.4 помечена `cross-checked`, а не `recomputed`** — переигровка
  потребовала бы создать worktree, то есть произвести ровно тот остаток, который вменяет F6
  (теперь снятый P3.6).
- **`docs-sync` follow-up** (`packages/task/CLAUDE.md`, описание compiler/enforcement seam) —
  долг P3.1, не тронут.
- **Валидационная self-reference P3.6** (см. Known Deviations item'а) — предложенный фикс
  (грепать только целевые секции, не весь файл) не сделан, чтобы не расширять правку сверх
  Scope; кандидат для будущей правки формы Validation этого класса items.
