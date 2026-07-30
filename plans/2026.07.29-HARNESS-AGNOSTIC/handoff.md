# HANDOFF — 2026-07-30 — after P1

**Next:** `/task:plan-audit 2026.07.29-HARNESS-AGNOSTIC P1`

| Параметр | Значение |
|:--|:--|
| Model | Claude Opus 5 |
| Thinking | xhigh — adversarial-аудит закрытой фазы против кода/git |
| Context | NEW SESSION |
| Суть | Фаза P1 закрыта (все семь items терминальны — 4 🟢 + 3 🟠), но три `🟠 Done with deviations` (P1.2, P1.3, P1.5) требуют аудита перед стартом P2; заход 1 (2026-07-30) дал RED и был закрыт ремедиацией P1.6/P1.7 — саму ремедиацию (и остающиеся `🟠`-items) второй adversarial-заход ещё не проверял |

```
/task:plan-audit 2026.07.29-HARNESS-AGNOSTIC P1
```

**Фаза P1 закрыта повторно `🟠 Done with deviations` (реконсиляция после реопена D75).** Все семь
items терминальны: P1.1/P1.4/P1.6/P1.7 `🟢`, P1.2/P1.3/P1.5 `🟠 Done with deviations`. `## Phase
Status` (`phases/P1.md`) и `## 4. Phase Index & Status Board` (`plan.md`) сверены и совпадают
(`4/7`, `🟠 Done with deviations`). Пометка `> УСТАРЕЛ` в `## Phase Handoff` снята — раздел
переписан целиком под финальное состояние фазы.

**Done:** P0 целиком (5/5 терминальны) · P1.1–P1.7 терминальны (4 `🟢` + 3 `🟠`): матрица «правило →
дом» по семи живым руководствам (P1.1); канон догнал реальность — фрагменты + каталог 76 ID `1.1.1`
+ аддендум-контракт sealed v1 (P1.2, P1.3); adoption-режим + CLI `harness instructions
<plan|check|adopt|apply|repair>` + модульная точка `--check` (P1.4); двенадцать проекций приняты под
управление, гейт дрейфа `[9/9]` в `packages/harness/scripts/validate.sh`, always-on бюджет
7620 → 5322 ток (P1.5); ремедиация канона — шесть правил, D73, `instructions`, гейт покрытия
105/105, бюджет 5322→5495 ток (P1.6); бухгалтерия ремонта — карта хешей, честная атрибуция WARN,
три подписи (P1.7).

**Карта «item → коммит» (P1; item-коммит | сопутствующие bookkeeping):**
P1.1 `fd5183af` | `340d0846` · P1.2 `e574fdda` | `d1e393af` · P1.3 `b02e48be` | `4ae56350`
(bookkeeping), `5996d92d` (дозапись журнала), `b191a19c` (Known Deviations) · P1.4 `1e0262a4` |
`d5482b37` · P1.5 `c3b3a8a3` (принятие) + `4647ad4b` (гейт) | `d052698f` · P1.6 `d5e01ef7`
(канон+рендер) + `eb64ea6c` (гейт покрытия) | `4416322e` (bookkeeping) · P1.7 `003180bf` (карта
хешей + три подписи).

**Известные отклонения (агрегат по items — полный текст в `phases/P1.md` § `Phase Handoff`):**
- P1.2 — process: `provenance` фикстуры совместимости НЕ дополнен полями миграции (существующий
  тест держит точный 4-ключевой словарь; ограничено `fixture_version` → `1.0.1`). Долг открыт.
- P1.3 — process: item-коммит несёт дифф вне `Files` (тест-литерал 67 → 76, регенерированная
  `provider-instructions.md`) — структурное следствие роста каталога; плюс порядок коммитов.
- P1.5 — material: `bash packages/skiller/scripts/validate.sh` красный (предсуществующая P0.5-
  краснота, починка вне `Files`); process: `mapping.json` + pre-image'ы в carve-out `artifacts/`;
  process: `apply` перезапущен после `INSTRUCTION_WRITE_FORBIDDEN` (no-write, дерево не тронуто);
  порядок коммитов пре-имиджей (P1.7, F7) — откат с дерева `c3b3a8a3` был невозможен.
- P1.6 — process: `--authorize` порядок из собственного ТЗ item'а не рабочий — исполнено верным
  алфавитным порядком; Scope/семантика не затронуты. Точечная правка формулировки остаётся открытым
  риском.

**Docs-sync:** подтверждён follow-up, крупнее этой фазы. Новый CLI `harness instructions`,
adoption-режим и механизм канона (`instructions.py`, гейт дрейфа и гейт покрытия литералов в
`validate.sh`) нигде в `docs/` не описаны. Целевое место — `packages/harness/docs/`
(environment/CLI-поверхность) + перекрёстная ссылка из `docs/routing.md`/`docs/control-surface.md`.

