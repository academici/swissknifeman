# HANDOFF — 2026-07-30 — after P2.6

**Next:** `/task:plan-exec 2026.07.29-HARNESS-AGNOSTIC P2.7`

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | medium — §3 Routing строка P2.7 (`implementation/medium`, `Exec = plan-exec`) |
| Context | continue (/clear) — ручной item |
| Суть | Второй item блока follow-up: docs-sync поверхности `harness instructions`/adoption-режима/механизма канона — раздел в `packages/harness/docs/index.md`, страница `reference/instruction-canon.md`, регистрация в двух сайдбарах, два корневых перекрёстка |

```
/task:plan-exec 2026.07.29-HARNESS-AGNOSTIC P2.7
```

**Что сделано этим заходом (exec, `plan-run` под сессией implementation/high).** P2.6 закрыт
`🟢`: провенанс генерируемой фикстуры покрытия литералов сужен до РОВНО извлекаемой §2 матрицы
(общий хелпер `literal_coverage_section` в `instructions.py`, генератор его импортирует вместо
собственной копии правила) и внутрь существующей `validate_literal_coverage` заведён гейт
равенства «записанный хеш == фактический хеш §2» на существующем коде
`INSTRUCTION_PROVENANCE_INVALID` — оба средства из D81, закрывающие разные половины находки A1
(`phases/P1.md` § `Audit P1 — 2026-07-30 (заход 2)`). Два коммита в требуемом порядке
(`317622c0` сужение+перегенерация, `23c1090c` гейт+тесты); четыре новых теста доказывают
сужение (негатив на подмену хеша, негатив на недоступный источник, негатив на неизвестный
`source_hash_scope`, позитив «правка вне §2 не краснит») — детали см. `phases/P2.md` P2.6
Completion Notes.

**Session:** Sonnet 5/high (implementation/high, `Exec = manual`, D39/D47 — совпадает с §3
Routing, перебора/недобора нет).

**Done:** P0 целиком (5/5 терминальны) · P1 целиком (7/7 терминальны: P1.1/P1.4/P1.6/P1.7 `🟢`,
P1.2/P1.3/P1.5 `🟠`) — матрица «правило → дом», канон 76 ID `1.1.1` + аддендум sealed v1, CLI
`harness instructions` + adoption, двенадцать управляемых проекций, гейт дрейфа `[9/9]`, гейт
покрытия 105/105, бюджет 7620 → 5322 → 5495 ток, карта «коммит → item» · аудит фазы P1 пройден
дважды (заход 1 RED закрыт ремедиацией P1.6/P1.7, заход 2 ATTENTION — блоком follow-up) ·
**блок follow-up P2 — P2.6 `🟢`**: непротухающий провенанс генерируемой фикстуры покрытия
(находка A1 закрыта).

**Карта «item → коммит» (P1–P2; item-коммит | сопутствующие bookkeeping):**
P1.1 `fd5183af` | `340d0846` · P1.2 `e574fdda` | `d1e393af` · P1.3 `b02e48be` | `4ae56350`
(bookkeeping), `5996d92d` (дозапись журнала), `b191a19c` (Known Deviations) · P1.4 `1e0262a4` |
`d5482b37` · P1.5 `c3b3a8a3` (принятие) + `4647ad4b` (гейт) | `d052698f` · P1.6 `d5e01ef7`
(канон+рендер) + `eb64ea6c` (гейт покрытия) | `4416322e` (bookkeeping) · P1.7 `003180bf` (карта
хешей + три подписи) | `a8abbf9e` (bookkeeping), `7d4f12b7` (закрытие фазы) · **P2.6 `317622c0`
(сужение+перегенерация) + `23c1090c` (гейт равенства, item-коммит)**.

**Remaining:** блок follow-up P2.7 → P2.8 → P2.9 → паритет P2.1–P2.5 → P3 (6) → P4 (5) →
P5 (3). Итого **22 из 35** items плана ещё не исполнено.

**Sources of truth:** `plan.md` (§3 Routing — девять строк фазы P2, §5 D1–D85, §6 Update Log с
картой хешей, §7 Contracts, §4 Status Board — P1 `7/7 🟠`, P2 `1/9 🟡`) · `phases/P1.md` (закрыта
`🟠`, два блока аудита: `## Audit P1 — 2026-07-30` RED и `## Audit P1 — 2026-07-30 (заход 2)`
ATTENTION) · `phases/P2.md` (Phase Context § блок follow-up, P2.6 Completion Notes) ·
`research/11-p2-followup-audit-p1-round2.md` (грунт блока: замеры провенанса, исправленные
предикаты, дома долгов) · `research/10-p1-remediation-canon-and-coverage.md` ·
`research/05-instruction-canon-routing.md` (матрица, read-only вход гейта покрытия и теперь
гейта провенанса) · `brief/01-refinements.md` Р9/Р10 ·
`artifacts/P1.6-extract-literals.py` (генератор фикстуры — идемпотентность доказана на
`23c1090c` двумя прогонами подряд, `git diff` пуст) ·
`packages/harness/tests/fixtures_data/instruction-literal-coverage-v1.json` (105 литералов,
`fixture_version` `1.1.2`, провенанс сужен до §2) · `roadmap.md` (v0.10.0, 35 items) ·
`journal.jsonl`.

