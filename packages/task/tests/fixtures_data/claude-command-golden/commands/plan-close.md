---
description: "План-протокол: recovery-сверка item Pn.m, адаптивное закрытие phase candidate Pn либо архив терминального плана. Пинит Sonnet/low."
argument-hint: "<PLAN-ID> Pn[.m] | archive <PLAN-ID>"
model: sonnet
effort: low
---
Это РЕКОНСИЛЯЦИЯ/ЗАКРЫТИЕ по plan-протоколу. Ввод пользователя: «$ARGUMENTS».
Модель/effort запинены (Sonnet/low — механическая сверка, thinking тут жжёт токены без
пользы) — не переключай вручную. SSOT схем/статусов — скилл `plan-protocol`.
Статусы — 6 канонических строк байт-в-байт; правки статусов ТОЛЬКО по фактам.

## Repair evidence

For every forward repair record, preserve `repair-decision/v1`, its digest, affected paths and
pre/post carriers in the append-only journal. A qualified `repair-in-current-attempt` record cannot
close, block, escalate, or emit a redesign handoff until its exact original carrier is rerun.

## DecisionRequest и isolated-child-return (P6.3)

Свободная проза не является каналом уточнения или авторизации. Когда дальнейший шаг требует
недостающего факта либо права действия, команда строит transient action по
`decision-request` v1, передаёт его единственному резолверу `task.plan_authority.authorize()` и
исполняет закрытый исход: `delegated` — продолжить только exact canonical action;
`approval_required` — материализовать `DecisionRequest` через `plan-decisions.py request` и
припарковать subject; `denied` — записать отказ и остановиться. Durable request всегда несёт
continuation identity, timeout из authority frame и объявленные варианты `escalate`/`reject`.
Уточнение авторазрешимо только закрытым allowlist систем-записей с provenance; после ответа intent
канонизируется и классифицируется заново. Модельная память, чат и свободный текст не дают approval.

Модельное суждение выполняется только как provider-neutral `isolated-child-return`: после risk
trigger либо повторного durable fingerprint root строит закрытый capsule `return-judgement` v1,
проверяет capability, независимо выбирает свежего reviewer с actor/context, отличными от executor,
и делает ровно один вызов. Full parent transcript, unrelated history, self-review и второй sample
запрещены. Capability absence даёт `cold-start-root: capability-missing`. Reviewer применяет
неизменяемый ассет `return-judgement@1.0.0`
(`packages/task/prompts/return-judgement-rubric-v1.md`,
SHA-256 `63323e5565fa2c321354e36ebe47624f37f86c3c3372ba01efaedcc61b6c2e1e`); root валидирует schema,
передаёт запись детерминированному reducer и продолжает исходный run. Неоткалиброванная пара
`model_id × rubric_sha256` и order-sensitive swap трактуются как `INSUFFICIENT_EVIDENCE`.
Raw provider flags допустимы только в additive adapter/projection.

## Continue-first block gate (v1)

<!-- block-confirmation:v1:begin -->
`block-confirmation/v1` выполняется одной закрытой последовательностью:

1. Root минимально воспроизводит signal и пишет nonterminal `local-repair` либо
   `block-candidate`; observation не меняет status/attempt.
2. Root строит immutable `block-candidate/v1` capsule и material fingerprint. До review он
   сопоставляет finding с `Scope Included`/Implementation Rules и заполняет
   `scope_coverage=in-scope|outside-scope|unknown` плюс concrete `boundary_evidence`. Broad
   inventory, число файлов/errors и длительность не являются boundary. `acceptance-failure` с
   `scope_coverage=in-scope` всегда возвращается в decomposition/local repair в том же attempt,
   даже если reviewer считает объём большим. Для external
   candidate до review обязательны `rag.status=verified` и непустые evidence IDs формы
   `rag:perplexity:sha256:<64 lowercase hex>`; empty/unavailable/pending/fallback-only пишет
   `rag-pending` и возвращает `gather-rag` без reviewer.
3. На один свежий fingerprint вызывается ровно один fresh reviewer с actor/context, отличными
   от executor, в `isolated-child-return`; тот же fingerprint переиспользует записанный review,
   второй reviewer разрешён только после доказанного material fingerprint change.
4. Reviewer получает только immutable capsule/evidence, применяет
   `block-confirmation-rubric-v1` и возвращает закрытый object
   `reviewer_actor/context/verdict/evidence_ids`, где verdict — ровно `JUSTIFIED`, `AVOIDABLE`,
   `INSUFFICIENT_EVIDENCE`, `OUT_OF_SCOPE` или `MALFORMED`.
5. Root валидирует capsule и review, затем единожды вызывает `task.plan_blocking.evaluate()`;
   reviewer даёт evidence, но не authorization.
