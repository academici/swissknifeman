# HANDOFF — 2026-07-29 — after P1.5

**Next:** `/task:plan-close 2026.07.29-HARNESS-AGNOSTIC P1`

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | low |
| Capabilities | — |
| Context | NEW SESSION — шаг-не-item |
| Суть | Закрыть фазу P1 (все пять items терминальны): Phase Handoff, счётчики Status Board, статус фазы, lint |

```
/task:plan-close 2026.07.29-HARNESS-AGNOSTIC P1
```

Фаза P1 отработана целиком: пять items терминальны (2 × `🟢` + 3 × `🟠`), но `## Phase Handoff`
в `phases/P1.md` — плейсхолдер, а строка фазы в `plan.md` §4 всё ещё `🟡 In progress`. Это ровно
работа `plan-close <ID> Pn`, а не следующего item'а: P2.1 не стартует, пока фаза P1 не терминальна
(предусловие phase-first). После закрытия фазы следующий шаг — P2.1 (`frontier/high`,
`Exec = manual`, триаж 17 `unsupported`), для него понадобится **NEW SESSION**.

**Done:** **P1.5 закрыт `🟠`** (`plan-run` / Claude Opus 5 (1M context) / high — frontier/high,
точное совпадение с §3 Routing, не перебор; item-коммит `4647ad4b`, коммит принятия `c3b3a8a3`).
Живая транзакция проведена в предписанном порядке `check` ДО → `adopt` семи → `apply` пяти →
`check` ПОСЛЕ: семь `ownership-conflict` целей (`CLAUDE.md`, `AGENTS.md`, пять пакетных
`CLAUDE.md`) приняты owner-gated режимом с Owner D# `2026.07.29-HARNESS-AGNOSTIC D12`,
посекционным `covered_spans`-mapping'ом (43 секции по фактическим границам `##`, объединение =
весь файл, непокрытых байт нет) и семью верифицированными pre-image'ами; пять отсутствовавших
пакетных `AGENTS.md` созданы `apply`. Все двенадцать целей `clean`, lock несёт 14 записей
(2 чужих от донора не тронуты + 12 наших, из них 7 с провенансом принятия). Шаг гейта
`[9/9] дрейф инструкций (12 проекций)` встал в `packages/harness/scripts/validate.sh` со
сплошной перенумерацией восьми существующих (`grep` — девять `[N/9]`, ни одной `/8`).
**Always-on бюджет: 7 620 → 5 322 ток (−30 %), `ELEVATED` → `OK`** (target ≤7000, warn >10000) —
порог не превышен, роста нет. `CLAUDE.md` — 88 строк / 7 520 байт (было 194 / 20 705), Codex-стек
`AGENTS.md` + крупнейший пакетный = 11 191 байт против потолка 32 768 (34 %).
- **Known Deviations:** (1) material — `bash packages/skiller/scripts/validate.sh` остался КРАСНЫМ
  (`реестр устарел относительно источников`); краснота предсуществующая (P0.5), её починка
  (`skiller registry`) правит файлы вне `Files` P1.5; (2) process — `mapping.json`, семь pre-image'ов
  и генератор положены в carve-out `plans/2026.07.29-HARNESS-AGNOSTIC/artifacts/` (pre-image обязан
  лежать внутри репо: `pre_image_path` уезжает в коммитимый lock); (3) process — `apply` отказал на
  первом прогоне (`INSTRUCTION_WRITE_FORBIDDEN`) из-за порядка целей в `--authorize`, дерева не изменив.
- Validation: `--check` `exit=0` (12 `clean`, CLI и модульная точка согласны) · `bash packages/harness/
  scripts/validate.sh` — `validate: OK` включая `[9/9]` · `bash packages/task/scripts/validate.sh` —
  `validate: OK` · `bash packages/skiller/scripts/validate.sh` — **failed**, см. Known Deviations ·
  Codex-стек `exit=0` · порядок коммитов D66 `exit=0` · `plan-lint` — 0 ERROR, 2 WARN (предсуществующий
  ложный `[NEEDS CLARIFICATION]`).
- Потребители целы: `harness doctor` — `OK` · `maind health --cwd` — `exit=0` (FAIL'ы — незапущенный
  демон памяти, окружение) · `skiller doctor` — три FAIL, все воспроизводятся идентично в нетронутом
  основном дереве (или являются артефактом worktree). Откат по pre-image не потребовался.
