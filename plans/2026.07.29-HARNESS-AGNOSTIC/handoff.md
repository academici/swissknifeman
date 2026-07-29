# HANDOFF — 2026-07-29 — after P1.2

**Next:** ЗАПУСК ВРУЧНУЮ: implementation/high

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | high |
| Capabilities | — |
| Context | continue (/clear) — ручной item |
| Суть | P1.3 — аддитивные секции канона: девять новых ID (7 common + 2 extension), `catalog_version` → `1.1.0`, аддендум-контракт `root/contracts/instruction-canon-addendum-v1.md` |

```
Читай, в этом порядке, НИЧЕГО СВЕРХ:
1) plans/2026.07.29-HARNESS-AGNOSTIC/plan.md — Context, Execution Rules, §3 Routing, Status Board
2) plans/2026.07.29-HARNESS-AGNOSTIC/handoff.md (этот файл)
3) plans/2026.07.29-HARNESS-AGNOSTIC/phases/P1.md — Phase Context + item P1.3 целиком
4) Required Reads item'а P1.3 в указанном порядке (первый — research/05-instruction-canon-routing.md
   §«Новые ID», закрытая P1.1)

Исполни item P1.3 СТРОГО по его Scope Included/Excluded, Implementation Rules, Code Guidance —
без импровизации при расхождении с деревом (эскалация вместо самостоятельной правки плана).
ВАЖНО: P1.2 (закрыт 🟠) сознательно ОТЛОЖИЛ сужение `root.codex.bootstrap` и
`root.codex.launch-and-hook-integrity` (перенос трёх правил в common — `root.provider-parity`,
`root.worktree-safety`, `root.evidence-integrity`) — common-ID этих правил заводит ИМЕННО этот item.
После того как P1.3 заведёт эти три ID, сужение двух Codex-фрагментов остаётся ЗА P1.2 (follow-up
правка вне текущего P1.3, зафиксировать в его Pending Work/handoff при закрытии, либо — если
Routing/владелец сочтут нужным — отдельным follow-up item'ом; сам P1.3 узкие extension-фрагменты не
трогает, только заводит common-ID). Прогони Validation item'а целиком, зафиксируй passed/failed.
Закрой item штатной топологией plan-протокола (item-коммит по Files · bookkeeping-коммит плана ·
перезапись handoff.md · plan-lint --baseline HEAD с атрибуцией K) — модель/effort ЭТОЙ сессии
(implementation/high), не пин plan-exec (sonnet/medium): Routing item'а требует `Exec = manual`,
поэтому /task:plan-exec его отклонит на гейте — закрывай сам, по протоколу (Pre-mutation/Pre-final
Task Contract с ФАКТИЧЕСКИМ маршрутом сессии, две ветки закрытия 🟢/🟠, Update Log, launch-block
следующего шага).
```

**Штатный носитель исполнения** — `task:plan-run` под сессией **implementation/high** (без ритуала
`/model`+`/effort`, если уже в такой сессии), либо `/model sonnet` + `/effort high` +
`/task:plan-run 2026.07.29-HARNESS-AGNOSTIC P1.3`. Голая slash-команда `/task:plan-exec` СЮДА НЕ
ПОДХОДИТ: она пинит sonnet/medium, а Routing P1.3 требует effort `high` (`Exec = manual`, D39/D47) —
гейт п. 2 `plan-exec` отклонит запуск (`ROUTING-BLOCKED`).

**Done:** **P1.2 закрыт `🟠` Done with deviations** (`plan-run`/Sonnet/high — implementation/high,
совпадает с §3 Routing; item-коммит `e574fdda`). Актуализированы 8 из 18 фрагментов канона
(6 scope × 3 провайдер-файла), где матрица `research/05` §6 отмечала «обновляется»:
`root/common.md`, `root/claude-code.md`, `packages/{skiller,harness,maind,analyst,task}/common.md`,
`packages/harness/claude-code.md`. Десять фрагментов (три `root/codex.md`,
`packages/skiller/{claude-code,codex}.md` и семь codex-фрагментов остальных пакетов) байт-в-байт не
тронуты — их записи уже совпадали с живыми руководствами.
- **28 записей каталога/фикстуры обновлены**: 26 — новый литерал из колонки «Обязательный литерал»
  матрицы ДОБАВЛЕН к существующим `compatibility_assertions` (ни одно старое утверждение не
  удалено); 2 (`harness.identity`, `harness.claude-code.lifecycle-surfaces`) — список поверхностей
  расширен (safe-dirs, statusline, review-gate) и `router`→`agent-router` переименован для точности,
  утверждения регенерированы из новой прозы без потери возможностей.
- `sources[0].sha256` пересчитан для 55 записей, ссылающихся на 8 изменённых файлов.
  `catalog_version` `1.0.0`→`1.0.1`, `CATALOG_VERSION` в `instructions.py` синхронизирована (диф —
  одна строка константы). Фикстура `instruction-compatibility-v1.json`: `fixture_version` → `1.0.1`,
  `records[].assertions` синхронизированы с каталогом поимённо и по порядку.