6. Только reducer action `terminal-block` после distinct `JUSTIFIED` разрешает terminal
   `blocked`/`escalated`. `AVOIDABLE` продолжает local repair, `INSUFFICIENT_EVIDENCE` — сбор
   evidence, `OUT_OF_SCOPE`/`MALFORMED` — repair capsule. Прямой append terminal event без
   reducer outcome запрещён.
<!-- block-confirmation:v1:end -->

Недоступное или не верифицируемое route evidence до product journal start обозначай
`ROUTE-UNVERIFIABLE`: это `routing-rejected`, не attempt и не transition статуса. Верни exact
fresh-launch continuation, а после корректного запуска повтори исходный route gate; не подменяй
evidence конфигом, актором или свободным текстом.

## Путь чтения по объявленной раскладке

Сначала прочитай поле `Layout` в `## 0. Meta`; исполняется только явный `Layout | v2`
(отсутствующий или `v1` возвращает `PLAN_LAYOUT_V1_RETIRED`). РОВНО пять обязательных слотов:

1. `plans/<PLAN-ID>/plan.md` — identity, Context, Execution Rules и §3 Routing;
2. `plans/<PLAN-ID>/phases/<Pn>/<Pn>.md` — только Phase Context;
3. `plans/<PLAN-ID>/phases/<Pn>/<Pn.m>.md` — полное ТЗ выбранного item;
4. `plans/<PLAN-ID>/bundles/<Pn.m>.json` — объявленные digest-qualified inputs;
5. `plans/<PLAN-ID>/phases/<Pn>/<Pn.m>.state.md` — byte-fresh item state.

В v2 `handoff.md` НЕ входит в обязательный путь: состояние выбранного item берётся только из
fresh item state. Повторное чтение запрещено.

**Layout v2 — производство закрытия (P6.2).** После journal append закрывающая команда
регенерирует `state`, `status`, `decisions`, `closure` и `bundle` через `plan-views.py`, а затем
проверяет каждый применимый вид с `--check`; она не дописывает output-поля в стабильный item-spec.
Для terminal producer она запускает `plan-downstream.py --record` на item-коммите: исходы
`green`/`red`/`unknown` все оставляют item-scoped record, связанный парой consumer-spec SHA-256 и
producer commit; `red` блокирует закрытие. Terminal escalation получает return-evidence с одним из
`new`/`repeat`/`unqualifiable`, без схлопывания последнего в `new`. `closure/<Pn>.json` существует
только при `Closure Protocol | v1`, а `<Pn>.closed.md` всегда генерируется как отдельный read-model.

**Правила handoff.Next (любой режим, записывающий handoff):**
- **Заголовок — ДВЕ формы** (иная = ERROR `plan-lint`, D30): `# HANDOFF — <ISO-дата> —
  after Pn.m` — закрыт item; `# HANDOFF — <ISO-дата> — after Pn` — закрыта/проаудирована/
  ре-дизайнена ФАЗА (режим `Pn` этой команды пишет РОВНО эту форму).
- **Форма `Next` — закрытый enum из 8**, объявляется **ПЕРВОЙ непустой строкой поля**
  (D40; иная форма/порядок = ERROR `plan-lint`):
  | Форма Next | Когда |
  |:--|:--|
  | `/task:plan-exec <ID> Pn.m` | следующий item детализирован, `Exec = plan-exec` (§9) |
  | `/task:plan-design <ID> Pn` | следующая фаза — скелет |
  | `/task:plan-design <ID> Pn.m` | item эскалирован (🔴) либо требует ре-дизайна |
  | `/task:plan-audit <ID> Pn` | `phase_audit_policy` требует audit для terminal phase candidate |
  | `/task:plan-close <ID> Pn` | policy разрешает direct close либо fresh GREEN audit совпадает с candidate fingerprint |
  | `/task:plan-close <ID> Pn.m` | только recovery legacy/incomplete journal/evidence mismatch; не normal Next |
  | `/task:plan-close archive <ID>` | план терминален целиком |
  | «план закрыт» | все items терминальны, следующий шаг вне протокола |
  | «ЗАПУСК ВРУЧНУЮ: `<model/effort>`» | `Exec = manual` (§9): команды нет — launch-block несёт
  предписанную модель и голый промпт item'а отдельным code-block (либо `/model`+`/effort`+`/task:plan-run <ID> Pn.m`, D18) |