- **Pending Work:** (1) `apply_instructions` требует `--authorize` в плановом (алфавитном) порядке и
  отказывает без подсказки — кандидат `roadmap/`; (2) долг D73 стал видимым в живом `AGENTS.md:82`
  (повтор common-правил `root.worktree-safety`/`root.provider-parity`) — чинится во фрагменте канона.

**Ранее:** P1.4 закрыт `🟢` (adoption-режим + CLI `harness instructions`). P1.3 закрыта `🟠`
(девять аддитивных ID канона 1.1.0 + аддендум-контракт). P1.2 закрыта `🟠` (8/18 фрагментов канона
актуализированы). P1.1 закрыта `🟢` (матрица «правило → дом», D72–D74). P0 закрыта целиком
(4/5 🟢 + 1/5 🟠).

**Remaining:** закрытие фазы P1, затем P2 (5) → P3 (6) → P4 (5) → P5 (3). Итого 19/29 items ещё
не исполнено.

**Sources of truth:** `plans/2026.07.29-HARNESS-AGNOSTIC/plan.md` (§3 Routing, §5 D1–D74,
§7 Contracts, § Обсуждение 1–7, три блока `## Audit design`) · `phases/P0.md`–`P5.md` (P0 закрыта,
P1 — все пять items терминальны: 2 🟢 + 3 🟠, фаза ждёт `plan-close`) ·
`research/05-instruction-canon-routing.md` (матрица «правило → дом» — вход P1.1–P1.5 закрыт) ·
`research/04-instruction-mechanism-inventory.md` (механизм, G1–G5 — все пять закрыты) ·
`artifacts/P1.5-mapping.json` + `artifacts/P1.5-preimages/` (source-to-semantic mapping и семь
pre-image'ов принятия — хранятся до закрытия фазы) · `artifacts/P1.5-build-mapping.py` (генератор
mapping'а) · `findings/02-rag-instruction-loading-2026-07-29.md` Ф7/Ф8 · `roadmap.md` (батч B1
закрыт; дальше всё solo) · `brief/00-brief.md` + `brief/01-refinements.md` · `findings/00`–`06` ·
`research/00`–`04`, `06`–`09` · `open-questions.md` (OQ-3, OQ-5–OQ-9 открыты) · `index.md` ·
`journal.jsonl` · `root/contracts/provider-parity-definition.md` (sealed v1) ·
`root/contracts/instruction-canon-addendum-v1.md` (sealed v1, P1.3) ·
`plans/archive/2026.07.19-DUAL-PROVIDER/root/contracts/provider-instruction-contract.md`
(frozen v1.0.0 — контракт механизма) · `plans/archive/2026.07.18-FOREMAN/` (архивирован) ·
`docs/reference.md`, `docs/rejected-optimizations.md` · `plans/README.md`.

**Open risks:**
- **Двенадцать корневых и пакетных руководств теперь УПРАВЛЯЕМЫЕ.** Ручная правка блоков между
  маркерами запрещена навсегда: контент меняется только через фрагменты канона
  (`packages/harness/configs/common/instructions/**`) + повторный прогон, иначе следующий прогон
  гейта `[9/9]` покажет `managed-drift`. Правило записано в самом каноне (`root.generated-artifacts`).
- **Гейт `[9/9]` живёт только в `packages/harness/scripts/validate.sh`** — CI пакета harness его
  зовёт, а `analyst`/`task` в CI не покрыты вовсе (OQ-9); локальный прогон ≠ CI (R2).
- **`AGENTS.md:82` дублирует два common-правила** (долг D73, см. Pending Work P1.5) — правится
  фрагментом `root/codex.md`, не живым файлом.
- **`apply_instructions` чувствителен к порядку `--authorize`** (Pending Work P1.5) — цена ложного
  отказа на каждом следующем прогоне `apply`.
- **Фикстурный `provenance` не отражает миграцию P1.2** (P1.2 Known Deviation) — нужен отдельный item
  со строкой `packages/harness/tests/test_instruction_compatibility.py` в `Files`.
- **Посторонний дифф в дереве не убран и не тронут**: `roadmap/README.md` (M) + untracked
  `roadmap/2026.07.29-launch-block-command-row.md`. Существовал до P0.2, ни в один item-коммит
  P0.1–P1.5 не попал.
- **`packages/skiller/scripts/validate.sh` на дереве КРАСНЫЙ**: `ERROR: реестр устарел
  относительно источников — прогони: skiller registry`. Предсуществующий, Known Deviation P0.5,
  теперь ещё и material-отклонение P1.5 (его Validation требовала зелёного).
