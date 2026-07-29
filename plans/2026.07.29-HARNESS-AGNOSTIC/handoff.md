# HANDOFF — 2026-07-29 — after P1.4

**Next:** ЗАПУСК ВРУЧНУЮ: frontier/high

| Параметр | Значение |
|:--|:--|
| Model class | frontier |
| Effort | high |
| Capabilities | — |
| Context | continue (/clear) — ручной item |
| Суть | P1.5 — живая транзакция: `adopt` семи `ownership-conflict` целей + `apply` пяти `missing`, гейт дрейфа `[9/9]` в `validate.sh`, замер `skiller budget --first-turn` до/после |

```
Читай, в этом порядке, НИЧЕГО СВЕРХ:
1) plans/2026.07.29-HARNESS-AGNOSTIC/plan.md — Context, Execution Rules, §3 Routing, Status Board
2) plans/2026.07.29-HARNESS-AGNOSTIC/handoff.md (этот файл)
3) plans/2026.07.29-HARNESS-AGNOSTIC/phases/P1.md — Phase Context + item P1.5 целиком
4) Required Reads item'а P1.5 в указанном порядке (research/05-instruction-canon-routing.md —
   mapping; research/04 §2/§4; packages/harness/scripts/validate.sh шаги [7/8]/[8/8];
   provider-instruction-contract.md §«Drift and repair»; plan.md §2 Execution Rules)

Единственная необратимая внутрь-репо граница до P5.2 (R1 — необратимая ЖИВАЯ транзакция на
CLAUDE.md/AGENTS.md текущего дерева). Перед стартом переведи матрицу research/05 в конкретный
mapping.json — формат `adopt()` (заведён в P1.4): `{"<target_path>": {"covered_spans":
[[start,end],...]}}`, byte-offsets в pre-image каждой из семи `ownership-conflict` целей;
контракт дословно этот формат НЕ специфицирует — он спроектирован P1.4, см. Open risks ниже.

Исполни item P1.5 СТРОГО по его Scope Included/Excluded, Implementation Rules, Code Guidance —
порядок обязателен (check ДО → adopt семи → apply пяти → check ПОСЛЕ, все 12 clean), ДВА
коммита в порядке «принятие → гейт» (D66), НЕ смешивая правки инструкций и правку гейта.
Прогони Validation item'а целиком, зафиксируй passed/failed. Закрой item штатной топологией
plan-протокола (item-коммит по Files · bookkeeping-коммит плана · перезапись handoff.md ·
plan-lint --baseline HEAD с атрибуцией K) — модель/effort ЭТОЙ сессии (frontier/high), не пин
plan-exec (sonnet/medium): Routing item'а требует `Exec = manual`, поэтому /task:plan-exec его
отклонит на гейте — закрывай сам, по протоколу (Pre-mutation/Pre-final Task Contract с
ФАКТИЧЕСКИМ маршрутом сессии, две ветки закрытия 🟢/🟠, Update Log, launch-block следующего шага).
```

**Штатный носитель исполнения** — `task:plan-run` под сессией **frontier/high** (без ритуала
`/model`+`/effort`, если уже в такой сессии), либо `/model opus` + `/effort high` +
`/task:plan-run 2026.07.29-HARNESS-AGNOSTIC P1.5`. Голая slash-команда `/task:plan-exec` СЮДА НЕ
ПОДХОДИТ: она пинит sonnet/medium, а Routing P1.5 требует frontier/high (`Exec = manual`) —
гейт п. 2 `plan-exec` отклонит запуск (`ROUTING-BLOCKED`).

