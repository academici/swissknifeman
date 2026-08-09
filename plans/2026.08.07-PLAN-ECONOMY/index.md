# Карта плана 2026.08.07-PLAN-ECONOMY

Что где лежит и откуда взялось. Провенанс слоёв знаний → фаза-потребитель.

## Носители

| Файл | Роль |
|:--|:--|
| `plan.md` | Stable Meta, Context, Execution Rules, Routing, pointer to decision catalog and Contracts (Layout v2) |
| `status.md` | Generated owner view: volatile Meta, phase board and journal-derived Update Log |
| `handoff.md` | Где мы; вход холодного старта; launch-block следующего шага |
| `phases/Pn/Pn.md` + `Pn.m.md`/`Pn.m.state.md` | Thin phase indices, handwritten specifications and generated item state (Layout v2) |
| `decisions/` | Immutable D-records and generated navigation views |
| `roadmap.md` | Исполнительская карта 47 items: батчи B1/B2, 44 `manual`-item, три `plan-exec`; P5 повторно реоткрыта D146 по существующим владельцам P5.4/P5.5 без нового item |
| `journal.jsonl` | Append-only лог исполнения |
| `open-questions.md` | Открытых нет; закрыты OQ-1–OQ-6 |
| `root/contracts/` | Замороженные контракты плана; судьба — docs проекта |
| `artifacts/` | Рабочие артефакты фаз (дампы замеров, реконструкции); судьба — архив |
| `artifacts/p2-migration-inventory.json` | Generated 1,053-element lossless migration inventory |
| `artifacts/p2-weight-before-after.json` | Generated per-item before/after baseline; четыре D2(a) и дополнительные D2(b)/producer gaps адресованы D131 → P2.9/P2.10 |
| `findings/21-p2.8-read-admission-diagnosis-2026-08-08.md` | Repo-grounded correction первого P2.8 verdict: полный класс D2(a)/D2(b)/future-producer failures |
| `research/20-p2.8-stage-aware-admission-redesign.md` | Stage-aware модель, декомпозиция P2.8–P2.10, alternatives и pre-mortem |
| `findings/13-design-audit-2026-08-07.md` | ЧЕТЫРЕ захода `plan-audit design`: 1 RED F1–F12 → D84–D95; 2 RED N1–N11 → D96–D104; 3 ATTENTION A1/A2 → D105–D106; 4 RED F4.1–F4.4 → owning-root remediation D126, новый audit не назначен |

Всего items: 47 (P0 5 · P1 5 · P2 10 · P3 7 · P4 6 · P5 5 · P6 9).

## Слои знаний → кто потребляет