- **Launch-block ОБЯЗАТЕЛЕН**: таблица `Batch / Model / Thinking / Context / Суть` не несёт
  команду. Сразу после неё ОБЯЗАТЕЛЕН отдельный fenced code-block с provider-native командой
  активного адаптера; у `Exec = manual` он несёт голый промпт item'а либо
  `/model`+`/effort`+`/task:plan-run <ID> Pn.m`, D18. Команда предпочтительно занимает одну
  физическую строку; намеренный shell-перенос использует `\` на каждой продолжаемой строке;
  самодостаточна из холодной сессии — plan-ID + cold-start reads, «эта сессия» —
  только как дополнение. Скелет — `snippets/launch-block-template.md` скилла `plan-protocol`.
- **`Context` — РОВНО одно из трёх layout-v2 значений** (§6): `continue-root` ·
  `isolated-child-return` · `cold-start-root` с одной declared reason. Обычная последовательность,
  локальная repair и phase close используют `continue-root`; имя команды не требует новой сессии.
- **Один controller:** перед записью Context собери `task.plan_continuity.WorkEstimate`, вызови
  `task.plan_continuity.reduce()` и передай тот же typed decision в renderer. Delivery receipt и
  lint только проверяют сохранённый outcome/reason; они не выбирают новую сессию повторно.
- **Сверка с Execution Rules плана**: команда в Next не должна противоречить
  `## 2. Execution Rules` — план запрещает `/task:plan-exec` (программный план) →
  Next обязан указывать предписанную планом команду запуска делегатов, не plan-exec
  (инцидент FLEX-IMPL: handoff слал исполнителя на запрещённую команду).

**Pre-final — Task Contract (P2.7/P2.11, ОБЯЗАТЕЛЬНЫЙ шаг).** Шаг 4 режима `Pn.m` ниже собирает и
проверяет Task Contract v1 через `packages/task/lib/task/task_contract.py` (`task-contract-v1.md`
§Pre-mutation predicate + §Pre-final predicate) ДО вердикта — компилятор владеет hash/precedence/
portability/evidence логикой, эта команда его ЗОВЁТ безусловно, а не пересказывает. **Гейт
БИНАРЕН:** зелёное — РОВНО `pre_mutation == "allow"` И `pre_final == "allow"`; `n/a` — НЕ зелёное
(D76: «сессия заблокирована, объявлять сдачу нечего»). Маршрут `actual_route` на этой границе —
маршрут ИСПОЛНИТЕЛЯ item'а (D75), не пин этой команды. `pre_final` утверждает свойство ФОРМЫ
спеки item'а, а не то, что item исполнен хорошо (D77) — вердикт material/process остаётся за
status-rule ниже. Точная команда, лестница маршрута и таблица код→действие — в самом шаге 4.

## Режим `Pn.m` — реконсиляция item'а

1. Прочитай `plans/<PLAN-ID>/plan.md` (Status Board) и item Pn.m в `phases/Pn.md`.
2. Сверь заявленное с git-фактами: `git log --oneline -- <Files item'а>` ·
   `git diff <до>..<после> -- <Files>` — правки реально есть и соответствуют Scope Included?
