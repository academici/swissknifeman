# HANDOFF — 2026-07-30 — after P1.6

**Next:** `/task:plan-exec 2026.07.29-HARNESS-AGNOSTIC P1.7`

| Параметр | Значение |
|:--|:--|
| Model | Sonnet |
| Thinking | medium — §3 Routing строка P1.7 (`implementation/medium`, `Exec = plan-exec`) |
| Context | continue (/clear) — обычный item-by-item exec |
| Суть | Бухгалтерия ремонта: карта «коммит → item» в `## 6. Update Log`/`handoff.md`, `Last Updated` = дата последней строки Update Log, честная атрибуция WARN, порядок коммитов пре-имиджей в Known Deviations P1.5, три подписи (F4–F10) |

```
/task:plan-exec 2026.07.29-HARNESS-AGNOSTIC P1.7
```

**P1.6 закрыт `🟢 Done` (сессия sonnet/high, `Exec = manual`, точное совпадение §3 Routing).**
Шесть правил, потерянных при сжатии, вернулись в тела фрагментов (`root.cli-routing`,
`root.shared-core`, `root.marketplace`, `root.plan-lifecycle`, `root.decision-verification`,
`root.codex.launch-and-hook-integrity`); `root.codex.bootstrap` сужен по D73 (изъяты два дубля
`root.worktree-safety`/`root.provider-parity`, изъятие подтверждено чтением, не только зелёным
`validate_catalog()`); `instructions` дописан в `harness.command-surface`. `catalog.json`/фикстура
совместимости — `1.1.1` (инвентарь неизменен, `76`); двенадцать проекций перерендерены (`clean`
12/12), lock — 14 записей, 7 pre-image хешей перепроверены. Гейт покрытия (D76): извлекатель
`artifacts/P1.6-extract-literals.py` → фикстура `instruction-literal-coverage-v1.json` (105/105,
провенанс матрицы), `validate_literal_coverage` заведён ТОЛЬКО в `check_instructions` (не в
`validate_catalog`/`plan_instructions` — тестом подтверждено), `[9/9]` краснеет без перенумерации,
9 новых тестов (481 всего, было 472). Бюджет 5322→5495 ток (OK, порог ≤7000 не задет). Два
коммита в требуемом порядке: `d5e01ef7` (канон+рендер), `eb64ea6c` (гейт покрытия).

**Порядок исполнения жёсткий: P1.6 → P1.7 (теперь достижим).** Предмет P1.7 включает хеш
item-коммита P1.6 (`d5e01ef7`) и `Last Updated` по дате последней строки `## 6. Update Log`.

