# HANDOFF — 2026-07-30 — after P2

**Next:** audit: task:plan-audit 2026.07.29-HARNESS-AGNOSTIC P2

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | xhigh — фаза закрыта с deviations (4 из 9 items 🟠), аудит перед следующей фазой |
| Context | NEW SESSION — шаг-не-item |
| Суть | Фаза P2 закрыта (`plan-close`, 5🟢+4🟠); перед стартом P4 — adversarial-аудит закрытой фазы P2 |

```
/task:plan-audit 2026.07.29-HARNESS-AGNOSTIC P2
```

**Session:** Sonnet 5/low (реконсиляция/закрытие фазы P2 + бухгалтерская реконсиляция находок
аудита P3 — механическая сверка таблиц и Phase Handoff по уже закрытым item'ам, решений не
принималось).

**Done:** P0 целиком (5/5) · P1 целиком (7/7) · **P2 закрыта `plan-close`'ом (9/9 items — 5 🟢 +
4 🟠, `🟠 Done with deviations`).** · **P3 закрыта `plan-close`'ом (6/6 items — 0 🟢 + 6 🟠,
`🟠 Done with deviations`), аудит P3 проведён (вердикт ATTENTION) и реконсилирован этим же
заходом** (см. `## Audit P3 — 2026-07-30` в `phases/P3.md` и Update Log `plan.md`).

**Карта «item → коммит» (P2, реконсилировано 2026-07-30, аудит P2, находка F1):**
P2.1 `ed306ca6` · P2.2 `632e75d3`(+`ad325a5e`) · P2.3 `c97e5cfb`(+`3e883a68`) ·
P2.4 `cf1498a1`(+`966d7764`) · P2.5 `fa826d47` · P2.6 `317622c0`+`23c1090c` · P2.7 `e16082a1` ·
P2.8 `a264a339` · P2.9 `ffda7173`.

**Карта «item → коммит» (P3):**
P3.1 `f61ac378` · P3.2 `dd6a1404` · P3.3 `41f2156b` · P3.4 `599878e0` · P3.5 `1373fccf` · P3.6 —
без item-коммита (законный исход «покрыто существующим скиллом», ноль диффа зафиксирован).

**Реконсиляция P3 этим заходом (без реопена, без переоценки Deliverables):**
- P3.2 `🟢`→`🟠 Done with deviations` (material-триггер «Validation осталась красной»,
  `validate.sh` на `dd6a1404`: exit=1) — Status Board P3 `1/6`→`0/6`.
- Три числа исправлены на воспроизводимые с якорем дерева: тесты «535»→«522 (509 было на
  `41f2156b` + 13 новых, на `599878e0`)»; lint «5 WARN»→«4 WARN» в трёх местах (P3.4/P3.5/P3.6),
  с пометкой, что пятый WARN (`phase-first`) наблюдался на промежуточном незакоммиченном
  состоянии до флипа статуса фазы и на сданном дереве не воспроизводится; таблица проверенных
  фактов P3.2 «стало 9»→«стало 10 (на `dd6a1404`)».
- Восемь цитат `bash bin/skiller …` → `bash packages/skiller/bin/skiller …` (Validation
  P3.4/P3.5/P3.6, Completion Notes P3.4/P3.6) — `bin/skiller` в дереве нет ни на одном коммите.
- OQ-7 (`open-questions.md`) — «8 профилей из 9» → измеренное «9 профилей из 10 (P3.4, на
  `599878e0`)».
- `roadmap/README.md` — обе целевые спеки (`2026.07.29-launch-block-command-row.md`,
  `agent-scoped-skill-loading-vs-connect-default.md`) закоммичены как есть (дефолт владельца,
  индекс каталога больше не ссылается на untracked-файлы).

**Remaining:** после аудита P2 — P4 (5 items) → P5 (3 items). Итого **8 из 35** items плана ещё
не исполнено (P4.1–P4.5, P5.1–P5.3), плюс аудит P2.