3. Прогони команды из **Validation** item'а, зафиксируй результат.
4. **Pre-final — Task Contract, ОБЯЗАТЕЛЬНЫЙ шаг, не условный.** ДО вердикта — собери и
   проверь контракт тем же Python API, что `plan-exec.md`'s pre-mutation/pre-final (CLI-форма
   `check` не годится по той же причине — `route.actual` неразрешён по конструкции, флага на
   живой route у `build` нет).

   **Маршрут `actual_route` — маршрут ИСПОЛНИТЕЛЯ item'а, лестница D75, fail-closed:**
   1. Строка routing-adherence в **Completion Notes** закрываемого item'а (`phases/Pn.md`) —
      носитель КЛАССА и effort'а (`plan-protocol` §9 уже обязывает исполнителя `plan-run`
      печатать фактическую пару «класс, effort» в отчёте и Update Log). Основной источник.
   2. Терминальная запись `journal.jsonl` этого item'а — `actor` = `<model>/<effort>` (D72:
      модель, не класс). Перекрёстная сверка: effort обязан совпасть с п.1; модель обязана
      отображаться в заявленный класс по committed-карте
      `command-routing.json::mappings.*.class_selectors`. **Расхождение п.1↔п.2 → СТОП + D#**,
      а не выбор в пользу удобного.
   3. **Ни того, ни другого** (item не исполнялся; легаси-запись без маршрута) → **СТОП** с
      текстом «маршрут исполнителя <Pn.m> неразрешим: нет routing-adherence в Completion Notes
      и нет терминальной записи journal.jsonl» и названным ПРОХОДОМ (записать фактический
      маршрут по §9). Подстановка собственного пина команды, `unknown` и «продолжай как
      раньше» ЗАПРЕЩЕНЫ.

   Частный случай `plan-run`: сессия исполняет и закрывает item в ОДНОЙ сессии — «фактический
   маршрут сессии» И ЕСТЬ маршрут исполнителя, лестница схлопывается в п.1 тривиально.

   ```
   PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/lib" python3 - <<'PY'
   import sys
   from task import task_contract, route_evidence
   contract = task_contract.build("plans/<PLAN-ID>", "<Pn.m>", actual_route=route_evidence.capture_actual(
       "<provider-attested model_class с шага лестницы D75 выше>", "<provider-attested effort>",
       source="provider-doctor", model="<provider-attested модель>"))
   result = task_contract.evaluate(contract)
   print(result)
   sys.exit(0 if result["pre_mutation"] == "allow" and result["pre_final"] == "allow" else 1)
   PY
   ```

   Provider API не аттестует модель/effort → передай `capture_actual(None, None,
   source="self-attested")`, запиши unknown и остановись: self-attestation не заменяет selector.
   **Гейт бинарен.** Зелёное — РОВНО `pre_mutation == "allow"` И `pre_final == "allow"`.
   `n/a`, любой `block:*` и любое иное значение — красное; формулировки «условно зелёное»,
   «предупреждение», «продолжай, если …» и синонимы ЗАПРЕЩЕНЫ (`plan-protocol` §6 прямо
   запрещает «мягкий пункт Validation»). Таблица код→действие:

   | `pre_mutation` | `pre_final` | Действие |
   |:--|:--|:--|
   | `allow` | `allow` | зелёное — item честно резолвится в публично проверяемый факт; вердикт по status-rule ниже |
   | `block:*` | `n/a` | **`n/a` — НЕ зелёное** (`task-contract-v1.md:164-165`: «evaluated only when pre-mutation allowed; otherwise it reports `n/a` — a blocked session has nothing to declare done»): item НЕ закрывается; разбери код `pre_mutation` по код→действие таблице `plan-exec.md`'s Pre-mutation (реальные коды — эскалация п.5 analog / структурные — D#-запись, реопен-кандидат P2.6) |
   | `allow` | `block:ACCEPTANCE_NOT_PUBLIC` | реальный — заводит material-триггер «Validation осталась красной / acceptance-критерий не выполнен» ниже: `🟠 Done with deviations` с Known Deviations, НЕ тихий `🟢` |
   | `allow` | `block:EVIDENCE_REF_UNKNOWN` / `block:EVIDENCE_PROOF_CLASS_INSUFFICIENT` | структурный (`build()` этого не производит при корректной работе) — СТОП, D#-запись, реопен-кандидат P2.6 (владелец `build`), НЕ тихая правка здесь |

   **Что утверждает `pre_final` (D77, названо, не подразумевается).** Предикат проверяет
   свойство ФОРМЫ спеки item'а — есть ли хотя бы один публично проверяемый acceptance-пункт на
   детерминированном классе доказательства — и НЕ утверждает, что item исполнен ХОРОШО: он
   зелен и на не стартовавшем `⬜`-item'е. Вердикт material/process остаётся за status-rule
   ниже, `pre_final: allow` его не заменяет.

   Модуль `task.task_contract`/`task.route_evidence` недоступен (standalone-раскладка вне
   монорепо) → СТОП с явным текстом «шаг недоступен: `task.task_contract` не импортируется» —
   fail-closed.

   **Вердикт по фактам — по предикату material/process** (6 триггеров, не «на глаз»; §6
   канона, дословно как `plan-exec.md`). Непустые Known Deviations САМИ ПО СЕБЕ статус item'а
   НЕ меняют. `🟠 Done with deviations` ОБЯЗАТЕЛЕН при **material**-отклонении (любое из):
   Scope Included выполнен не полностью или иначе, чем предписано · Validation осталась
   красной · затронут public contract / SemVer / замороженный контракт СВЕРХ ТЗ item'а ·
   acceptance-критерий не выполнен · принят workaround, который ЖИВЁТ В КОДЕ/артефакте
   (а не в процессе исполнения) · item-коммит несёт дифф вне `Files` item'а (считается
   только по НЕплановым путям — carve-out §8), верен сам дифф или нет. `🟢 Done`
   сохраняется при **process**-отклонении, но запись в Known Deviations ОБЯЗАТЕЛЬНА:
   перебор тира (исполнено моделью/effort ВЫШЕ предписанных Routing), бандлинг коммитов,
   порядок правок, стилистика отчёта. Тихое умолчание = дефект (находка аудита).
   **Нет подтверждения (нет коммитов/диффа, Validation красная) — НЕ 🟢:** оставь/верни
   `🟡 In progress` или `🔴 Blocked`, причина — в Completion Notes item'а (`phases/Pn.md`).
   **`🔴 Blocked`/`⛔ Skipped by decision` при `Closure Protocol | v1` (opt-in, D44/P8.3):**
   допиши в **Pending Work** строку `Возобновление: <точная команда>` (🔴 — команда
   продолжения или `— (внешний блокер: <что ждём>)`, если локального шага нет в принципе;
   ⛔ — РОВНО `Возобновление: —` И ссылка `D<номер>`, предъявляющая решение о пропуске) —
   иначе `plan_lint.py` даёт ERROR.
   Файлы item'а НЕ закоммичены (`git status` modified/untracked) → item ещё не `🟢`: дождись
   коммита либо допиши в Completion Notes «не закоммичено, коммит — за оркестратором волны»
   (иначе cold-start по git-истории не увидит работу).