**Known Deviation (process, P1.6) — найден и честно раскрыт дефект собственного ТЗ:**
Implementation Rules P1.6 утверждали, что порядок `--authorize` — «scope × provider» (буквальная
строка `CLAUDE.md,AGENTS.md,packages/skiller/CLAUDE.md,…`), и что формулировка «алфавитный» из
Pending Work (1) P1.5 «неточна». Прогон опроверг это: `apply_instructions` сравнивает
`authorized_target_paths` с порядком `fresh.artifact_plan.actions`, который на практике
АЛФАВИТНЫЙ по `target_path` — то есть P1.5 был прав, а корректирующая формулировка P1.6 сама
оказалась неверной. Исполнено эмпирически подтверждённым алфавитным порядком (Scope/семантика
canonа не затронуты — чисто процессное расхождение «какая строка идёт в CLI-флаг уже
замороженного механизма»). **Не чинится молча**: нужна ещё одна точечная правка формулировки
(кандидат — новый пункт в P1.7 сверх названных F8–F10, либо отдельная D-запись; решение
владельца, не мешает P1.7's текущий Scope).

**Done:** P0 целиком (5/5 терминальны) · P1.1–P1.6 терминальны (3 `🟢` + 3 `🟠`): матрица «правило →
дом» по семи живым руководствам (P1.1); канон догнал реальность — фрагменты + каталог 76 ID
`1.1.1` + аддендум-контракт sealed v1 (P1.2, P1.3); adoption-режим + CLI `harness instructions
<plan|check|adopt|apply|repair>` + модульная точка `--check` (P1.4); двенадцать проекций приняты под
управление, гейт дрейфа `[9/9]` в `packages/harness/scripts/validate.sh`, always-on бюджет
7620 → 5322 ток (P1.5); ремедиация канона — шесть правил, D73, `instructions`, гейт покрытия
105/105, бюджет 5322→5495 ток (P1.6). **Не сдано:** P1.7 (⬜) — фаза не терминальна.

**Карта «item → коммит» (P1; item-коммит | сопутствующие bookkeeping):**
P1.1 `fd5183af` | `340d0846` · P1.2 `e574fdda` | `d1e393af` · P1.3 `b02e48be` | `4ae56350`
(bookkeeping), `5996d92d` (дозапись журнала), `b191a19c` (Known Deviations) · P1.4 `1e0262a4` |
`d5482b37` · P1.5 `c3b3a8a3` (принятие) + `4647ad4b` (гейт) | `d052698f` · P1.6 `d5e01ef7`
(канон+рендер) + `eb64ea6c` (гейт покрытия) | bookkeeping-коммит этого закрытия (следующий в
истории после этой перезаписи `handoff.md`). Фаза закрыта коммитом `81886a14` (устарело —
реопенена D75). Перенос ВСЕХ этих хешей в строки `## 6. Update Log` дословно и полнота карты —
предмет P1.7 (находка F4: прежняя редакция раздела теряла три хеша и путала bookkeeping с item).

**Известные отклонения (агрегат по items — полный текст в `phases/P1.md`):**
- P1.2 — process: `provenance` фикстуры совместимости НЕ дополнен полями миграции (существующий
  тест держит точный 4-ключевой словарь; ограничено `fixture_version` → `1.0.1`). Долг открыт.
- P1.3 — process: item-коммит несёт дифф вне `Files` (тест-литерал 67 → 76, регенерированная
  `provider-instructions.md`) — структурное следствие роста каталога; плюс порядок коммитов.
- P1.5 — material: `bash packages/skiller/scripts/validate.sh` красный (предсуществующая P0.5-
  краснота, починка вне `Files`); process: `mapping.json` + pre-image'ы в carve-out `artifacts/`;
  process: `apply` перезапущен после `INSTRUCTION_WRITE_FORBIDDEN` (no-write, дерево не тронуто).
  **Дополняется P1.7 (F7):** материал откатa (`artifacts/P1.5-preimages/`) впервые закоммичен в
  `d052698f`, а lock со ссылками на него — предыдущим `c3b3a8a3`, то есть откат по контракту с
  дерева `c3b3a8a3` был невозможен.
- P1.6 — process: **`--authorize` порядок из собственного ТЗ item'а не рабочий** (см. выше) —
  исполнено верным алфавитным порядком; Scope/семантика не затронуты.

**Lint:** `python3 packages/task/scripts/plan-lint.py plans/2026.07.29-HARNESS-AGNOSTIC` — **0 ERROR,
2 WARN**. Оба WARN предсуществуют P1.6 (не рождены его диффом): `phases/P0.md:42` (предсуществующий
с P0) и `phases/P1.md:73` (рождён реопеном D75, до начала P1.6 — унаследован, не новый). ERROR-гейт
**K = 0**. Честная атрибуция обоих WARN и база сравнения для P1.7 — предмет P1.7 (F6).

**Sources of truth:** `plan.md` (§3 Routing, §5 **D1–D79**, §7 Contracts) · `phases/P0.md` (закрыта) ·
`phases/P1.md` (**🟡** — items P1.1–P1.6 терминальны, P1.7 ⬜, блок `## Audit P1 — 2026-07-30`) ·
`research/10-p1-remediation-canon-and-coverage.md` (грунт ремедиации — прогон покрытия, целевые
формулировки, форма гейта, F1–F10) · `research/05-instruction-canon-routing.md` (матрица — **read-only
вход**, 121 строка/105 литералов, sha256 `b2df0bce…5f219`) ·
`research/04-instruction-mechanism-inventory.md` · `brief/01-refinements.md` Р7/Р8 ·
`artifacts/P1.5-mapping.json` + `artifacts/P1.5-preimages/` (держатся до архивации плана) ·
`artifacts/P1.6-extract-literals.py` (генератор фикстуры покрытия, идемпотентен) ·
`packages/harness/tests/fixtures_data/instruction-literal-coverage-v1.json` (105 литералов,
провенанс) · `roadmap.md` (v0.9.0, 31 item) · `root/contracts/provider-parity-definition.md`
(sealed v1) · `root/contracts/instruction-canon-addendum-v1.md` (sealed v1) · `journal.jsonl` ·
`plans/archive/2026.07.18-FOREMAN/`.

**Remaining:** P1.7 (закрыть фазу заново) → P2 (5) → P3 (6) → P4 (5) → P5 (3). Итого
20/31 items ещё не исполнено.

**Open risks:**
- **Гейт покрытия литералов заведён в P1.6 и обязан остаться единственным носителем проверки
  ПОКРЫТИЯ.** Любая будущая правка канона обязана держать его зелёным; фикстура покрытия
  генерируемая — правка руками запрещена (`root.generated-artifacts`), только повторный прогон
  `artifacts/P1.6-extract-literals.py`.
- **Найден и раскрыт дефект собственного ТЗ P1.6** (см. Known Deviation выше): формулировка
  «`--authorize` порядок — scope × provider, не алфавитный» неверна; корректная (алфавитная,
  как P1.5 изначально и утверждал) требует отдельной точечной правки текста — не блокирует P1.7,
  но должна быть учтена, если P1.7's подписи когда-либо коснутся P1.5/P1.6 Implementation Rules
  (сейчас Scope P1.7 такой правки не включает — решение владельца, если нужно расширять).
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