| Файл | Слой | Что несёт | Потребляют фазы |
|:--|:--|:--|:--|
| `brief/00-brief.md` | 0 | Бриф владельца 2026-08-07 без потери мыслей; три исполненных распоряжения | все |
| `brief/01-refinements.md` | 0 | Уточнения владельца, включая узкий реопен P4 по §3: event-scoped judgement, полный owner packet, воспроизводимая item-tree acceptance и reconciliation границ P4.2/P4.4 при сохранении frozen contracts | P0, P1, P2, P4, P5, P6 |
| `brief/02-p5-audit-reopen-2026-08-09.md` | 0 | Вызов владельца на четырёхшаговый реопен P5 после RED-аудита: fail-closed ingress/outcomes/views и producer-based item-tree acceptance при неизменных frozen contracts | P5.4, P5.5 |
| `brief/03-p5-audit-reopen-round2-2026-08-09.md` | 0 | Повторный четырёхшаговый реопен P5 после RED-аудита захода 2: единый semantic outcome, substantive bounds, exact retry и расширенная producer/error acceptance | P5.4, P5.5 |
| `findings/00-plan-read-weight-2026-08-07.md` | 1 | Машинный замер 24 планов флота: пол 12к–254к токенов, разбор `plan.md` по секциям, 153 КБ фазовый файл, слепой линтер, дефект корректности при лимите ~25к | P0, P1, P3 |
| `findings/01-rag-context-engineering-2026-08-07.md` | 1 | Шесть внешних запросов: R1 JIT-раскрытие и context rot · R2 раскладки spec-kit/Kiro/Tessl/AGENTS.md · R3 ADR «файл на решение + генерируемые виды» · R4 проекции и снапшоты event sourcing · R5 отрицательный результат по детекции повторной причины · R6 безлюдные решения | P1, P2, P3, P4, P5 |
| `findings/02-prompt-caching-economics-2026-08-07.md` | 1 | Множители кэша, правило точного префикса, минимальный кэшируемый префикс, 20-блочное окно; пересмотр обоснования | P1, P3 (правило порядка), D8 |
| `findings/03-token-counting-api-2026-08-07.md` | 1 | Как честно считать токены Claude: привязка счёта к семейству модели, `tiktoken` занижает на ~15–20%, локального токенизатора Claude не существует, смена поколения даёт до ~1.35×. **Вывод «только `count_tokens`» ОТМЕНЁН D92** — якорь калибровки перенесён на дифференциальный замер по `usage` транскриптов Claude Code; действующее основание канала — `findings/14-…` R21–R23 | P0 |
| `findings/05-generated-regions-2026-08-07.md` | 1 | R7: managed-регионы внутри рукописных файлов — контракт маркеров, fail-closed политика, именованные прецеденты; дефолт «сначала отдельные генерируемые файлы»; свежесть проверяется регенерацией, не хешем | P1, P2 |
| `research/00-user-intent.md` | 2 | Трассировка 19 мыслей владельца → фазы/D#; и мысли, которые вынуждены появиться | DoR всех фаз |
| `research/01-target-architecture.md` | 2 | Три читателя, источник истины против производных, целевая раскладка, бюджет как гейт, ограничитель кружения, протокол решений, вывод порядка фаз | все |
| `research/02-p0-measurement-design.md` | 2 | Форма оценки сверху и протокол калибровки, процедура зонда лимита, определение веса и таксономия пробелов, дисциплина выбора порога, pre-mortem P0 | P0 |
| `research/03-p1-reader-contract-design.md` | 2 | Четыре читателя и их права, реестр носителей и классы, форма слепка, входное объявление истории, слоты пути и предикат порядка, дисциплина заморозки, pre-mortem P1 из 8 причин | P1, вход P2/P3 |
| `findings/08-gates-and-manifests-2026-08-07.md` | 1 | R8 lock-файл: два утверждения (свежесть против целостности), пересчёт дайджестов, таксономия отказов, режимы отказа коммитнутого манифеста · R9 храповые гейты: три модели раскатки, честная граница тезиса «гейт выключат», защищённое объявление области · R10 гейт потребителя: записанные ожидания, механическое обнаружение, pending/unknown, ключ результата | P3 |
| `research/05-p3-gate-design.md` | 2 | Реконсиль контракт-блока P3, форма bundle и таксономия отказов, дисциплина раскатки гейта, семьи проверок, непрерывность через реестр диспозиций, перенос гейта потребителя, вывод семи items, pre-mortem P3 из 8 причин | P3, вход P6 |
| `findings/09-fingerprinting-and-judges-2026-08-07.md` | 1 | R11 отпечаток причины отказа: идентичность от ШВА а не от текста, версионированный кортеж рядом с хешем, закрытые списки включаемого и исключаемого, «unknown — не группа» и три пространства имён, «ложное слияние дороже ложного разделения», слоистые идентичности · R12 вердикт модели в детерминированной петле: судья-сенсор без полномочий действия, закрытый enum с первоклассным воздержанием, «необходимо но никогда не достаточно», провенанс и три исхода воспроизведения, шесть режимов отказа судьи | P4 |
| `research/06-p4-loop-limiter-design.md` | 2 | Реконсиль контракт-блока P4, ИЗМЕРЕНИЕ корпуса журналов (10 планов, 1109 записей, 87 возвратов, 8 субъектов выше потолка), предикат возврата и форма отпечатка, три пространства имён и метрики, потолок и владельческий гейт с ортогональностью существующим счётчикам, монотонность вердикта и запреты, двусоставная приёмка с честной границей, pre-mortem P4 из 9 причин | P4, вход P5/P6 |
| `findings/10-decision-policy-and-authority-2026-08-07.md` | 1 | R13 детерминированный движок политики: закрытый мир и default-deny, deny-overrides, воспроизводимая запись с пинованными дайджестами политики и данных, утечка семантики «нет совпадения → allow» в адаптере, shadow-режим · R14 рамка делегирования как deny-by-default программа классов решений: остаточное владельцу, агрегация против дробления, монотонное сужение, «что одобрено — то и исполняется», инвалидация при перепланировании, lease/claim · R15 допустимость дефолта по таймауту по классам решений · R16 уточнение против апрува: закрытый allowlist автоответов, провенанс системы-записи, ПЕРЕКЛАССИФИКАЦИЯ после ответа, аудит автоответа, Lies-in-the-Loop | P5 |
| `findings/14-calibration-and-canon-budget-2026-08-07.md` | 1 | R21 `count_tokens`: бесплатен, собственные RPM-лимиты, но требует учётных данных Console · R22 подписка Pro/Max доступа к Console/API не даёт, её OAuth-токен делает только запросы модели · R23 настоящий токенизатор доступен без ключа через `usage` транскриптов Claude Code (сумма трёх входных полей), с четырьмя названными ограничениями · R24 бюджет документа-инструкции агента: вендорские 500 строк `SKILL.md`, двухпороговый CI-гейт, датированное исключение, вред правила «no growth ever» | P0, P6 |
| `findings/17-p0.1-claude-auth-blocker-2026-08-08.md` | 1 | Историческое evidence остановленного Claude-прогона; blocker superseded D118 и больше не стоит на critical path | История P0.1 |
| `findings/18-codex-token-usage-2026-08-08.md` | 1 | Официальный JSONL contract Codex + локальный probe 0.147.0: exactly-one `turn.completed`, canonical `usage.input_tokens`, cache breakdown не суммируется повторно, isolation flags | P0.1, вход P0.5/P3 |
| `findings/19-session-continuity-and-adaptive-review-2026-08-08.md` | 1 | R23 manager сохраняет control при nested specialist; R24 отдельный контекст окупается выборочно; R25 внешний источник не задаёт численный cap | P1, P4, P5, P6 |
| `research/09-finish-round3-design-2026-08-07.md` | 2 | Синтез закрытия находок аудита F1–F12: три шва перевода компилятора контракта и таблица потребителей раскладки, машинный пересчёт поверхности связности с процедурой, протокол дифференциальной калибровки без ключа, форма двухпорогового гейта веса канона, бухгалтерия прогонов и источник `session_id` | P0, P1, P2, P6 |
| `research/10-finish-round4-design-2026-08-07.md` | 2 | Синтез закрытия находок аудита захода 2 (N1–N11): четыре носителя раскладки в двух модулях и разбор владельца правки `journal.py`, пересчёт поверхности связности с условием на полноту входа `Files`, что означает `--exact` после D92, машинный критерий `unresolvable_entry` и 25 раскрытых позиций, бухгалтерия прогона 4 и что заход НЕ доказывает | P0, P2, P3, P4, P5, P6 |
| `research/11-finish-round5-design-2026-08-07.md` | 2 | Синтез узкого закрытия находок захода 3 (A1/A2): три точки опоры `plan_reader` на раскладку и назначение источника формы `Next` под v2, сверка якорей §8 контракта драйвера, машинный пересчёт поверхности связности после нормализации поля `Files` | P2.1 |
| `research/14-p0.1-dense-ascii-reopen-2026-08-08.md` | 2 | Dense-класс, реальный корпус и сохранность v1; Claude-specific active channel superseded D118/research 15 | P0, вход P3 |
| `research/15-p0.1-provider-neutral-calibration-2026-08-08.md` | 2 | Трёхслойная архитектура adapter → neutral bracket-control core → qualified artifact consumer; active Codex adapter, deferred Claude adapter, schema/invariants/tests | P0.1, вход P0.5/P3 |
| `research/16-multiprovider-field-loop-2026-08-08.md` | 2 | Сквозная модель shared contract + independent provider certification; закрытая минимальная provider-surface; bounded calibration и ранний field loop | все фазы, особенно P0.1/P2.8/P3.7/P6 |
| `research/17-session-continuity-adaptive-review-2026-08-08.md` | 2 | Лестница local-fix → isolated-review → owner-gate, три независимые оси context/model/control, scoped-review capsule, распределение по P1/P4/P5/P6 и canary-инварианты | P1, P4, P5, P6 |
| `research/18-audit-red-remediation-2026-08-08.md` | 2 | Закрытие F4.1–F4.4: machine `session_canary`, exact P6.8 comparator, DoR/roadmap reconcile, продолжение P1.5 без пятого аудита | P1, P4, P5, P6 |
| `research/07-p5-decision-protocol-design.md` | 2 | Реконсиль контракт-блока P5 (четыре расхождения), два вида решения и механизм закрытия обхода, рамка как программа и машинная форма D13-а с агрегацией, определение «ветки» через субъект и фазовый join, форма запроса и ответа поле за полем, что сознательно не переносится, носители очереди и расширение реестра, запреты содержимого записи, вывод пяти items, pre-mortem P5 из 10 причин | P5, вход P6 |
| `research/04-p2-carriers-design.md` | 2 | Две раскладки и их адресация, таблица носителей v2, форма записи решения и четыре вида, расщепление 16 полей пункта, ядро против владельческого вида, каркас проекций, терминальная фаза, self-hosting с инвентарём и приёмочным замером, pre-mortem P2 из 8 причин | P2, вход P3/P6 |
| `findings/21-p2.8-read-admission-diagnosis-2026-08-08.md` | 1 | Field correction: четыре D2(a) недостаточны, есть oversized/unresolved/future producer classes D2(b) | P2.8–P2.10, вход P3.3 |
| `research/20-p2.8-stage-aware-admission-redesign.md` | 2 | Три admission states, декомпозиция migration→machine semantics→self-host proof, alternatives и pre-mortem | P2.8–P2.10, вход P3.3 |
| `research/21-p4-audit-reopen-2026-08-08.md` | 2 | Repo-grounded синтез Audit P4: plan-local `return_event_id`, event-scoped reducer и полный packet, непротиворечивая gate matrix, item-tree acceptance, reconciliation P4.2 fixture/P4.4 `engine.py`; D142, без нового P4.7 | P4.2, P4.4, P4.6 |
| `research/22-p5-audit-reopen-2026-08-09.md` | 2 | Repo-grounded синтез Audit P5: contract-driven request/response/auto-answer ingress, outcome→state/continuation matrix, единая regeneration boundary и producer-based detached-tree acceptance; D144, без расфриза P5.1/P5.2 | P5.4, P5.5 |
| `research/23-p5-audit-reopen-round2-2026-08-09.md` | 2 | Repo-grounded синтез Audit P5 захода 2: один semantic reducer во всех consumers, substantive bounds отдельно от mandatory, idempotent exact retry и differentiating RED→green acceptance; D146 | P5.4, P5.5 |