5. У `🟠`-item'ов перечитай Known Deviations: deviation могла быть устранена ПОЗЖЕ
   соседним коммитом (проверь git-историей) — устаревшую пометь «(устранено) … коммитом
   <sha>», не оставляй пугать несуществующим долгом.
6. Синхронизируй `## Phase Status` (в `phases/Pn.md`) и `## 4. Phase Index & Status Board`
   (в `plan.md`); перезапиши `handoff.md`, если статус изменился (заголовок `after Pn.m`,
   форма `Next` — из enum выше). **Печать кодов границ (D88/P10.1):** если вердикт шага 4
   закрывает item `🟢`/`🟠`, а Completion Notes ещё не несёт строку `write-site:
   pre_mutation: <код> · pre_final: <код>` — допиши её ОДНОЙ строкой из
   `result["pre_mutation"]`/`result["pre_final"]` того же шага 4 (не вычисляй заново, не
   пересказывай прозой — `plan_lint.py` матчит только эту строку построчно).
   **Цитаты-доказательства (P11.6), на итоговом дереве (после перезаписи handoff'а выше):**
   если вердикт шага 4 закрывает item `🟢`/`🟠` — `python3 packages/task/scripts/verify-plan-citations.py
   plans/<PLAN-ID> --strict`; счёт публикуется С АТРИБУЦИЕЙ: «цитаты: N находок — новых от
   диффа item'а: K» (baseline перечня `verify-citations-known-exceptions.json` чист — P11.5 —
   поэтому находка на итоговом дереве атрибутируется диффу ЭТОГО item'а). K > 0 — чинится
   ДО коммита реконсиляции; N − K > 0 (остаточные находки вне Scope item'а) — строка в
   Pending Work item'а + Open risks handoff'а, не молчаливое ослабление.
   **Журнал (D21, P1.1, хелпер `lib/task/journal.py`):** append ОДНУ запись —
   `PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/lib" python3 -m task.journal append --plan-dir plans/<PLAN-ID>
   --plan <PLAN-ID> --item <Pn.m> --command plan-close --actor sonnet/low
   --session-id "$(python3 packages/task/scripts/plan-session.py current --id)" --result
   <closed-green|closed-deviations|blocked — по итоговому статусу шага 4> --note "<1 строка:
   что сверено>"` (реконсиляция атомарна — старт-запись не нужна, один прогон = один факт).
   `--note` обязана быть не длиннее 300 символов; детали остаются в Completion Notes/findings,
   writer отказывает до записи, а historical long note сохраняется по D141.

## Режим `Pn` — закрытие фазы

0. Вычисли `candidate = task.plan_gates.phase_candidate_fingerprint(...)` из scope, terminal
   item heads и material risk, затем вызови
   `task.plan_gates.phase_audit_policy(..., candidate_snapshot=candidate["snapshot"])` и
   `phase_close_gate(..., candidate_fingerprint=candidate["fingerprint"],
   candidate_snapshot=candidate["snapshot"])`. Это ОДИН policy seam для handoff и close:
   `full`, material risk, non-green terminal item или multi-item `light` требуют fresh GREEN
   audit; `none` и single-item `light` при всех 🟢 и без material risk разрешают direct close.
   Fresh audit означает final verdict одного audit-fixer root на rebound candidate, а не routine
   repair-run/second-audit цепочку.
   Process-only deviation при 🟢 сам по себе audit не включает. Если policy требует audit,
   отсутствующий, RED, ATTENTION или stale audit отказывает без phase mutation; если не требует —
   gate возвращает `allow` без exploratory отказа. Audit сам фазу не закрывает.
   **Owner direct-close override — узкая ветка для policy, требующей audit.** Только explicit
   `phase_close_gate(..., owner_decision="D#")` может заменить audit-путь. Accepted,
   non-superseded carrier проходит либо как exact phase-scoped direct-green-validation
   (`item` и `items` содержат закрываемый `Pn`, есть `supersedes` и literal
   `` `phase-close: direct-green-validation` ``), либо как full-phase AUDIT-CAP remediation:
   `item` принадлежит фазе, `items` в точности равен всем item'ам фазы и body несёт literals
   `AUDIT-CAP`, `третьего Audit Pn` и штатный `task:plan-close`. Номер D — данные carrier,
   не product constant. Любое отсутствие/несовпадение возвращает named refusal без phase
   mutation; вызов без `owner_decision` сохраняет byte-semantically прежний audit GREEN path.
   **Terminal-blocked deviation override — отдельная owner-only ветка.** Accepted,
   non-superseded D# обязан иметь `item: Pn`, точный `items: [Pn, все Pn.*]` и literal
   `` `phase-close: terminal-blocked-deviations` ``. Gate дополнительно требует terminal
   candidate snapshot с хотя бы одним `🔴 Blocked`; только тогда разрешён `plan-close`
   `closed-deviations`, а phase status становится `🟠 Done with deviations`. Исторические
   RED/blocked item states, audit results и release disposition не переписываются. Без такой
   D# terminal blocked item остаётся fail-closed.
1. Все items фазы терминальны (`🟢`/`🟠`/`⛔`)? Нет — перечисли нетерминальные
   с их статусами и ОСТАНОВИСЬ (фаза не закрывается частично).
   Затем `git status --short`: файлы в дереве ВНЕ объединения Files всех item'ов фазы —
   предупреждение «незапланированные/грязные файлы в дереве закрываемой фазы» с их
   списком (не закрывай молча: это либо чужая незакоммиченная работа, либо регресс —
   маршрутизируй оркестратору).
2. Сведи таблицы: `## Phase Status` фазы (`phases/Pn.md`) ↔ статусы items ↔ строка фазы в
   `## 4. Phase Index & Status Board` (`plan.md`; `Items 🟢/всего`, статус фазы) — без
   расхождений.
3. **Docs-sync check (ОБЯЗАТЕЛЬНО, не «на усмотрение»).** Прогони критерий скилла
   `docs-maintenance` над сдачей фазы целиком (все Completion Notes items): есть
   содержательное для `docs/` проекта (новый процесс, возможность установки/настройки,
   схема, фича для понимания проекта, «трюк/подводный камень» работы с агентами,
   изменивший поведение флота)? Критерий не дублируем здесь — он один раз живёт в
   скилле `docs-maintenance`. Три исхода, ОДИН обязателен к записи в Phase Handoff (шаг 4):
   (a) обновил `docs/` — закоммить вместе с закрытием фазы (шаг 9) или отдельным
   doc-коммитом раньше; строка в Phase Handoff «Docs: обновлено — <файл(ы)>»;
   (b) не требуется — строка «Docs: не требуется» (не молчание — явная отметка, что
   проверка прошла); (c) требуется, но крупнее этой фазы — follow-up-строка в Phase
   Handoff «Что дальше», не тихая отсрочка. Гейт per-ФАЗА (не per-item — там шумно).
4. Заполни `## Phase Handoff` в `phases/Pn.md`: что сдали, известные отклонения, вердикт
   docs-sync (шаг 3), что дальше. **Агрегат «известные отклонения» собирается
   МЕХАНИЧЕСКИ** (J5/J6): перечисли непустые поля `Known Deviations` КАЖДОГО item'а
   фазы (item → его отклонение, дословно), а НЕ пересказом; все поля пусты →
   «отклонений нет». Утверждать в блоке то, чего нет в полях items, ЗАПРЕЩЕНО (ложь,
   класс B1). Блок несёт первой строкой маркер `> УСТАРЕЛ — фаза реопенена <D#>` (фаза
   реопенена, §3 скилла) — **сними маркер, перезаписав блок ЦЕЛИКОМ** актуальным
   сдачным текстом (снимает ТОЛЬКО эта команда); маркера нет — заполни блок как обычно.
4a. **Отчёт закрытия фазы `closure/<Pn>.json`** (P8.1/D42) — ТОЛЬКО если `## 0. Meta` плана
   несёт `Closure Protocol | v1` (нет поля — шаг пропускается молча, это opt-in). Собери файл
   **МЕХАНИЧЕСКИ из полей items фазы**, пересказ запрещён: `items[]` — по строке на item
   (`id`/`status` из `## Phase Status` БЕЗ расхождений, `evidence_class` + `evidence`);
   `gates[]` — гейты сдачи; `metrics[]` — числа сдачи (`value` строкой); `phase_status` —
   байт-в-байт строка фазы из Status Board; `git` — `head_sha`/`branch`/`dirty` на момент
   закрытия; `inputs_sha256` — sha256 `plan.md` и `phases/<Pn>.md` (`sha256sum`).
   **Класс свидетельства — enum РОВНО из трёх** (`real` — прогон на закоммиченном дереве,
   evidence несёт команду и число · `synthetic` — фикстура/один кейс, evidence это НАЗЫВАЕТ ·
   `baseline_pending` — числа нет, названа ПРИЧИНА). «Нет числа» выражается ЗАПИСЬЮ
   `baseline_pending`, а НЕ отсутствием ключа/строки; `real` с пустым evidence = ERROR линтера.
   Схема и правила заполнения — `snippets/closure-template.md` скилла `plan-protocol` (§8);
   файл входит в коммит закрытия (шаг 9, `git add plans/<PLAN-ID>`).
5. Перезапиши `plans/<PLAN-ID>/handoff.md` **целиком**: заголовок
   `# HANDOFF — <ISO-дата> — after Pn` (закрывается ФАЗА, не item — D30); Next — launch-
   block с формой из enum выше (первый item следующей фазы или закрытие плана) + сверка
   с Execution Rules (правила в шапке).
   **Отдельно** добавь строку в `## 6. Update Log` плана (`plan.md` — НЕ в `handoff.md`:
   он перезаписывается целиком, запись бы исчезла): «Что» ≤ 2 строк, без пересказа
   Completion Notes (канон §4 скилла).
6. Если ВСЕ фазы плана теперь терминальны (`🟢`/`🟠`/`⛔` — по строке статуса каждой фазы
   в `## 4. Phase Index & Status Board`) — план закрыт ЦЕЛИКОМ: обнови `plans/ACTIVE.md`
   (в корне `plans/`; файла нет — создай) на канонический формат 4 строки: `# ACTIVE`,
   пустая строка, `**Active:** —`, `**Updated:** <YYYY-MM-DD>`; обнови `Status` в
   `## 0. Meta` plan.md (агрегат фаз: все 🟢 → `🟢 Done`, есть 🟠 → `🟠 Done with
   deviations`); в `Next:` handoff'а пиши «план закрыт» (линт это допускает только при
   полностью терминальном плане); добавь строку в `## 6. Update Log` **плана** (`plan.md`).
   Закрывается ОДНА фаза, другие ещё нетерминальны — `plans/ACTIVE.md` НЕ трогай.
   `Last Updated` в `## 0. Meta` плана = дата закрытия фазы (машинного гейта нет, сверяет
   `plan-audit`).
7. `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/plan-lint.py" plans/<PLAN-ID> --baseline HEAD`
   — **ПОСЛЕ шага 5** (прогон ДО перезаписи handoff ЗАПРЕЩЁН: счёт «до» не описывает
   финальное дерево; нет переменной/скрипта — предупреждение и пропуск). Счёт с
   АТРИБУЦИЕЙ: `N ERROR / M WARN — новых от закрытия: K` (`--baseline HEAD`). K > 0 —
   чинится ДО коммита; N − K > 0 (остаточные ошибки вне этой фазы) — строка в Open risks
   `handoff.md`. Любое число в отчёте — с якорем дерева `<число> (на <git-ref>)`.
   Следом (та же граница — после перезаписи handoff, на итоговом дереве): `python3
   packages/task/scripts/verify-plan-citations.py plans/<PLAN-ID> --strict`; счёт с той же атрибуцией: «цитаты:
   N находок — новых от закрытия: K» (baseline перечня `verify-citations-known-exceptions.json`
   чист — P11.5). K > 0 — чинится ДО коммита закрытия фазы; N − K > 0 (остаточные находки вне
   этой фазы) — строка в Open risks `handoff.md`.
8. **Журнал (D21, P1.1):** append ОДНУ запись для закрываемой ФАЗЫ (item_id = `Pn`) —
   `python3 -m task.journal append --plan-dir plans/<PLAN-ID> --plan <PLAN-ID> --item Pn
   --command plan-close --actor sonnet/low
   --session-id "$(python3 packages/task/scripts/plan-session.py current --id)" --run-id <derive_run_id для plan/Pn/attempt/session>
   --attempt <N> --result <closed-green — все items 🟢 |
   closed-deviations — хоть один 🟠> --note "фаза Pn закрыта"` — ДО коммита закрытия (шаг 9,
   `journal.jsonl` входит в `git add plans/<PLAN-ID>` того же коммита).
9. **Коммит закрытия фазы — ОДИН** (только плановые пути + docs/, если правился шагом 3;
   топология «двух коммитов» §8 — про ITEM, не про фазу — второй не выдумывай):
   `git add plans/<PLAN-ID>` (+ `docs/<файлы>`, если правились) — `git add -A` /
   `git commit -a` ЗАПРЕЩЕНЫ — чужой дифф уедет незамеченным) + Conventional Commits (рус.)
   `docs(plan): фаза Pn закрыта (<PLAN-ID>)`. Идёт **ПОСЛЕ lint'а** (шаг 7, гейт K = 0); хеш
   этого коммита — в отчёт (якорь дерева для чисел, D36). Cold-start по `git log` иначе
   видит `next: plan-close … Pn` и закрывает фазу повторно.