- **`scripts/test-provider-docs.py` на дереве КРАСНЫЙ** (1 fail из 4) — битая ссылка
  `roadmap/self-learning-memory.md` из `README.md:122`. Предсуществующая.
- **`scripts/public-hygiene.py` на дереве красный** (предсуществующая находка) — закрыть или
  объявить исключением до P5.1.
- **`harness doctor --provider-audit` печатает `HARNESS_CATALOG_MISMATCH:test`** — предсуществующий
  неблокирующий диагностический вывод несвязанного `profile-catalog.json`/MCP/roles-аудита;
  не гейтит `validate: OK`; вне предмета этого плана.
- **Ложное срабатывание правила `plan_lint.py:1941-1948`** остаётся на `phases/P0.md:42` и
  `phases/P1.md:51,138` (2 WARN, стабильно, ERROR-счёт не затронут).
- **`§7 Consumed`, строка AR-контрактов, обещает «пин снимается в P0.3», но Scope P0.3 этого не
  нёс** — фактический адресат P4.1. Правит `plan-design` одной строкой §7.
- **Parse-контракт донора остаётся просроченным и измеренно breaking**: P4.5 по D37 обязан
  эскалировать, а не исполнять.
- **Аудит исчерпан, страховки «ещё один заход» больше нет** — дефект в ТЗ всплывёт на исполнении.
- **Дисциплина «новая Validation обязана быть прогнана»** машинного гейта не имеет
  (PROMOTE-CANDIDATE, дом `roadmap/`). **Правило design-коммита (D69)** — тоже.
- **Маршруты стали мягче:** девять items ушли из гейтованного `plan-exec` в `plan-run` (D47) —
  строка `Session: <model>/<effort>` в отчёте и Update Log каждого такого item'а обязательна.
- Общий state `~/.swissknifeman`/`~/.maind` изоляцией не покрыт — риск принят владельцем (D4).
- **P5.2 — единственная необратимая внутрь граница плана** (R1); **локальный прогон гейтов ≠ CI**
  (R2), CI не зовёт `validate.sh` пакетов `analyst`/`task` (OQ-9).
- **P4.3 правит тот же `packages/harness/scripts/validate.sh` со сплошной перенумерацией**
  `[10/10]` — знаменатель снимается прогоном, не берётся из ТЗ (D48); база теперь `[1/9]`…`[9/9]`.
- **P3.5 растит листинг, который меряет P3.4** (D52); **P3.3: гейт, который никогда не краснел, не
  доказан**; **P3.2 разблокирована** — её зависимость от закрытой P1.5 (D51/D67) снята.
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
  (P0.5, вне Scope; теперь ещё и Known Deviation P1.5)** · перевод прозы «кап делегирования» в
  командах `task:*` на ссылку к SSOT · раскатка на потребителей (D45) · push/PR/тег и публикация
  доков (D41) · расширение CI на `analyst`/`task` (OQ-9) · русский канон скиллов в `.gitignore` (Р5) ·
  собственный замер бюджета обнаружения на живом Codex CLI (`[UNVERIFIED]`, смежно с P3.4) ·
  **раскатка adoption-режима на 25 онбордженных проектов** (кандидат `roadmap/`, Scope Excluded фазы
  P1) · **фикстурный `provenance` P1.2** — обновление теста `test_instruction_compatibility.py` ·
  **сужение `root.codex.bootstrap`/`.launch-and-hook-integrity`** (D73, теперь видимо в живом
  `AGENTS.md:82`) · **буквальная формулировка Validation P1.4** (`-p 'test_instruction*'` не матчит
  `test_provider_instructions.py`) · **порядок-чувствительный `--authorize` у `apply_instructions`**
  (Pending Work P1.5) · **удаление pre-image'ов P1.5** — Scope Excluded держит их до закрытия фазы P1.
- open_questions: OQ-3 две capability `unsupported` у обоих провайдеров (P2.1) · OQ-6 дом логики
  Codex-обработчиков (P2.1) · OQ-7 структурный перебор бюджета обнаружения (замер P3.4) · OQ-8
  дрейф канона ролей и инсталляционного шаблона (Deferred) · OQ-9 CI не покрывает `analyst`/`task`
  (Deferred). OQ-2 закрыта D71 (вариант B), OQ-1 закрыта D31, OQ-4 закрыта D27.
