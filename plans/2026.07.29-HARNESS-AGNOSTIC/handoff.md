# HANDOFF — 2026-07-29 — after P1.3

**Next:** ЗАПУСК ВРУЧНУЮ: implementation/high

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | high |
| Capabilities | — |
| Context | continue (/clear) — ручной item |
| Суть | P1.4 — `adopt_instructions`/`adopt(...)` (fail-closed, pre-image, semantic mapping, lock-провенанс, rollback) + CLI `harness instructions <plan\|check\|adopt\|apply\|repair>` + модульная точка `--check` |

```
Читай, в этом порядке, НИЧЕГО СВЕРХ:
1) plans/2026.07.29-HARNESS-AGNOSTIC/plan.md — Context, Execution Rules, §3 Routing, Status Board
2) plans/2026.07.29-HARNESS-AGNOSTIC/handoff.md (этот файл)
3) plans/2026.07.29-HARNESS-AGNOSTIC/phases/P1.md — Phase Context + item P1.4 целиком
4) Required Reads item'а P1.4 в указанном порядке (первый — provider-instruction-contract.md
   §«Drift and repair», §«Provenance and lock», §«Consumer API»)

Исполни item P1.4 СТРОГО по его Scope Included/Excluded, Implementation Rules, Code Guidance —
без импровизации при расхождении с деревом (эскалация вместо самостоятельной правки плана).
Прогони Validation item'а целиком, зафиксируй passed/failed. Закрой item штатной топологией
plan-протокола (item-коммит по Files · bookkeeping-коммит плана · перезапись handoff.md ·
plan-lint --baseline HEAD с атрибуцией K) — модель/effort ЭТОЙ сессии (implementation/high), не
пин plan-exec (sonnet/medium): Routing item'а требует `Exec = manual`, поэтому /task:plan-exec
его отклонит на гейте — закрывай сам, по протоколу (Pre-mutation/Pre-final Task Contract с
ФАКТИЧЕСКИМ маршрутом сессии, две ветки закрытия 🟢/🟠, Update Log, launch-block следующего шага).
```

**Штатный носитель исполнения** — `task:plan-run` под сессией **implementation/high** (без ритуала
`/model`+`/effort`, если уже в такой сессии), либо `/model sonnet` + `/effort high` +
`/task:plan-run 2026.07.29-HARNESS-AGNOSTIC P1.4`. Голая slash-команда `/task:plan-exec` СЮДА НЕ
ПОДХОДИТ: она пинит sonnet/medium, а Routing P1.4 требует effort `high` (`Exec = manual`, D39/D47) —
гейт п. 2 `plan-exec` отклонит запуск (`ROUTING-BLOCKED`).

**Done:** **P1.3 закрыт `🟠` Done with deviations** (`plan-run`/Sonnet/high — implementation/high,
совпадает с §3 Routing; item-коммит `b02e48be`). Заведены девять аддитивных семантических ID по
матрице P1.1 (D72): семь common в `root` (`root.provider-parity`, `root.worktree-safety`,
`root.untrusted-content`, `root.evidence-integrity`, `root.generated-artifacts`,
`root.speculative-work`, `root.docs-build`) и два provider-extension
(`root.codex.package-scope-routing` codex, `harness.claude-code.safe-dirs` claude-code).
`catalog_version` `1.0.1`→`1.1.0`, `contract_version` остаётся `1.0.0` (аддитивный minor, D16).
Инвентарь: 67→**76** записей (56 common + 20 extension, было 49+18); `[25, 11, 12, 9, 10, 9]` по
scope. Фрагменты `root/common.md` (+7), `root/codex.md` (+1),
`packages/harness/claude-code.md` (+1) получили новые `<!-- instruction:<id> -->` секции;
`sources[0].sha256` пересчитан для всех записей, ссылающихся на эти три файла. Фикстура
`instruction-compatibility-v1.json` → `1.1.0`, 76 записей в порядке
`COMMON_IDS + EXTENSION_IDS[claude-code] + EXTENSION_IDS[codex]` по scope; `provenance` не тронут
(тот же прецедент D14, что и P1.2). Аддендум-контракт
`root/contracts/instruction-canon-addendum-v1.md` запечатан (`type: contract`,
`status: additive-extension (P1.3)`, `version: v1`); `plan.md` §7 Exported переведён в
`sealed (P1.3)`.
- **Known Deviations:** item-коммит несёт дифф вне `Files` этого item'а — ДВА файла синхронизированы
  вслед за ростом инвентаря до 76, иначе `bash packages/harness/scripts/validate.sh` становился
  красным: (а) `packages/harness/tests/test_instruction_compatibility.py` — точный литерал
  `len(expected["records"])` `67`→`76` (только число, `provenance`-словарь не тронут); (б)
  `packages/harness/docs/reference/provider-instructions.md` — сгенерированный артефакт,
  перегенерирован через свой генератор (`operator_reference()`) ПОСЛЕ обновления
  соответствующего литерала в `instructions.py` (уже в `Files`), не правкой руками.