**Sources of truth:** `plan.md` (§3 Routing, §5 D1–D89, §6 Update Log, §4 Status Board — P2
`5/9`, P3 `0/6`, обе `🟠 Done with deviations`) · `phases/P2.md` (Phase Context, P2.1–P2.9
Completion Notes, Phase Handoff) · `phases/P3.md` (Phase Context, `## Audit P3 — 2026-07-30`,
P3.1–P3.6 Completion Notes реконсилированы, Phase Handoff) · `roadmap.md` §«Карта запуска» ·
`journal.jsonl`.

**Open risks:**
- **`packages/skiller/scripts/validate.sh` красный на ОДНОМ предсуществующем гейте** (долг
  P0.5): §14 `ERROR: протухшие переводы SKILL.ru.md→SKILL.md`
  (`skills/repository-bootstrap/package-architecture/SKILL.md`, 225-строчный чужой RU-источник
  — требует содержательного перевода, не механической правки). Сквозной долг, тянущийся через
  P2.2–P2.4 и P3.1/P3.3/P3.4/P3.5/P3.6 — ни один item его не создал, каждый задокументировал.
  Чинится одним заходом: содержательный перевод + `check-translations.sh --stamp` +
  `skiller registry` + коммит. Дом: follow-up fix-item либо `roadmap/`.
- **`plan-lint` DoR-гейт (SKILL §7) даёт false positive на строке-легенде** для КАЖДОЙ фазы,
  чей статус перешёл в `🟡`/`🟠`/`🟢` — WARN (P0/P1/P2/P3), не контентный дефект.
- **69 длинных описаний без триггера** в `desc-trigger-burndown.txt` (унаследованный долг,
  P3.5) — сокращаются по одному при следующей содержательной правке каждого скилла, не
  батчем; `roadmap/skill-description-quality.md` держит критерий.
- **Структурный перебор фолбэк-бюджета обнаружения Codex** (9/10 профилей, WARN-гейт
  `validate.sh` §17 держит число видимым) — три варианта решения записаны
  `roadmap/codex-skill-listing-fallback-overflow.md`, решение владельца не выбрано (OQ-7, D29).
- **Таблица «Внешние источники, всплывшие в аудитах»** в `references/framework-audits.md`
  прогоном #4 не пополнена — кандидат на добор.
- **path-scoped rules — индекс правил в hub не заведён** (P3.1 Pending Work) — кандидат `roadmap/`.
- **Verification-контракты паков — разрыв 4/10 (review-gate) / 1/10 (`test-verifier`) / 6/10
  (ни того ни другого)** — измеренный факт в ledger'е P3.2, кодом не закрыт; дом — `roadmap/`.
- **CLI-обвязка `harness doctor --settings --provider codex` не заведена** (P2.4 Pending Work).
- **Декларативный (не инкрементальный) CLI `harness hooks --provider codex` /
  `harness agent-packs --provider codex render`** — merge-режим кандидат `roadmap/`.
