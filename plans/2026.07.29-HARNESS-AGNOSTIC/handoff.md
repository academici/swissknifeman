# HANDOFF — 2026-07-30 — after P1.7

**Next:** `/task:plan-close 2026.07.29-HARNESS-AGNOSTIC P1`

| Параметр | Значение |
|:--|:--|
| Model | Sonnet |
| Thinking | low — реконсиляция терминальной фазы по git-фактам, без принятия решений |
| Context | NEW SESSION — шаг-не-item |
| Суть | Все семь items P1.1–P1.7 терминальны — закрыть фазу P1 повторно (реконсиляция статусов, `## Phase Status`/`## 4. Phase Index & Status Board`, новый `## Phase Handoff`, снятие пометки `> УСТАРЕЛ`), чтобы стал достижим P2 |

```
/task:plan-close 2026.07.29-HARNESS-AGNOSTIC P1
```

**P1.7 закрыт `🟢 Done` (сессия sonnet/medium, `Exec = plan-exec`, точное совпадение §3 Routing).**
Карта «коммит → item» восстановлена в `## 6. Update Log` — все шесть строк, закрывающих P1.1–P1.6,
несут item-коммиты (`fd5183af` · `e574fdda` · `b02e48be` · `1e0262a4` · `c3b3a8a3`+`4647ad4b` ·
`d5e01ef7`+`eb64ea6c`), проверено `git show --stat --oneline -s` на каждом. `Last Updated` уже
совпадала с датой последней строки Update Log на старте item'а — правки не потребовалось (F5).
Атрибуция WARN честна: `plan-lint --baseline 4bdc4a5e` даёт 1 WARN новым от рабочего дерева
(`phases/P1.md:73`, рождён DoR-блоком реопена D75, а не P1.6/P1.7); ERROR-гейт `K = 0` (F6).
Known Deviations (2) P1.5 дополнены порядком коммитов пре-имиджей: материал отката
(`artifacts/P1.5-preimages/`) впервые закоммичен `d052698f`, а lock со ссылками на него — предыдущим
`c3b3a8a3` — откат по контракту с того дерева был невозможен (F7). Три ложные подписи приведены к
фактам: 135 строк §2 `research/05` = 121 строка данных + 14 разметки, число строк матрицы — 121
(F8); «семь codex-фрагментов» = 4 `codex.md` + 3 `claude-code.md` (F9); «шесть `<pkg>.identity`» =
четыре записи (`skiller`/`harness`/`maind`/`task`), у `analyst` — `analyst.identity-human-gate`
(F10, D79). Item-коммит `003180bf`; validate.sh — `validate: OK`.

**Фаза P1 теперь терминальна по items (все семь 🟢/🟠), но статус фазы и `## Phase Handoff`
остаются устаревшими (D75) до штатного `plan-close`.** Не закрывать P1.7-исполнением напрямую —
это отдельный шаг-не-item со своей ролью реконсиляции (не принимает новых решений, сверяет статусы
с git-фактами).

**Done:** P0 целиком (5/5 терминальны) · P1.1–P1.7 терминальны (4 `🟢` + 3 `🟠`): матрица «правило →
дом» по семи живым руководствам (P1.1); канон догнал реальность — фрагменты + каталог 76 ID `1.1.1`
+ аддендум-контракт sealed v1 (P1.2, P1.3); adoption-режим + CLI `harness instructions
<plan|check|adopt|apply|repair>` + модульная точка `--check` (P1.4); двенадцать проекций приняты под
управление, гейт дрейфа `[9/9]` в `packages/harness/scripts/validate.sh`, always-on бюджет
7620 → 5322 ток (P1.5); ремедиация канона — шесть правил, D73, `instructions`, гейт покрытия
105/105, бюджет 5322→5495 ток (P1.6); бухгалтерия ремонта — карта хешей, честная атрибуция WARN,
три подписи (P1.7). **Не сдано:** реконсиляция фазы P1 штатным `plan-close`.

**Карта «item → коммит» (P1; item-коммит | сопутствующие bookkeeping):**
P1.1 `fd5183af` | `340d0846` · P1.2 `e574fdda` | `d1e393af` · P1.3 `b02e48be` | `4ae56350`
(bookkeeping), `5996d92d` (дозапись журнала), `b191a19c` (Known Deviations) · P1.4 `1e0262a4` |
`d5482b37` · P1.5 `c3b3a8a3` (принятие) + `4647ad4b` (гейт) | `d052698f` · P1.6 `d5e01ef7`
(канон+рендер) + `eb64ea6c` (гейт покрытия) | `4416322e` (bookkeeping) · P1.7 `003180bf` (карта
хешей + три подписи) | bookkeeping-коммит этого закрытия (следующий в истории после этой
перезаписи `handoff.md`). Фаза закрыта коммитом `81886a14` (устарело — реопенена D75, повторное
закрытие — задача следующего шага). Карта дословно перенесена в `## 6. Update Log` — предмет
P1.7 исполнен (находка F4 закрыта).

