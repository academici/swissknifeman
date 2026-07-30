# HANDOFF — 2026-07-30 — after P3.4

**Next:**

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | medium — §3 Routing строка P3.5 (`implementation/medium`, `Exec = plan-exec`) |
| Context | continue (/clear) — ручной item |
| Суть | P3.5 — гейт-рэтчет качества описаний-триггеров + починка blocker-набора (39 скиллов) двуязычным потоком |

```
/task:plan-exec 2026.07.29-HARNESS-AGNOSTIC P3.5
```

**Session:** Sonnet 5/high (implementation/high — точное соответствие предписанным
§3 Routing `implementation/high`; ни недобора, ни перебора, впервые в серии P3.3–P3.4).

**Done:** P0 целиком (5/5) · P1 целиком (7/7) · P2 целиком (9/9 — 5 🟢 + 4 🟠, формально не
закрыта `plan-close`'ом) · **P3.1 (🟠) + P3.2 (🟢) + P3.3 (🟠) + P3.4 (🟠) — 4/6 фазы P3.**

**Карта «item → коммит» (P3):**
P3.1 `f61ac378` · P3.2 `dd6a1404` · P3.3 `41f2156b` · P3.4 `599878e0` (у всех четырёх
item-коммит единственный).

**Remaining:** Фаза P2 не закрыта формально (`plan-close P2`) — открытый долг с предыдущих
заходов, не тронут этим item'ом. P3.5–P3.6 (2 items фазы P3) → P4 (5) → P5 (3). Итого
**10 из 35** items плана ещё не исполнено (плюс формальные закрытия фаз P2 и, впоследствии, P3).

**Sources of truth:** `plan.md` (§3 Routing, §5 D1–D89, §6 Update Log, §4 Status Board — P3
`1/6` `🟡 In progress`) · `phases/P3.md` (Phase Context, P3.1–P3.4 Completion Notes) ·
`roadmap.md` §«Карта запуска» · `roadmap/codex-skill-listing-fallback-overflow.md` (новая
запись D29/OQ-7, эта сессия) ·
`plans/2026.07.29-HARNESS-AGNOSTIC/artifacts/P3-skill-listing-budget.md` (замер этой сессии) ·
`packages/skiller/lib/skiller/budget.py` (provider-aware модель, эта сессия) · `journal.jsonl`.

**Open risks:**
- **`packages/skiller/scripts/validate.sh` красный на ОДНОМ предсуществующем гейте**
  (долг P0.5, СУЖЕН этой сессией — §12b снят побочным эффектом `skiller registry`,
  понадобившегося для регенерации `skill-authoring`): §14 `ERROR: протухшие переводы
  SKILL.ru.md→SKILL.md` (`skills/repository-bootstrap/package-architecture/SKILL.md`,
  225-строчный чужой RU-источник — требует содержательного перевода, не механической
  правки, вне `Files` P3.4). **Это ЕДИНСТВЕННЫЙ блокирующий долг для Validation
  P3.5/P3.6** — оба требуют зелёного `validate.sh`. Чинится одним заходом: regen из
  `SKILL.ru.md` + `check-translations.sh --stamp` + коммит. Дом: follow-up fix-item
  либо `roadmap/`.
- **Фаза P2 требует формального закрытия** (`plan-close 2026.07.29-HARNESS-AGNOSTIC P2`).
- **`plan-lint` DoR-гейт (SKILL §7) даёт false positive на строке-легенде** («Все `[NEEDS
  CLARIFICATION]` сняты…» матчится как сам маркер) для КАЖДОЙ фазы, чей статус перешёл в
  `🟡`/`🟠`/`🟢` — четыре WARN (P0/P1/P2/P3). Не контентный дефект, чинить в самом линтере.
- **`plan-lint` phase-first WARN**: «P3 содержит активные 🟡 items, хотя P2 ещё не терминальна»
  — производная того же незакрытого P2; снимается его `plan-close`.
- **Структурный перебор фолбэк-бюджета обнаружения Codex** (9/10 профилей, WARN-гейт
  `validate.sh` §17 держит число видимым) — три варианта решения записаны
  `roadmap/codex-skill-listing-fallback-overflow.md` (Codex-специфичный профиль ·
  принятая деградация · отложить до живого прогона Codex CLI), решение владельца не
  выбрано (OQ-7, D29).
- **Таблица «Внешние источники, всплывшие в аудитах»** в `references/framework-audits.md`
  прогоном #4 не пополнена (`Scope Included` P3.3 её не называл) — кандидат на добор.
- **path-scoped rules — индекс правил в hub не заведён** (P3.1 Pending Work): rules-каталоги
  есть у пяти паков, `generate-hub.sh` их не индексирует. Кандидат `roadmap/`.
- **Verification-контракты паков — разрыв 4/10 (review-gate) / 1/10 (`test-verifier`) / 6/10
  (ни того ни другого)** — измеренный факт в ledger'е P3.2, кодом не закрыт; дом — `roadmap/`.
- **CLI-обвязка `harness doctor --settings --provider codex` не заведена** (P2.4 Pending Work).
- **Декларативный (не инкрементальный) CLI `harness hooks --provider codex` /
  `harness agent-packs --provider codex render`** — merge-режим кандидат `roadmap/`.
- **Точная схема пейлоада Codex `apply_patch`** за пределами `tool_name` — `[UNVERIFIED]`.
- **Посторонний незакоммиченный дифф в дереве частично снят этим item'ом:**
  `roadmap/README.md` — СВОЯ правка закоммичена ВМЕСТЕ с давно висящей чужой строкой
  (`2026.07.29-launch-block-command-row.md`, byte-в-byte не тронута, была M до старта
  этого item'а); untracked `roadmap/2026.07.29-launch-block-command-row.md` остаётся
  нетронутым (не наш предмет).
- **Слепота `_validate_conflicts` к дублю СМЫСЛА** (`instructions.py:1005-1022`) — дом `roadmap/`.
- **Фикстурный `provenance` СОВМЕСТИМОСТИ не отражает миграцию P1.2** — не заведён.
- **Order-sensitivity `apply_instructions`** — дом заведён P2.8, реализация отложена (D84).
- **Двенадцать корневых и пакетных руководств УПРАВЛЯЕМЫЕ**: ручная правка блоков между
  маркерами запрещена навсегда.
- **Гейт `[9/9]` живёт только в `packages/harness/scripts/validate.sh`** — `analyst`/`task` в CI
  не покрыты (OQ-9).
- **`vitepress build` в дереве не прогоняется** — `node_modules` отсутствуют; новые страницы
  архива (`docs/audits/2026-07-29-harness-agnostic{,.raw}.md`) сборкой не проверены.
- **Маршруты мягче:** items с `effort high` идут через `plan-run` (D47) — строка
  `Session: <model>/<effort>` в отчёте и Update Log обязательна.
- Общий state `~/.swissknifeman`/`~/.maind` изоляцией не покрыт — риск принят владельцем (D4).
- **P5.2 — единственная необратимая внутрь граница плана** (R1).
- Портируемость (`plan-portability-v1.md`): host-специфичные пути запрещены в
  `Inputs`/`Required Reads`/`Validation` — действует на P5.1–P5.3.

**Workarounds/Deferred/Open questions:**
- workarounds: правка общего `plans/verify-citations-known-exceptions.json` (D54) — дом
  design-коммит, не `Files` какого-либо item'а. · Доказательство §16/§17 `validate.sh`
  изолированным раннером (текст секции извлечён `sed`'ом из закоммиченного `validate.sh`)
  — вынужденная форма, пока §14 краснеет раньше по порядку.
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
  (заведён P2.4) · формальное закрытие фазы P2 (`plan-close`) · индекс `path-scoped rules` в
  hub (P3.1 Pending Work) · унификация verification-контрактов паков 4/10→10/10 (P3.2 Open
  risks) · добор таблицы внешних источников в `references/framework-audits.md` (P3.3
  Pending Work).
- open_questions: OQ-7 структурный перебор бюджета обнаружения Codex — ИЗМЕРЕН P3.4, решение
  между тремя вариантами (`roadmap/codex-skill-listing-fallback-overflow.md`) остаётся
  открытым · OQ-8 дрейф канона ролей (Deferred) · OQ-9 CI не покрывает `analyst`/`task`
  (Deferred). OQ-3/OQ-6 закрыты D86/D87 (P2.1); OQ-2 закрыта D71, OQ-1 — D31, OQ-4 закрыта
  P3.4 записью канона авторинга (D27, было готово с design-прохода — этот item лишь
  зафиксировал вердикт письменно). Новых открытых вопросов P3.4 не добавил.