- Validation: `validate_catalog(load_catalog())` — `()` · `(CATALOG_VERSION,CONTRACT_VERSION) ==
  ('1.1.0','1.0.0')` — True · `bash packages/harness/scripts/validate.sh` — `validate: OK` (463
  теста зелёные; `harness provider audit: ERROR HARNESS_CATALOG_MISMATCH:test` подтверждён
  предсуществующим прогоном на дереве ДО этого item'а через `git stash`, не наш предмет) ·
  `check()` — `len(pl.actions)==12`, те же 7 `ownership-conflict` + 5 `missing` · addendum `test -f`
  — passed · `plan-lint` — 0 ERROR, 2 WARN (оба предсуществующий ложный
  `[NEEDS CLARIFICATION]`-детект).
- **Pending Work:** сужение `root.codex.bootstrap`/`root.codex.launch-and-hook-integrity` до
  Codex-специфичной части (правило теперь дублируется в новых common-ID) остаётся follow-up P1.2
  (уже закрыт `🟠`) — не Scope Included P1.3. Дом: отдельная правка `root/codex.md` +
  `catalog.json` (не заведена этим item'ом, не блокирует P1.4/P1.5).

**Ранее:** P1.1 закрыта `🟢` (матрица «правило → дом», D72–D74). P1.2 закрыта `🟠` (8/18
фрагментов канона актуализированы). P0 закрыта целиком (4/5 🟢 + 1/5 🟠).

**Remaining:** P1.4 → P1.5, затем P2 (5) → P3 (6) → P4 (5) → P5 (3). Итого 21/29 items ещё не
исполнено.

**Sources of truth:** `plans/2026.07.29-HARNESS-AGNOSTIC/plan.md` (§3 Routing, §5 D1–D74,
§7 Contracts, § Обсуждение 1–7, три блока `## Audit design`) · `phases/P0.md`–`P5.md` (P0 закрыта,
P1 — 1/5 🟢 + 2/5 🟠) · `research/05-instruction-canon-routing.md` (матрица «правило → дом» — вход
P1.3 закрыт, ещё вход P1.4 и P1.5) · `research/04-instruction-mechanism-inventory.md` (механизм,
G1–G5, ограничения авторинга) · `findings/02-rag-instruction-loading-2026-07-29.md` Ф7/Ф8 ·
`roadmap.md` (батч B1 закрыт; дальше всё solo) · `brief/00-brief.md` + `brief/01-refinements.md` ·
`findings/00`–`06` · `research/00`–`04`, `06`–`09` · `open-questions.md` (OQ-3, OQ-5–OQ-9 открыты) ·
`index.md` · `journal.jsonl` · `root/contracts/provider-parity-definition.md` (sealed v1) ·
`root/contracts/instruction-canon-addendum-v1.md` (sealed v1, P1.3) ·
`plans/archive/2026.07.19-DUAL-PROVIDER/root/contracts/provider-instruction-contract.md`
(frozen v1.0.0 — контракт механизма) · `plans/archive/2026.07.18-FOREMAN/` (архивирован) ·
`docs/reference.md`, `docs/rejected-optimizations.md` · `plans/README.md`.

**Open risks:**
- **Фикстурный `provenance` не отражает миграцию P1.2** (P1.2 Known Deviation) — вне Scope
  дальнейших items, если владелец захочет иное, нужен отдельный item со строкой
  `packages/harness/tests/test_instruction_compatibility.py` в `Files`.
- **Сужение `root.codex.bootstrap`/`root.codex.launch-and-hook-integrity` осталось не сделанным**
  (D73): common-ID, принимающие эти правила, теперь существуют (P1.3), но САМО сужение двух
  Codex-фрагментов — работа без явного дома ни в одном из закрытых items (P1.2/P1.3) — follow-up,
  не блокирует P1.4/P1.5, но правило технически дублируется (common + extension) до починки.
- **Правило `CHANGELOG.md`** (D55) доехало в канон в P1.2 (`root.development-validation`) —
  закрыто, снято из рисков.
- **Посторонний дифф в дереве не убран и не тронут**: `roadmap/README.md` (M) + untracked
  `roadmap/2026.07.29-launch-block-command-row.md`. Существовал до P0.2, ни в один item-коммит
  P0.1–P1.3 не попал.
- **`packages/skiller/scripts/validate.sh` на дереве КРАСНЫЙ**: `ERROR: реестр устарел
  относительно источников — прогони: skiller registry`. Предсуществующий, Known Deviation P0.5.
- **`scripts/test-provider-docs.py` на дереве КРАСНЫЙ** (1 fail из 4) — битая ссылка
  `roadmap/self-learning-memory.md` из `README.md:122`. Предсуществующая.
- **`scripts/public-hygiene.py` на дереве красный** (предсуществующая находка) — закрыть или
  объявить исключением до P5.1.
- **`--check` не зовёт ни один гейт** (D21): до P2.5 конформанс каталога держится ручным прогоном.
- **`harness doctor --provider-audit` печатает `HARNESS_CATALOG_MISMATCH:test`** — предсуществующий
  неблокирующий диагностический вывод несвязанного `profile-catalog.json`/MCP/roles-аудита
  (подтверждено идентичным на дереве ДО P1.3 через `git stash`); не гейтит `validate: OK`; вне
  предмета этого плана (инструкции — отдельный каталог/валидатор).
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
  захочет (см. Open risks) · **сужение `root.codex.bootstrap`/`.launch-and-hook-integrity`** (D73,
  см. Pending Work выше).
- open_questions: OQ-3 две capability `unsupported` у обоих провайдеров (P2.1) · OQ-6 дом логики
  Codex-обработчиков (P2.1) · OQ-7 структурный перебор бюджета обнаружения (замер P3.4) · OQ-8
  дрейф канона ролей и инсталляционного шаблона (Deferred) · OQ-9 CI не покрывает `analyst`/`task`
  (Deferred). OQ-2 закрыта D71 (вариант B), OQ-1 закрыта D31, OQ-4 закрыта D27.
