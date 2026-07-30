# HANDOFF — 2026-07-30 — after P1

**Next:** `/task:plan-audit 2026.07.29-HARNESS-AGNOSTIC P1`

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | xhigh — фаза закрыта с тремя `🟠`-эскалациями, аудит перед P2 |
| Context | NEW SESSION — шаг-не-item |
| Суть | Аудит фазы P1 (три Known Deviations, follow-up docs-sync) перед стартом P2 |

```
/task:plan-audit 2026.07.29-HARNESS-AGNOSTIC P1
```

**PHASE-CLOSED: P1.** Реконсиляция `plan-close <ID> P1` подтвердила: все пять items терминальны
(2 `🟢` + 3 `🟠`), git-факты сходятся с заявленным (item-коммиты `e574fdda`/`4ae56350`+`5996d92d`/
`c3b3a8a3`/`4647ad4b`), правок статусов не потребовалось. `## Phase Status` (`phases/P1.md`) и
`## 4. Phase Index & Status Board` (`plan.md`) сведены: `P1 | Паритет корневых инструкций | 2/5 |
🟠 Done with deviations`. `## Phase Handoff` в `phases/P1.md` заполнено.

**Done:** P1 целиком (5/5 items терминальны) — матрица «правило → дом» по семи живым руководствам (P1.1); канон догнал
реальность — 8/18 фрагментов + аддитивный каталог 76 ID / 1.1.0 + аддендум-контракт (P1.2, P1.3);
adoption-режим + CLI `harness instructions <plan|check|adopt|apply|repair>` (P1.4); живая транзакция
принята — двенадцать корневых/пакетных руководств управляемы, гейт дрейфа `[9/9]` в
`packages/harness/scripts/validate.sh`, always-on бюджет 7620→5322 ток (P1.5).

**Known Deviations (агрегат, механически из items — см. Phase Handoff `phases/P1.md` для полного
текста):**
- P1.2 — process: фикстурный `provenance` НЕ дополнен полями миграции (существующий тест держит
  точный 4-ключевой словарь; ограничена `fixture_version`→`1.0.1`).
- P1.3 — process: item-коммит несёт дифф вне `Files` (тест-литерал 67→76, регенерированная
  `provider-instructions.md`) — структурное следствие роста каталога; плюс порядок коммитов.