## Режим `archive <ID>` — конвейер план→архив→docs

Скилл `plan-protocol` §12. Терминальный план не лежит вечно в `plans/` — переезжает в
архив, а его долгоживущий материал (`root/`) мигрирует в документацию проекта.

1. **Предусловия.** План терминален ЦЕЛИКОМ (каждая фаза `🟢`/`🟠`/`⛔` в
   `## 4. Phase Index & Status Board`) — нет: перечисли нетерминальные фазы и
   ОСТАНОВИСЬ (сначала режим `Pn`). `plans/ACTIVE.md` указывает на `<ID>` — сброс на
   `—` входит в шаг 4. Meta несёт `Home: repo:<путь>` — работай в репо-доме; синк
   зеркала в Brain (`brain sync`) — ДО переноса, чтобы архивировалась финальная версия.
2. **Перенос.** `git mv plans/<ID> plans/archive/<ID>` — ОТДЕЛЬНЫМ коммитом
   `chore(plan): archive <ID>`, без других правок в этом коммите.
3. **Миграция root/ → docs** проекта по Diátaxis-типам: `architecture.md`/
   `philosophy.md` → explanation; `data-model.md`/`contracts/` → reference; гайды фаз →
   how-to. Набор — что фактически лежит в `root/` (пусто/нет каталога — шаг пропусти,
   отметь в чек-листе); целевые пути — канон docs проекта. `artifacts/`, `findings/`,
   `research/` остаются в архиве, в docs не мигрируют.
