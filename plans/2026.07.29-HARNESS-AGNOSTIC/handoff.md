# HANDOFF — 2026-07-30 — after P3.6

**Next:** close: task:plan-close 2026.07.29-HARNESS-AGNOSTIC P3

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | low — механическая сверка таблиц/Phase Handoff по закрытым фактам, решений не принимается |
| Context | NEW SESSION — шаг-не-item |
| Суть | Фаза P3 (6/6 items терминальны — 1 🟢 + 5 🟠) готова к формальному закрытию: таблицы Phase Status/Status Board сверены, Phase Handoff фазы ещё не заполнен |

```
/task:plan-close 2026.07.29-HARNESS-AGNOSTIC P3
```

Если предпочтителен переход сразу к фазе P4 (детализирована, ждёт исполнения) без формального
закрытия P3 первым шагом — P4.1 (frontier/high, manual):

```
Исполни item P4.1 плана 2026.07.29-HARNESS-AGNOSTIC вручную (Exec=manual, frontier/high).
Порядок чтения: plan.md §0/§1/§2/§3 (строка P4.1)/§4 → handoff.md (этот файл) →
phases/P4.md Phase Context + P4.1 целиком → Required Reads item'а.
```

**Session:** Sonnet 5/high (implementation/high — точное соответствие §3 Routing строке P3.6,
`Exec = manual`, запуск через `task:plan-run`, D18/D47).

**Done:** P0 целиком (5/5) · P1 целиком (7/7) · P2 (9/9 items закрыты — 5 🟢 + 4 🟠, формально
не закрыта `plan-close`'ом) · **P3 целиком (6/6 items закрыты — 1 🟢 + 5 🟠), формально не
закрыта `plan-close`'ом.**

**Карта «item → коммит» (P3):**
P3.1 `f61ac378` · P3.2 `dd6a1404` · P3.3 `41f2156b` · P3.4 `599878e0` · P3.5 `1373fccf` · P3.6 —
**без item-коммита** (Files item'а не менялись: перечень §4 из шести правил `research/05`
целиком разрешился исходом «покрыто существующим скиллом» — `axioma/ecosystem-map` ·
`general/plan-protocol` · `general/verify-claims` + `repository-bootstrap/decision-verification`
· `repository-bootstrap/ecosystem-mcp` · `repository-bootstrap/skill-authoring` ·
`repository-bootstrap/release-discipline`; ноль диффа зафиксирован как законный исход, не
имитирован правкой; см. `phases/P3.md` P3.6 Completion Notes).

**Remaining:** Фаза P3 закрыта по items, ждёт формального `plan-close P3` (таблицы уже
согласованы, `## Phase Handoff` P3 ещё не заполнен). Фаза P2 остаётся тем же открытым долгом
(`plan-close P2`), не тронута этим item'ом. После формальных закрытий P2/P3 — P4 (5 items) →
P5 (3 items). Итого **8 из 35** items плана ещё не исполнено (P4.1–P4.5, P5.1–P5.3), плюс два
формальных закрытия фаз (P2, P3).

**Sources of truth:** `plan.md` (§3 Routing, §5 D1–D89, §6 Update Log, §4 Status Board — P3
`1/6` `🟡 In progress`, флип на терминальный статус — задача `plan-close P3`) · `phases/P3.md`
(Phase Context, P3.1–P3.6 Completion Notes) · `roadmap.md` §«Карта запуска» ·
`plans/2026.07.29-HARNESS-AGNOSTIC/research/05-instruction-canon-routing.md` §4 (перечень
выносов, вход этого item'а) · `journal.jsonl`.

**Open risks:**
- **`packages/skiller/scripts/validate.sh` красный на ОДНОМ предсуществующем гейте** (долг
  P0.5): §14 `ERROR: протухшие переводы SKILL.ru.md→SKILL.md`
  (`skills/repository-bootstrap/package-architecture/SKILL.md`, 225-строчный чужой RU-источник
  — требует содержательного перевода, не механической правки). **Был ЕДИНСТВЕННЫМ блокирующим
  долгом для Validation P3.6** (осталась им — этот item его не снял, вне `Files`). Чинится одним
  заходом: содержательный перевод из `SKILL.ru.md` + `check-translations.sh --stamp` + коммит.
  Дом: follow-up fix-item либо `roadmap/`.
- **Фаза P2 требует формального закрытия** (`plan-close 2026.07.29-HARNESS-AGNOSTIC P2`).
- **Фаза P3 требует формального закрытия** (`plan-close 2026.07.29-HARNESS-AGNOSTIC P3`) —
  новый открытый долг этого item'а (P3.6 был последним item'ом фазы).
- **`plan-lint` DoR-гейт (SKILL §7) даёт false positive на строке-легенде** для КАЖДОЙ фазы,
  чей статус перешёл в `🟡`/`🟠`/`🟢` — четыре WARN (P0/P1/P2/P3), не контентный дефект.
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
- **`roadmap/README.md` несёт чужую несвязанную строку** (`agent-scoped-skill-loading-vs-
  connect-default.md`, владельческий черновик 2026-07-30, byte-в-byte не тронут этим item'ом,
  соседствует с untracked `roadmap/2026.07.29-launch-block-command-row.md` — тоже не наш предмет).
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
  (заведён P2.4) · формальное закрытие фазы P2 (`plan-close`) · формальное закрытие фазы P3
  (`plan-close`, новое) · индекс `path-scoped rules` в hub (P3.1 Pending Work) · унификация
  verification-контрактов паков 4/10→10/10 (P3.2 Open risks) · добор таблицы внешних источников
  в `references/framework-audits.md` (P3.3 Pending Work) · сокращение 69 длинных описаний без
  триггера, one-way (P3.5 Pending Work) · рычаг №4 владельца (сжатие описаний ради слотов,
  ECO-OPT D74, OQ-7).
- open_questions: OQ-7 структурный перебор бюджета обнаружения Codex — ИЗМЕРЕН P3.4/P3.5,
  решение между тремя вариантами (`roadmap/codex-skill-listing-fallback-overflow.md`) остаётся
  открытым · OQ-8 дрейф канона ролей (Deferred) · OQ-9 CI не покрывает `analyst`/`task`
  (Deferred). OQ-3/OQ-6 закрыты D86/D87 (P2.1); OQ-2 закрыта D71, OQ-1 — D31, OQ-4 закрыта
  P3.4 записью канона авторинга (D27). Новых открытых вопросов P3.6 не добавил.