**Done:** **P1.4 закрыт `🟢`** (`plan-run`/Sonnet/high — implementation/high, точное совпадение
с §3 Routing, не перебор; item-коммит `1e0262a4`). Реализован owner-gated adoption-режим в
`packages/harness/lib/harness/instructions.py`: `adopt_instructions(request, *, catalog=None)` +
convenience-обёртка `adopt(...)` — fail-closed вход (`owner_decision`, `mapping_path`,
`preimage_destination` все обязательны), отказ на цели вне `ownership-conflict`, отказ на
mapping без содержательного покрытия (`covered_spans` — новый JSON-формат, спроектирован этим
item'ом, контракт дословно формат не специфицирует), pre-image пишется атомарно и
верифицируется перечитыванием ДО мутации цели, непокрытые байты сохраняются дословно ПОСЛЕ
двух управляемых блоков, провенанс принятия — `semantic_metadata.adoption`
(`owner_decision`/`pre_image_hash`/`pre_image_path`/`mapping_path`) в P2-lock-записи.
Ключевое архитектурное решение: этот `adoption`-факт ОБЯЗАН попадать в рендер ДО вычисления
`source_hash` (через новый `adoption_hints`-параметр `_projections`/`_projection`, который
`_observe` заполняет ИЗ УЖЕ СУЩЕСТВУЮЩЕЙ lock-записи) — иначе `core.provider_lock._classify`
(frozen, вне `Files`) вечно возвращал бы `stale-source` вместо `clean` на втором прогоне
(полное равенство dataclass между записанной и заново вычисленной provenance). Найдено падением
теста идемпотентности, исправлено без правки контракта/диагностик/сигнатур публичных операций.
`rollback_adoption(root, target_path)` — путь восстановления pre-image байт-в-байт со снятием
lock-записи (не CLI-глагол — явная внепроцессная процедура восстановления). Новый CLI-глагол
`harness instructions <plan|check|adopt|apply|repair>` (`cmd_instructions`, `COMMANDS`,
case-список `bin/harness`, usage-шапка, `sed`-диапазон `2,21`→`2,25`) + модульная точка
`python3 -m harness.instructions --check` — оба пути дают идентичный вердикт на живом дереве
(смоук-тест: 7 `ownership-conflict` + 5 `missing`, `exit=1`, байт-в-байт одинаковый вывод).
Девять новых тестов в отдельном `test_instruction_adoption.py` (успешный adopt + сохранение
непокрытых байтов · отказ на не-conflict цели · отказ на пустом mapping · отказ на
mapping-только-из-whitespace · отказ без `owner_decision` · идемпотентность второго `check` ·
повторный `adopt` уже управляемой цели отказывает · rollback байт-в-байт + снятие lock-записи ·
rollback без записи адопции — fail-closed); 28 тестов `test_provider_instructions.py` и 6 тестов
`test_instruction_compatibility.py` не тронуты и зелёные.
- **Known Deviations:** — (item-коммит несёт диф СТРОГО по `Files`; `packages/harness/commands/
  harness.md` НЕ правился — прецедент flotы: `agent-packs`/`safe-dirs`/`router`/`wf` тоже не
  спроецированы в `/harness:*`-справку, эта команда не первое исключение).
- Validation: `bash packages/harness/scripts/validate.sh` — `validate: OK` (на `1e0262a4`;
  предсуществующий `harness provider audit: ERROR HARNESS_CATALOG_MISMATCH:test` подтверждён
  несвязанным, тот же прецедент, что в P1.3) · 28+9+6=43 instruction-теста зелёные · CLI/модульная
  точка `--check` — идентичный вердикт байт-в-байт · `git status --short` на живых 12 целях/lock —
  пусто · `plan-lint` — 0 ERROR, 2 WARN (оба предсуществующий ложный `[NEEDS CLARIFICATION]`).
- **Pending Work:** буквальная команда Validation `-p 'test_instruction*'` не матчит
  `test_provider_instructions.py` (имя файла не с этого префикса) — дефект формулировки ТЗ P1.4,
  не блокер (28 тестов прогнаны явно поверх шаблона); правка формулировки — не заведена отдельным
  item'ом, чинить при следующей правке `phases/P1.md`, если понадобится.

**Ранее:** P1.3 закрыта `🟠` (девять аддитивных ID канона 1.1.0 + аддендум-контракт). P1.2 закрыта
`🟠` (8/18 фрагментов канона актуализированы). P1.1 закрыта `🟢` (матрица «правило → дом»,
D72–D74). P0 закрыта целиком (4/5 🟢 + 1/5 🟠).

**Remaining:** P1.5, затем P2 (5) → P3 (6) → P4 (5) → P5 (3). Итого 20/29 items ещё не исполнено.

**Sources of truth:** `plans/2026.07.29-HARNESS-AGNOSTIC/plan.md` (§3 Routing, §5 D1–D74,
§7 Contracts, § Обсуждение 1–7, три блока `## Audit design`) · `phases/P0.md`–`P5.md` (P0 закрыта,
P1 — 2/5 🟢 + 2/5 🟠) · `research/05-instruction-canon-routing.md` (матрица «правило → дом» —
вход P1.1–P1.4 закрыт, ещё вход P1.5 — перевод матрицы в конкретный `mapping.json` формата
`adopt()`) · `research/04-instruction-mechanism-inventory.md` (механизм, G1–G5, ограничения
авторинга — G2/G3 закрыты P1.4) · `findings/02-rag-instruction-loading-2026-07-29.md` Ф7/Ф8 ·
`roadmap.md` (батч B1 закрыт; дальше всё solo) · `brief/00-brief.md` + `brief/01-refinements.md` ·
`findings/00`–`06` · `research/00`–`04`, `06`–`09` · `open-questions.md` (OQ-3, OQ-5–OQ-9 открыты) ·
`index.md` · `journal.jsonl` · `root/contracts/provider-parity-definition.md` (sealed v1) ·
`root/contracts/instruction-canon-addendum-v1.md` (sealed v1, P1.3) ·
`plans/archive/2026.07.19-DUAL-PROVIDER/root/contracts/provider-instruction-contract.md`
(frozen v1.0.0 — контракт механизма) · `plans/archive/2026.07.18-FOREMAN/` (архивирован) ·
`docs/reference.md`, `docs/rejected-optimizations.md` · `plans/README.md`.

**Open risks:**
- **`adopt()`'s `mapping.json`-формат (`covered_spans`) спроектирован в P1.4, не взят из
  контракта дословно** — контракт требует только «source-to-semantic mapping», конкретную форму
  не специфицирует. P1.5 обязан перевести матрицу `research/05` в РЕАЛЬНЫЕ `covered_spans`
  (byte-offsets) для каждой из семи `ownership-conflict` целей ПЕРЕД вызовом `adopt` — это не
  готовый входной артефакт, а работа самого P1.5.
- **Фикстурный `provenance` не отражает миграцию P1.2** (P1.2 Known Deviation) — вне Scope
  дальнейших items, если владелец захочет иное, нужен отдельный item со строкой
  `packages/harness/tests/test_instruction_compatibility.py` в `Files`.
- **Сужение `root.codex.bootstrap`/`root.codex.launch-and-hook-integrity` осталось не сделанным**
  (D73): common-ID, принимающие эти правила, теперь существуют (P1.3), но САМО сужение двух
  Codex-фрагментов — работа без явного дома ни в одном из закрытых items (P1.2/P1.3) — follow-up,
  не блокирует P1.5, но правило технически дублируется (common + extension) до починки.
- **Посторонний дифф в дереве не убран и не тронут**: `roadmap/README.md` (M) + untracked
  `roadmap/2026.07.29-launch-block-command-row.md`. Существовал до P0.2, ни в один item-коммит
  P0.1–P1.4 не попал.
- **`packages/skiller/scripts/validate.sh` на дереве КРАСНЫЙ**: `ERROR: реестр устарел
  относительно источников — прогони: skiller registry`. Предсуществующий, Known Deviation P0.5.
- **`scripts/test-provider-docs.py` на дереве КРАСНЫЙ** (1 fail из 4) — битая ссылка
  `roadmap/self-learning-memory.md` из `README.md:122`. Предсуществующая.
- **`scripts/public-hygiene.py` на дереве красный** (предсуществующая находка) — закрыть или
  объявить исключением до P5.1.
- **`--check` не зовёт ни один гейт** (D21): до P1.5 конформанс каталога держится ручным
  прогоном — P1.5 закрывает это (шаг гейта `[9/9]` в `validate.sh`).
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
  см. Pending Work выше) · **буквальная формулировка Validation P1.4** (`-p 'test_instruction*'`
  не матчит `test_provider_instructions.py`) — правка формулировки при следующем касании
  `phases/P1.md`.
- open_questions: OQ-3 две capability `unsupported` у обоих провайдеров (P2.1) · OQ-6 дом логики
  Codex-обработчиков (P2.1) · OQ-7 структурный перебор бюджета обнаружения (замер P3.4) · OQ-8
  дрейф канона ролей и инсталляционного шаблона (Deferred) · OQ-9 CI не покрывает `analyst`/`task`
  (Deferred). OQ-2 закрыта D71 (вариант B), OQ-1 закрыта D31, OQ-4 закрыта D27.