- **Точная схема пейлоада Codex `apply_patch`** за пределами `tool_name` — `[UNVERIFIED]`.
- **`phases/P1.md` несёт два остаточных вхождения фразы A7** вне трёх Files-локаций P2.9
  (цитата находки внутри блока аудита + эхо в архивном launch-block'е) — историческое
  свидетельство, требует D-записи владельца для правки архивных секций либо остаётся навсегда.
- **Слепота `_validate_conflicts` к дублю СМЫСЛА** (`instructions.py:1005-1022`) — дом `roadmap/`.
- **Фикстурный `provenance` СОВМЕСТИМОСТИ не отражает миграцию P1.2** — не заведён.
- **Order-sensitivity `apply_instructions`** — дом заведён P2.8, реализация отложена (D84).
- **Двенадцать корневых и пакетных руководств УПРАВЛЯЕМЫЕ**: ручная правка блоков между
  маркерами запрещена навсегда.
- **Гейт `[9/9]` живёт только в `packages/harness/scripts/validate.sh`** — `analyst`/`task` в CI
  не покрыты (OQ-9).
- **`vitepress build` в дереве не прогоняется** — `node_modules` отсутствуют.
- **Маршруты мягче:** items с `effort high` идут через `plan-run` (D47) — строка
  `Session: <model>/<effort>` в отчёте и Update Log обязательна.
- Общий state `~/.swissknifeman`/`~/.maind` изоляцией не покрыт — риск принят владельцем (D4).
- **P5.2 — единственная необратимая внутрь граница плана** (R1).
- Портируемость (`plan-portability-v1.md`): host-специфичные пути запрещены в
  `Inputs`/`Required Reads`/`Validation` — действует на P5.1–P5.3.

**Workarounds/Deferred/Open questions:**
- workarounds: правка общего `plans/verify-citations-known-exceptions.json` (D54) — дом
  design-коммит, не `Files` какого-либо item'а. · Доказательство §16/§17 `validate.sh`
  изолированным раннером — вынужденная форма, пока §14 краснеет раньше по порядку.
- deferred: замер формата транскрипта Codex · opt-in флаг Claude-половины `git-guardrails` ·
  проекция `writable_roots` из allowlist'а · правка `_validate_conflicts`/схемы `obligations` ·
  починка order-sensitivity `apply_instructions` (дом заведён P2.8) · фикстурный `provenance`
  P1.2 · изоляция общего state (OQ-5) · тонкая обвязка супервизора (P4.1, D38) · round-trip гейт
  живым прогоном Codex (D3) · структурный перебор листинга Codex (заведён P3.4, решение — OQ-7)
  · общий differ канона ролей (OQ-8) · машинные гейты PROMOTE-CANDIDATE · регенерация
  `package-architecture` SKILL.ru.md→SKILL.md (долг P0.5, сужен P3.4 до одного файла) ·
  раскатка на потребителей (D45) · push/PR/тег и публикация доков (D41) · расширение CI на
  `analyst`/`task` (OQ-9) · русский канон скиллов в `.gitignore` (Р5) · раскатка adoption-режима
  · удаление pre-image'ов P1.5 · починка архивных упоминаний A7 в `phases/P1.md` ·
  декларативный merge-режим `harness hooks --provider codex` (заведён P2.3) · декларативный
  merge-режим `harness agent-packs --provider codex render` (заведён P2.4) · точная схема
  Codex `apply_patch` (заведён P2.3) · отдельный machine-owned `check_command` для Codex
  `review-gate` (заведён P2.3) · CLI-флаг `harness doctor --settings --provider codex`
  (заведён P2.4) · индекс `path-scoped rules` в hub (P3.1 Pending Work) · унификация
  verification-контрактов паков 4/10→10/10 (P3.2 Open risks) · добор таблицы внешних источников
  в `references/framework-audits.md` (P3.3 Pending Work) · сокращение 69 длинных описаний без
  триггера, one-way (P3.5 Pending Work) · рычаг №4 владельца (сжатие описаний ради слотов,
  ECO-OPT D74, OQ-7).
- open_questions: OQ-7 структурный перебор бюджета обнаружения Codex — ИЗМЕРЕН P3.4/P3.5
  (9/10, `open-questions.md` теперь несёт измеренное число), решение между тремя вариантами
  (`roadmap/codex-skill-listing-fallback-overflow.md`) остаётся открытым · OQ-8 дрейф канона
  ролей (Deferred) · OQ-9 CI не покрывает `analyst`/`task` (Deferred). OQ-3/OQ-6 закрыты
  D86/D87 (P2.1); OQ-2 закрыта D71, OQ-1 — D31, OQ-4 закрыта P3.4 записью канона авторинга
  (D27). Новых открытых вопросов это закрытие не добавило.