**Известные отклонения (агрегат по items — полный текст в `phases/P1.md`):**
- P1.2 — process: `provenance` фикстуры совместимости НЕ дополнен полями миграции (существующий
  тест держит точный 4-ключевой словарь; ограничено `fixture_version` → `1.0.1`). Долг открыт.
- P1.3 — process: item-коммит несёт дифф вне `Files` (тест-литерал 67 → 76, регенерированная
  `provider-instructions.md`) — структурное следствие роста каталога; плюс порядок коммитов.
- P1.5 — material: `bash packages/skiller/scripts/validate.sh` красный (предсуществующая P0.5-
  краснота, починка вне `Files`); process: `mapping.json` + pre-image'ы в carve-out `artifacts/`;
  process: `apply` перезапущен после `INSTRUCTION_WRITE_FORBIDDEN` (no-write, дерево не тронуто);
  порядок коммитов пре-имиджей теперь дописан в Known Deviations (2) — откат с дерева `c3b3a8a3`
  был невозможен (P1.7, F7).
- P1.6 — process: `--authorize` порядок из собственного ТЗ item'а не рабочий — исполнено верным
  алфавитным порядком; Scope/семантика не затронуты. Точечная правка формулировки (кандидат — новый
  D# или follow-up item) остаётся открытым риском ниже — P1.7 её не касался (вне Scope).

**Lint:** `python3 packages/task/scripts/plan-lint.py plans/2026.07.29-HARNESS-AGNOSTIC` — **0 ERROR,
2 WARN** (на дереве item-коммита `003180bf`). Атрибуция (`--baseline 4bdc4a5e`, дерево до фазы P1):
**1 новый от рабочего дерева** — `phases/P1.md:73`, ложный `[NEEDS CLARIFICATION]`-детект внутри
DoR-блока реопена D75 (текст «Все `[NEEDS CLARIFICATION]` сняты»), не самим P1.6/P1.7;
`phases/P0.md:42` предсуществует всему плану. ERROR-гейт **K = 0**.

**Sources of truth:** `plan.md` (§3 Routing, §5 **D1–D79**, §6 Update Log с картой хешей, §7
Contracts) · `phases/P0.md` (закрыта) · `phases/P1.md` (**🟡** — все items терминальны, фаза ждёт
`plan-close`, блок `## Audit P1 — 2026-07-30`) · `research/10-p1-remediation-canon-and-coverage.md`
(грунт ремедиации — прогон покрытия, целевые формулировки, форма гейта, F1–F10) ·
`research/05-instruction-canon-routing.md` (матрица — read-only вход, 121 строка/105 литералов,
снятие 2 §5 уточнено D79) · `research/04-instruction-mechanism-inventory.md` ·
`brief/01-refinements.md` Р7/Р8 · `artifacts/P1.5-mapping.json` + `artifacts/P1.5-preimages/`
(держатся до архивации плана) · `artifacts/P1.6-extract-literals.py` (генератор фикстуры покрытия,
идемпотентен) · `packages/harness/tests/fixtures_data/instruction-literal-coverage-v1.json` (105
литералов, провенанс) · `roadmap.md` (v0.9.0, 31 item) ·
`root/contracts/provider-parity-definition.md` (sealed v1) ·
`root/contracts/instruction-canon-addendum-v1.md` (sealed v1) · `journal.jsonl` ·
`plans/archive/2026.07.18-FOREMAN/`.

**Remaining:** реконсиляция P1 (`plan-close`) → P2 (5) → P3 (6) → P4 (5) → P5 (3). Итого
19/31 items ещё не исполнено (реконсиляция фазы — не item).

**Open risks:**
- **Гейт покрытия литералов заведён в P1.6 и обязан остаться единственным носителем проверки
  ПОКРЫТИЯ.** Любая будущая правка канона обязана держать его зелёным; фикстура покрытия
  генерируемая — правка руками запрещена (`root.generated-artifacts`), только повторный прогон
  `artifacts/P1.6-extract-literals.py`.
- **Дефект собственного ТЗ P1.6, найден и раскрыт, но не починен (вне Scope P1.7):** формулировка
  «`--authorize` порядок — scope × provider, не алфавитный» неверна; корректная (алфавитная, как
  P1.5 изначально утверждал) требует отдельной точечной правки текста — кандидат: новая D-запись
  или follow-up item; решение владельца.
- **Слепота `_validate_conflicts` к дублю СМЫСЛА** (`obligations` с самореферентным `object`,
  `instructions.py:1005-1022`): зелёный `validate_catalog()` НЕ доказывает отсутствия дубля
  common-правила внутри provider-extension. Дом правки — `roadmap/`, вне этой фазы (Р8).
- **Двенадцать корневых и пакетных руководств УПРАВЛЯЕМЫЕ**: ручная правка блоков между маркерами
  запрещена навсегда — только фрагменты + повторный прогон, иначе `managed-drift` на `[9/9]`.
- **Гейт `[9/9]` живёт только в `packages/harness/scripts/validate.sh`** — `analyst`/`task` в CI не
  покрыты вовсе (OQ-9); локальный прогон ≠ CI (R2).
- **Фикстурный `provenance` не отражает миграцию P1.2** — нужен отдельный item со строкой
  `packages/harness/tests/test_instruction_compatibility.py` в `Files`.
- **`packages/skiller/scripts/validate.sh` на дереве КРАСНЫЙ** (долг P0.5, material-отклонение
  P1.5); `scripts/test-provider-docs.py` и `scripts/public-hygiene.py` — предсуществующе красные.
- **Посторонний дифф в дереве не убран и не тронут:** `roadmap/README.md` (M) + untracked
  `roadmap/2026.07.29-launch-block-command-row.md` (предсуществует до P0.2, вне `Files` P1).
- **Docs-sync follow-up:** `harness instructions`/adoption-режим/механизм канона не описаны в
  `docs/` — целевое место `packages/harness/docs/` + ссылка из `docs/routing.md`.
- **Аудит design-фазы исчерпан** — дефект в ТЗ P2–P5 всплывёт на исполнении.
- **Маршруты мягче:** items с `effort high` идут через `plan-run` (D47) — строка
  `Session: <model>/<effort>` в отчёте и в Update Log обязательна.
- Общий state `~/.swissknifeman`/`~/.maind` изоляцией не покрыт — риск принят владельцем (D4).
- **P5.2 — единственная необратимая внутрь граница плана** (R1).
- Портируемость (`plan-portability-v1.md`): host-специфичные пути запрещены в
  `Inputs`/`Required Reads`/`Validation` — действует на P5.1–P5.3.

**Workarounds/Deferred/Open questions:**
- workarounds: правка общего `plans/verify-citations-known-exceptions.json` (D54) — дом
  design-коммит, не `Files` какого-либо item'а.
- deferred: правка `_validate_conflicts`/схемы `obligations` (кандидат `roadmap/`, Р8) ·
  порядок-чувствительный `--authorize` у `apply_instructions` (формулировка нуждается в правке,
  см. Open risks) · фикстурный `provenance` P1.2 · изоляция общего state (OQ-5) · тонкая обвязка
  супервизора (P4.1, D38) · round-trip гейт живым прогоном Codex · структурный перебор листинга
  Codex (OQ-7) · общий differ канона ролей (OQ-8) · машинные гейты PROMOTE-CANDIDATE («Validation
  прогнана», «design-заход в истории» D69) · `skiller registry` не прогнан (P0.5) · раскатка на
  потребителей (D45) · push/PR/тег и публикация доков (D41) · расширение CI на `analyst`/`task`
  (OQ-9) · русский канон скиллов в `.gitignore` (Р5) · раскатка adoption-режима на онбордженные
  проекты · удаление pre-image'ов P1.5 (держатся до архивации плана) · docs-sync `harness
  instructions`/adoption/канон.
- open_questions: OQ-3 две capability `unsupported` у обоих провайдеров (P2.1) · OQ-6 дом логики
  Codex-обработчиков (P2.1) · OQ-7 структурный перебор бюджета обнаружения (P3.4) · OQ-8 дрейф
  канона ролей (Deferred) · OQ-9 CI не покрывает `analyst`/`task` (Deferred). OQ-2 закрыта D71,
  OQ-1 закрыта D31, OQ-4 закрыта D27. Реопен P1 новых открытых вопросов не добавил (развилки
  закрыты D75–D79 по режиму Р6).