| `findings/11-rollout-and-acceptance-2026-08-07.md` | 1 | R17 включение построенной выключенной проверки (порядок, негативный e2e, флаг-долг, курица-яйцо) · R18 рубрика судьи (форма, смещения, версионирование промпта как провенанс, калибровка) · R19 раскатка версионированного канона по флоту (semantic split-brain, анти-дрейф прозы и спеки, вывод старой прозы, маленький вход) · R20 честная приёмка на своём экземпляре (векторы Гудхарта, пред-регистрация, границы dogfooding, две руки) | P6 |
| `research/08-p6-rollout-design.md` | 2 | Пятый реконсиль контракт-блока P6, разрешение конфликта D43 с «режимом оценки», три класса правки команд, носитель и калибровка рубрики, EN-only переход и три гейта канона, наблюдаемость раскатки, предобъявленная двурукая приёмка с антисмещением, снятие паузы ARTIFEX, вывод девяти items, pre-mortem P6 из 13 причин | P6 |

Зарезервированные имена будущих слоёв: `findings/04-fleet-read-weight-machine.md` (Deliverable P0.4) ·
`findings/06-p1-path-feasibility.md` (Deliverable P1.5) · `findings/07-p2-selfhosting-measurement.md` (Deliverable P2.8) ·
`findings/12-p6-acceptance-measurement.md` (Deliverable P6.8 — отчёт двурукой приёмки; он же `Inputs`/`Required Reads` последнего item'а плана P6.9).
Артефакты P4: `artifacts/P4/measure_returns.py` + `returns-baseline.json` (Deliverables P4.2) ·
`artifacts/P4/historical-detect.json` + `acceptance-report.md` + `validate_acceptance.py` (Deliverables P4.6; обязаны входить в item tree P4.6).
Артефакты P5: `artifacts/P5/validate_acceptance.py` + `acceptance-results-v2.json` +
`acceptance-report.md` (D144 Deliverables P5.5; validator/results/report обязаны входить в item tree).
Артефакты P6: `artifacts/P6/{provider-certification.md,would-fail-*.txt,judge-calibration-bank.jsonl,judge-calibration-report.md,canon-weight-before-after.json,rollout-dry-run.txt,fleet-adoption-inventory.{json,md},acceptance-arm-a-migrated.json,acceptance-arm-b-fresh.json,session-canary-results.json}` · `findings/12-p6-acceptance-measurement.md` (Deliverable P6.8) · контракт `root/contracts/acceptance-protocol-v1.{md,manifest.json}` с machine `session_canary` (Deliverable P6.7).

## Внешние зависимости плана

| Что | Откуда | Зачем |
|:--|:--|:--|
| Классы полномочий AUTO / AUTO-FIX / OWNER и классы внимания | `plans/2026.08.03-ARTIFEX-SUPERVISOR/root/contracts/authority-policy-v1.md` (заморожен, донор на паузе) | P5 строит рамку поверх них, не изобретая второй словарь власти (D6); P4 заимствует классы для гейта кружения БЕЗ расширения закрытых множеств (D53) |
| Идентичность находки (шов `file` × `rule_or_contract_locus` × `defect_class`) и дисциплина durable-счётчика | `packages/task/lib/task/review_policy.py` (`finding_id`, `LoopBudget.from_committed`) | P4 переиспользует вокабуляр шва дословно и повторяет честный `unknown`, не чеканя второй словарь идентичности (D52) |
| Схема журнала | `packages/task/lib/task/journal.py` (запечатана планом `2026.07.18-FOREMAN` P1.1) | P1.3 сверяет входное объявление истории поле за полем; схема НЕ меняется (D24); P4 читает факты |
| Определение обязательного пути чтения | `packages/task/commands/plan-exec.md` §1 | P0.3 воспроизводит сегодняшний путь как базу замера; P1.4 заменяет его машинной спецификацией (D25); P6.1 переводит команды |
| Точка гейта | `packages/task/scripts/plan-lint.py`, `packages/task/lib/task/plan_lint.py` | P2 учит линтер раскладке v2 (без новых требований), P3 встраивает три проверки |
| Раздача скилла | `packages/skiller/skills/general/plan-protocol/` | P6.5 приводит канон к v2 в EN-only модели (RU-источники удаляются, гейты перепривязываются), P6.6 раскатывает по флоту с инвентарём адопции |
| Решение об английском как языке-источнике | `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE` (на паузе) | P6.5 исполняет удаление RU-носителей и перепривязку гейтов; контракт локали и компактификация 229 чужих канонов остаются донору (D79) |