- **Known Deviation:** фикстурный `provenance` НЕ дополнен полями миграции этого плана — Scope
  Included этого требовал дословно, но `test_instruction_compatibility.py::test_fixture_is_independent_pre_renderer_p5_6_inventory`
  (файл вне `Files` этого item'а) держит `assertEqual` на точный исходный 4-ключевой `provenance`
  (`D86`/`DUAL-PROVIDER`); любое добавление ломает зелёный тест. Решение исполнителя по D14: `provenance`
  оставлен байт-в-байт, миграция ограничена `fixture_version`+`records[]`. Дом дальнейшей починки (если
  нужна) — вне Scope P1.2, см. `phases/P1.md` P1.2 Known Deviations.
- Validation: `validate_catalog` — 0 диагностик · инвентарь 67 (`[17,11,11,9,10,9]`) · `check()` — те
  же 7 `ownership-conflict` + 5 `missing` · `bash packages/harness/scripts/validate.sh` — `OK`
  (463 теста `scripts/test.sh` зелёные, включая полный `test_instruction_compatibility.py`) · живые
  `CLAUDE.md`/`AGENTS.md` не тронуты · `plan-lint` — 0 ERROR, 2 WARN (оба предсуществующие).

**Ранее:** P1.1 закрыта `🟢` (матрица «правило → дом», D72–D74). P0 закрыта целиком (4/5 🟢 + 1/5 🟠).

**Remaining:** P1.3 → P1.4 → P1.5, затем P2 (5) → P3 (6) → P4 (5) → P5 (3). Итого 22/29 items ещё не
исполнено.

**Sources of truth:** `plans/2026.07.29-HARNESS-AGNOSTIC/plan.md` (§3 Routing, §5 D1–D74,
§7 Contracts, § Обсуждение 1–7, три блока `## Audit design`) · `phases/P0.md`–`P5.md` (P0 закрыта,
P1 — 1/5 🟢 + 1/5 🟠) · `research/05-instruction-canon-routing.md` (матрица «правило → дом» — вход
P1.3, P1.4 и P1.5) · `research/04-instruction-mechanism-inventory.md` (механизм, G1–G5, ограничения
авторинга) · `findings/02-rag-instruction-loading-2026-07-29.md` Ф7/Ф8 · `roadmap.md` (батч B1
закрыт; дальше всё solo) · `brief/00-brief.md` + `brief/01-refinements.md` · `findings/00`–`06` ·
`research/00`–`04`, `06`–`09` · `open-questions.md` (OQ-3, OQ-5–OQ-9 открыты) · `index.md` ·
`journal.jsonl` · `root/contracts/provider-parity-definition.md` (sealed v1) ·
`plans/archive/2026.07.19-DUAL-PROVIDER/root/contracts/provider-instruction-contract.md`
(frozen v1.0.0 — контракт механизма) · `plans/archive/2026.07.18-FOREMAN/` (архивирован) ·
`docs/reference.md`, `docs/rejected-optimizations.md` · `plans/README.md`.

**Open risks:**
- **Фикстурный `provenance` не отражает миграцию P1.2** (см. Known Deviation выше) — вне Scope
  дальнейших items, если владелец захочет иное, нужен отдельный item со строкой
  `packages/harness/tests/test_instruction_compatibility.py` в `Files`.
- **Сужение `root.codex.bootstrap`/`root.codex.launch-and-hook-integrity` осталось не сделанным**
  (D73): P1.3 заводит принимающие common-ID (`root.provider-parity`, `root.worktree-safety`,
  `root.evidence-integrity`), но САМО сужение двух Codex-фрагментов — работа, не покрытая явно
  ни P1.2 (уже закрыт), ни Scope Included P1.3 (заводит ID, не правит extension-фрагменты
  дословно) — исполнителю P1.3 назвать это Pending Work/эскалацией по факту, не молчать.
- **Правило `CHANGELOG.md`** (D55) доехало в канон впервые в P1.2 (`root.development-validation`) —
  закрыто, снято из рисков.
- **Посторонний дифф в дереве не убран и не тронут**: `roadmap/README.md` (M) + untracked
  `roadmap/2026.07.29-launch-block-command-row.md`. Существовал до P0.2, ни в один item-коммит
  P0.1–P1.2 не попал.
- **`packages/skiller/scripts/validate.sh` на дереве КРАСНЫЙ**: `ERROR: реестр устарел
  относительно источников — прогони: skiller registry`. Предсуществующий, Known Deviation P0.5.
- **`scripts/test-provider-docs.py` на дереве КРАСНЫЙ** (1 fail из 4) — битая ссылка
  `roadmap/self-learning-memory.md` из `README.md:122`. Предсуществующая.
- **`scripts/public-hygiene.py` на дереве красный** (предсуществующая находка) — закрыть или
  объявить исключением до P5.1.
- **`--check` не зовёт ни один гейт** (D21): до P2.5 конформанс каталога держится ручным прогоном.
- **Ложное срабатывание правила `plan_lint.py:1941-1948`** остаётся на `phases/P0.md:42` и
  `phases/P1.md:51` (2 WARN, стабильно, ERROR-счёт не затронут).
- **`§7 Consumed`, строка AR-контрактов, обещает «пин снимается в P0.3», но Scope P0.3 этого не
  нёс** — фактический адресат P4.1. Правит `plan-design` одной строкой §7.
- **Parse-контракт донора остаётся просроченным и измеренно breaking**: P4.5 по D37 обязан
  эскалировать, а не исполнять.
- **Аудит исчерпан, страховки «ещё один заход» больше нет** — дефект в ТЗ всплывёт на исполнении
  (P1.2 — живой пример: конфликт Scope Included с зелёным тестом вне Files).
- **Дисциплина «новая Validation обязана быть прогнана»** машинного гейта не имеет
  (PROMOTE-CANDIDATE, дом `roadmap/`). **Правило design-коммита (D69)** — тоже.
- **Маршруты стали мягче:** девять items ушли из гейтованного `plan-exec` в `plan-run` (D47) —
  строка `Session: <model>/<effort>` в отчёте и Update Log каждого такого item'а обязательна.
- Общий state `~/.swissknifeman`/`~/.maind` изоляцией не покрыт — риск принят владельцем (D4).
- **P5.2 — единственная необратимая внутрь граница плана** (R1); **локальный прогон гейтов ≠ CI**
  (R2), CI не зовёт `validate.sh` пакетов `analyst`/`task` (OQ-9).
- **Три items правят один `packages/harness/scripts/validate.sh` со сплошной перенумерацией**
  (P1.5 `[9/9]`, P4.3 `[10/10]`) — знаменатель снимается прогоном, не берётся из ТЗ (D48).
- **Порядок двух коммитов P1.5 — «принятие → гейт» (D66)**; **точка принуждения
  `delegation_contract` живёт в `pending` между P4.3 и P4.4** (D58).
- **P3.5 растит листинг, который меряет P3.4** (D52); **P3.3: гейт, который никогда не краснел, не
  доказан**; **P3.2** не стартует до закрытой P1.5 (D51/D67).
- **P4.4 правит канон ролей, раздаваемый флоту**, и ложится в ДВА носителя без гейта сверки (D35,
  OQ-8); контракты `2026.07.24-AGENT-RELIABILITY` произведены планом, закрытым `🟠` — P4.1 обязана
  метить недоказанное `[UNVERIFIED]`.
- Портируемость (`plan-portability-v1.md`): host-специфичные пути запрещены в
  `Inputs`/`Required Reads`/`Validation` — действует на P5.1–P5.3.

**Workarounds/Deferred/Open questions:**
- workarounds: **правка общего перечня `plans/verify-citations-known-exceptions.json`** (D54) — файл
  вне каталога плана, его дом — design-коммит (D69), не `Files` какого-либо item'а.
- deferred: изоляция общего state (OQ-5) · **вся постройка тонкой обвязки супервизора —
  `roadmap/artifex-thin-wrapper.md`, файл производит P4.1 (D38)** · round-trip гейт живым прогоном
  Codex (Р3, `roadmap/codex-publication-consumer-acceptance.md`) · структурный перебор листинга на
  стороне Codex (OQ-7 → `roadmap/`, D29 в редакции D52) · перекалибровка токенайзера `budget.py`
  (чужой ECO-OPT) · общий differ «канон ↔ инсталляционный шаблон» ролей (OQ-8) · машинный гейт
  «новая Validation прогнана» (PROMOTE-CANDIDATE) · машинный гейт «design-заход оставил состояние
  в истории» (PROMOTE-CANDIDATE D69) · починка ложного срабатывания `[NEEDS CLARIFICATION]` в
  `plan_lint.py` (P0.3) · **`skiller registry` не прогнан — реестр устарел относительно источников
  (P0.5, вне Scope)** · перевод прозы «кап делегирования» в командах `task:*` на ссылку к SSOT ·
  раскатка на потребителей (D45) · push/PR/тег и публикация доков (D41) · расширение CI на
  `analyst`/`task` (OQ-9) · русский канон скиллов в `.gitignore` (Р5) · собственный замер бюджета
  обнаружения на живом Codex CLI (`[UNVERIFIED]`, смежно с P3.4) · **раскатка adoption-режима на 25
  онбордженных проектов** (кандидат `roadmap/`, Scope Excluded фазы P1) · **фикстурный `provenance`
  P1.2** — обновление теста `test_instruction_compatibility.py` под новую форму, если владелец
  захочет (см. Open risks).
- open_questions: OQ-3 две capability `unsupported` у обоих провайдеров (P2.1) · OQ-6 дом логики
  Codex-обработчиков (P2.1) · OQ-7 структурный перебор бюджета обнаружения (замер P3.4) · OQ-8
  дрейф канона ролей и инсталляционного шаблона (Deferred) · OQ-9 CI не покрывает `analyst`/`task`
  (Deferred). OQ-2 закрыта D71 (вариант B), OQ-1 закрыта D31, OQ-4 закрыта D27.