**Sources of truth:** `plan.md` (§3 Routing, §5 D1–D79, §6 Update Log с картой хешей, §7 Contracts,
§4 Phase Index & Status Board — P1 `4/7 🟠 Done with deviations`) · `phases/P0.md` (закрыта) ·
`phases/P1.md` (закрыта `🟠 Done with deviations`, `## Phase Handoff` актуален, блок
`## Audit P1 — 2026-07-30` — заход 1, RED) · `research/10-p1-remediation-canon-and-coverage.md`
(грунт ремедиации) · `research/05-instruction-canon-routing.md` (матрица, read-only вход) ·
`research/04-instruction-mechanism-inventory.md` · `brief/01-refinements.md` Р7/Р8 ·
`artifacts/P1.5-mapping.json` + `artifacts/P1.5-preimages/` (держатся до архивации плана) ·
`artifacts/P1.6-extract-literals.py` (генератор фикстуры покрытия, идемпотентен) ·
`packages/harness/tests/fixtures_data/instruction-literal-coverage-v1.json` (105 литералов) ·
`roadmap.md` (v0.9.0, 31 item) · `root/contracts/provider-parity-definition.md` (sealed v1) ·
`root/contracts/instruction-canon-addendum-v1.md` (sealed v1) · `journal.jsonl` ·
`plans/archive/2026.07.18-FOREMAN/`.

**Remaining:** аудит P1 (обязателен из-за трёх `🟠`) → P2 (5) → P3 (6) → P4 (5) → P5 (3). Итого
19/31 items ещё не исполнено плюс сам аудит P1.

**Почему `Next` — аудит, а не P2:** протокол требует adversarial-аудит фазы перед стартом следующей,
если ХОТЯ БЫ один item закрыт `🟠 Done with deviations` — здесь их три (P1.2, P1.3, P1.5). Заход 1
аудита (2026-07-30) уже состоялся и дал RED, но его мандат был «выполнены ли Deliverables Scope
Included фазы», и находки были закрыты ремедиацией (P1.6/P1.7) под `plan-run`/`plan-exec` —
самопроверкой исполнителя, а не независимым adversarial-заходом. Сами `🟠`-items (P1.2/P1.3/P1.5)
по протоколу реопена не правились (только Known Deviations/Pending Work и три названные подписи в
P1.7) и никогда не проходили собственный аудит на предмет «сверка 🟠 с кодом/git, no-op, scope
drift». Поэтому обязательство «аудит перед P2» остаётся неисполненным, и `Next` указывает на второй
заход `plan-audit`, а не на `plan-design P2` или `plan-run P2.1`.

**Open risks:**
- **Обязательный второй заход `plan-audit P1`** (см. выше) — до его зелёного/ATTENTION-вердикта
  переход к P2 нарушает протокол.
- **Гейт покрытия литералов заведён в P1.6 и обязан остаться единственным носителем проверки
  ПОКРЫТИЯ.** Любая будущая правка канона обязана держать его зелёным; фикстура покрытия
  генерируемая — правка руками запрещена (`root.generated-artifacts`), только повторный прогон
  `artifacts/P1.6-extract-literals.py`.
- **Дефект собственного ТЗ P1.6, найден и раскрыт, но не починен:** формулировка «`--authorize`
  порядок — scope × provider, не алфавитный» неверна; корректная (алфавитная, как P1.5 изначально
  утверждал) требует отдельной точечной правки текста — кандидат: новая D-запись или follow-up item.
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
  формулировка порядка `--authorize` у `apply_instructions` (см. Open risks) · фикстурный
  `provenance` P1.2 · изоляция общего state (OQ-5) · тонкая обвязка супервизора (P4.1, D38) ·
  round-trip гейт живым прогоном Codex · структурный перебор листинга Codex (OQ-7) · общий differ
  канона ролей (OQ-8) · машинные гейты PROMOTE-CANDIDATE («Validation прогнана», «design-заход в
  истории» D69) · `skiller registry` не прогнан (P0.5) · раскатка на потребителей (D45) ·
  push/PR/тег и публикация доков (D41) · расширение CI на `analyst`/`task` (OQ-9) · русский канон
  скиллов в `.gitignore` (Р5) · раскатка adoption-режима на онбордженные проекты · удаление
  pre-image'ов P1.5 (держатся до архивации плана) · docs-sync `harness instructions`/adoption/канон.
- open_questions: OQ-3 две capability `unsupported` у обоих провайдеров (P2.1) · OQ-6 дом логики
  Codex-обработчиков (P2.1) · OQ-7 структурный перебор бюджета обнаружения (P3.4) · OQ-8 дрейф
  канона ролей (Deferred) · OQ-9 CI не покрывает `analyst`/`task` (Deferred). OQ-2 закрыта D71,
  OQ-1 закрыта D31, OQ-4 закрыта D27. Реопен P1 новых открытых вопросов не добавил (развилки
  закрыты D75–D79 по режиму Р6).