- P1.5 — material: `bash packages/skiller/scripts/validate.sh` красный (предсуществующая P0.5-
  краснота, вне `Files` item'а); process: `mapping.json`+pre-image'ы в carve-out `artifacts/`;
  process: `apply` перезапущен после `INSTRUCTION_WRITE_FORBIDDEN` (no-write, дерево не тронуто).

**Docs-sync (шаг 3, обязательный):** **follow-up** — требуется, но крупнее фазы. `harness
instructions` CLI, adoption-режим и механизм канона (`instructions.py`, гейт дрейфа) нигде в
`docs/` не описаны (`grep -r` по `docs/` и `packages/harness/docs/` — ноль релевантных
совпадений). Целевое место — `packages/harness/docs/` + перекрёстная ссылка из корневого
`docs/routing.md`/`docs/control-surface.md`. Записано как открытый риск ниже, не тихая отсрочка.

**Lint:** `plan-lint` — предсуществующие 2 WARN (ложное срабатывание `plan_lint.py:1941-1948` на
`phases/P0.md:42` и `phases/P1.md:51,138`), 0 ERROR — новых от закрытия фазы: **K = 0**.
**Цитаты:** `verify-citations.py --strict` — baseline перечня чист (P11.5); находок вне
предсуществующего перечня, новых от закрытия фазы, **K = 0**.

**Sources of truth:** `plans/2026.07.29-HARNESS-AGNOSTIC/plan.md` (§3 Routing, §5 D1–D74,
§7 Contracts) · `phases/P0.md` (закрыта) · `phases/P1.md` (закрыта — Phase Status + Phase Handoff) ·
`research/05-instruction-canon-routing.md` · `research/04-instruction-mechanism-inventory.md` ·
`artifacts/P1.5-mapping.json` + `artifacts/P1.5-preimages/` (сохраняются до архивации плана) ·
`roadmap.md` (батч B1 закрыт) · `root/contracts/provider-parity-definition.md` (sealed v1) ·
`root/contracts/instruction-canon-addendum-v1.md` (sealed v1) · `journal.jsonl` ·
`plans/archive/2026.07.18-FOREMAN/` · `docs/reference.md`, `docs/rejected-optimizations.md`.

**Remaining:** P2 (5) → P3 (6) → P4 (5) → P5 (3). Итого 19/29 items ещё не исполнено.

**Open risks:**
- **Docs-sync follow-up (новое, P1 phase-close):** `harness instructions`/adoption-режим/канон
  механизм не описаны в `docs/` — целевой файл `packages/harness/docs/` + перекрёстная ссылка;
  кандидат отдельного item'а до/во время P2.
- **Двенадцать корневых и пакетных руководств теперь УПРАВЛЯЕМЫЕ.** Ручная правка блоков между
  маркерами запрещена навсегда — контент только через фрагменты канона + повторный прогон,
  иначе следующий прогон гейта `[9/9]` покажет `managed-drift`.
- **Гейт `[9/9]` живёт только в `packages/harness/scripts/validate.sh`** — `analyst`/`task` в CI
  не покрыты вовсе (OQ-9); локальный прогон ≠ CI (R2).
- **`AGENTS.md:82` дублирует два common-правила** (долг D73) — правится фрагментом `root/codex.md`.
- **`apply_instructions` чувствителен к порядку `--authorize`** — цена ложного отказа на каждом
  следующем прогоне `apply`.
- **Фикстурный `provenance` не отражает миграцию P1.2** — нужен отдельный item со строкой
  `packages/harness/tests/test_instruction_compatibility.py` в `Files`.
- **Посторонний дифф в дереве не убран и не тронут**: `roadmap/README.md` (M) + untracked
  `roadmap/2026.07.29-launch-block-command-row.md`. Предсуществовал до P0.2, вне Files P1.
- **`packages/skiller/scripts/validate.sh` на дереве КРАСНЫЙ** — предсуществующий (Known
  Deviation P0.5), теперь material-отклонение P1.5.
- **`scripts/test-provider-docs.py` на дереве КРАСНЫЙ** (битая ссылка) — предсуществующий.
- **`scripts/public-hygiene.py` на дереве красный** — предсуществующий, закрыть/исключить до P5.1.
- **Аудит design-фазы исчерпан** — дефект в ТЗ P2–P5 всплывёт на исполнении.
- **Маршруты стали мягче:** девять items ушли из гейтованного `plan-exec` в `plan-run` (D47) —
  строка `Session: <model>/<effort>` в отчёте и Update Log каждого такого item'а обязательна.
- Общий state `~/.swissknifeman`/`~/.maind` изоляцией не покрыт — риск принят владельцем (D4).
- **P5.2 — единственная необратимая внутрь граница плана** (R1); CI не зовёт `validate.sh`
  пакетов `analyst`/`task` (OQ-9).
- Портируемость (`plan-portability-v1.md`): host-специфичные пути запрещены в
  `Inputs`/`Required Reads`/`Validation` — действует на P5.1–P5.3.

**Workarounds/Deferred/Open questions:**
- workarounds: правка общего `plans/verify-citations-known-exceptions.json` (D54) — дом
  design-коммит, не `Files` какого-либо item'а.
- deferred: изоляция общего state (OQ-5) · тонкая обвязка супервизора (P4.1, D38) · round-trip
  гейт живым прогоном Codex (`roadmap/codex-publication-consumer-acceptance.md`) · структурный
  перебор листинга Codex (OQ-7) · общий differ канона ролей (OQ-8) · машинные гейты
  PROMOTE-CANDIDATE («Validation прогнана», «design-заход в истории» D69) · `skiller registry`
  не прогнан (P0.5, Known Deviation P1.5) · раскатка на потребителей (D45) · push/PR/тег и
  публикация доков (D41) · расширение CI на `analyst`/`task` (OQ-9) · русский канон скиллов
  в `.gitignore` (Р5) · раскатка adoption-режима на 25 онбордженных проектов · фикстурный
  `provenance` P1.2 · сужение `root.codex.bootstrap`/`.launch-and-hook-integrity` (D73) ·
  порядок-чувствительный `--authorize` у `apply_instructions` · удаление pre-image'ов P1.5
  (держатся до архивации плана) · **docs-sync `harness instructions`/adoption/канон** (новое).
- open_questions: OQ-3 две capability `unsupported` у обоих провайдеров (P2.1) · OQ-6 дом логики
  Codex-обработчиков (P2.1) · OQ-7 структурный перебор бюджета обнаружения (P3.4) · OQ-8 дрейф
  канона ролей (Deferred) · OQ-9 CI не покрывает `analyst`/`task` (Deferred). OQ-2 закрыта D71,
  OQ-1 закрыта D31, OQ-4 закрыта D27.