4. **Реестры и ссылки.** `plans/ACTIVE.md` — сброс на `—`, если указывал `<ID>`;
   ссылки на `plans/<ID>` в живых доках/реестрах → `plans/archive/<ID>`.
5. **Чек-лист миграции** (что перенесено в docs — файл→файл, что осталось в архиве) —
   допиши в финальный `handoff.md` архивированного плана (уже в `plans/archive/<ID>/`).
6. До второго коммита допиши в перенесённый journal terminal `item_id=archive`,
   `command=plan-close`, `result=closed-green` с непустым `session_id` и derived
   `run_id`; journal обязан войти во второй коммит, а не остаться незакоммиченным.
7. Миграционный дифф (docs + реестры + handoff + terminal journal) — вторым коммитом
   `docs(plan): миграция root/ <ID> → docs`. Прогони plan-lint по `plans/archive/<ID>`
   как в п. 6 режима `Pn` (счёт с атрибуцией `--baseline HEAD`). После коммита собери receipt
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/plan-delivery.py" --plan-dir plans/archive/<ID>
   --subject archive --kind terminal`. Ненулевой exit запрещает `final` и возвращает
   к repair носителей.

## Delivery receipt before final

В режиме `Pn.m` вызови `plan-delivery.py --subject Pn.m --kind terminal`; в режиме
`Pn` — `--subject Pn --kind terminal`; archive использует шаг 7. Receipt собирается
ТОЛЬКО после terminal journal/state, final handoff и closure, где она есть.
`FINAL_BEFORE_TERMINAL_FORBIDDEN`, stale digest, missing run_id или recommendation оставляют
dispatch активным. Финал обязан вывести `Delivery receipt: <compact JSON>` и
`Рекомендация следующего шага:` с exact `recommendation` receipt.

**Expected output режима `archive`:** строка `PLAN-ARCHIVED: <ID>` + чек-лист миграции
(перенесено → куда | осталось в архиве) + два sha коммитов. Next вне протокола —
launch-block не требуется, следующий план выбирает владелец.

**Expected output (режимы `Pn.m`/`Pn`):** таблица сверенных статусов
(`ID | было | стало | основание`) + `Lint: N ERROR / M WARN — новых от закрытия: K`
(режим `Pn`) + строка `Docs-sync: <обновлено <файлы> | не требуется | follow-up>` (режим
`Pn`, шаг 3 — обязательная, не опускай) + финальная строка «PHASE-CLOSED: Pn» (фаза
закрыта) либо список блокеров, почему фаза не закрыта. В ЛЮБОМ исходе финал сообщения —
полный launch-block следующего шага (SKILL §8): режим `Pn.m` / фаза НЕ закрыта → блок
следующего item'а (копия свежеперезаписанного handoff.Next: таблица + отдельный command block;
проза «выполните команду X» без Model/Thinking = дефект). При наличии
`plans/<PLAN-ID>/roadmap.md` следующий шаг сверяется с ним: шаг в batch/workflow-группе →
команда ГРУППЫ, не одиночный item; закрытие фазы/re-design → обнови roadmap (живой
документ). Фаза закрыта — сразу после
строки PHASE-CLOSED допиши launch-block:
```
| Параметр | Значение |
|:--|:--|
| Batch | <stable ID из Routing / solo; n/a для close/archive> |
| Model | <sonnet | opus | haiku | fable> |
| Thinking | <effort> — <причина в 3–8 слов> |
| Context | <РОВНО одно из трёх значений enum'а выше> |
| Суть | <1 строка: что делает следующий шаг> |

<ОБЯЗАТЕЛЬНЫЙ отдельный fenced code-block: provider-native команда; следующая детализированная
  фаза → `/task:plan-exec <PLAN-ID> P(n+1).1`; manual-фаза → prompt либо `/task:plan-run ...`;
  терминальный план → `/task:plan-close archive <PLAN-ID>` либо команды нет. Команда не должна
  противоречить Execution Rules; копипаст без правок.>
```