**Open risks:**
- **`plan-lint` WARN нового рода на `phases/P2.md`** (surfaced P2.6): DoR-чеклист фазы цитирует
  синтаксис маркера уточнения дословно в двух пунктах (design content, вне `Files` любого item'а
  блока follow-up) — как только статус фазы P2 покинул `⬜ Not started` (неизбежно с закрытием
  ЛЮБОГО item'а фазы), `plan-lint` читает цитату как открытый маркер. WARN, не ERROR — гейт `K=0`
  закрытия не задет; правка кандидат для P2.9 или ближайшего design-захода.
- **Формулировка порядка `--authorize` в ТЗ закрытого P1.6 неверна и НЕ правится** (протокол): верна
  АЛФАВИТНАЯ по `target_path` (P1.5 Pending Work 1), авторитет — **D84**; дом механизма — спека
  `roadmap/`, заводит P2.8. Копирование порядка из ТЗ P1.6 даст `INSTRUCTION_WRITE_FORBIDDEN`.
- **Посторонний незакоммиченный дифф в дереве не убран и не тронут:** `roadmap/README.md` (M,
  строка спеки launch-block'а) + untracked `roadmap/2026.07.29-launch-block-command-row.md`. P2.8
  правит ЭТОТ ЖЕ файл и обязан сохранить чужую строку незакоммиченной (`git stash` → коммит → pop).
- **Слепота `_validate_conflicts` к дублю СМЫСЛА** (`obligations` с самореферентным `object`,
  `instructions.py:1005-1022`): зелёный `validate_catalog()` НЕ доказывает отсутствия дубля
  common-правила внутри provider-extension. Дом правки — `roadmap/`, вне скоупа (Р8/Р10); спека
  ЗАХОДОМ НЕ ЗАВЕДЕНА — долг остаётся в этом списке.
- **Фикстурный `provenance` СОВМЕСТИМОСТИ не отражает миграцию P1.2** — нужен отдельный item со
  строкой `packages/harness/tests/test_instruction_compatibility.py` в `Files`; заходом не заведён
  (Р10), долг остаётся открытым.
- **Двенадцать корневых и пакетных руководств УПРАВЛЯЕМЫЕ**: ручная правка блоков между маркерами
  запрещена навсегда — только фрагменты + повторный прогон, иначе `managed-drift` на `[9/9]`.
- **Гейт `[9/9]` живёт только в `packages/harness/scripts/validate.sh`** — `analyst`/`task` в CI не
  покрыты вовсе (OQ-9); локальный прогон ≠ CI (R2).
- **`packages/skiller/scripts/validate.sh` на дереве КРАСНЫЙ** (долг P0.5, material-отклонение
  P1.5); `scripts/test-provider-docs.py` и `scripts/public-hygiene.py` — предсуществующе красные.
- **`vitepress build` в дереве не прогоняется** — `node_modules` отсутствуют; доки P2.7 проверяются
  машинными проверками ссылок и регистрации, установка зависимостей вне скоупа item'а.
- **Аудит design-фазы исчерпан** — дефект в ТЗ P2.1–P2.5 и P3–P5 всплывёт на исполнении.
- **Маршруты мягче:** items с `effort high` идут через `plan-run` (D47) — строка
  `Session: <model>/<effort>` в отчёте и в Update Log обязательна.
- Общий state `~/.swissknifeman`/`~/.maind` изоляцией не покрыт — риск принят владельцем (D4).
- **P5.2 — единственная необратимая внутрь граница плана** (R1).
- Портируемость (`plan-portability-v1.md`): host-специфичные пути запрещены в
  `Inputs`/`Required Reads`/`Validation` — действует на P5.1–P5.3.

**Workarounds/Deferred/Open questions:**
- workarounds: правка общего `plans/verify-citations-known-exceptions.json` (D54) — дом
  design-коммит, не `Files` какого-либо item'а.
- deferred: правка `_validate_conflicts`/схемы `obligations` (кандидат `roadmap/`, Р8; спека не
  заведена) · починка order-sensitivity `apply_instructions` (дом заведёт P2.8, реализация
  отложена — D84) · фикстурный `provenance` P1.2 · изоляция общего state (OQ-5) · тонкая обвязка
  супервизора (P4.1, D38) · round-trip гейт живым прогоном Codex · структурный перебор листинга
  Codex (OQ-7) · общий differ канона ролей (OQ-8) · машинные гейты PROMOTE-CANDIDATE («Validation
  прогнана» — четвёртый прецедент в P1, «design-заход в истории» D69) · `skiller registry` не
  прогнан (P0.5) · раскатка на потребителей (D45) · push/PR/тег и публикация доков (D41) ·
  расширение CI на `analyst`/`task` (OQ-9) · русский канон скиллов в `.gitignore` (Р5) · раскатка
  adoption-режима на онбордженные проекты · удаление pre-image'ов P1.5 (держатся до архивации
  плана). **Снято из deferred:** docs-sync `harness instructions`/adoption/канона — получил дом,
  item P2.7 (D85).
- open_questions: OQ-3 две capability `unsupported` у обоих провайдеров (P2.1) · OQ-6 дом логики
  Codex-обработчиков (P2.1) · OQ-7 структурный перебор бюджета обнаружения (P3.4) · OQ-8 дрейф
  канона ролей (Deferred) · OQ-9 CI не покрывает `analyst`/`task` (Deferred). OQ-2 закрыта D71,
  OQ-1 закрыта D31, OQ-4 закрыта D27. Блок follow-up новых открытых вопросов не добавил (все
  развилки закрыты D80–D85 по режиму Р6/D14).
