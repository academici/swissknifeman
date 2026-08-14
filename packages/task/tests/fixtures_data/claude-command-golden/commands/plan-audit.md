---
description: "План-протокол: независимый audit-fixer terminal phase candidate Pn перед phase close либо один pre-exec review плана (design). Пинит Opus/xhigh."
argument-hint: "<PLAN-ID> Pn | <PLAN-ID> design"
model: opus
effort: xhigh
---
Это независимый ADVERSARIAL audit-fixer terminal phase candidate перед единственным phase close
либо pre-exec review плана. Ввод пользователя: «$ARGUMENTS».
Модель/effort запинены (Opus/xhigh) — не переключай вручную. В phase-режиме root после
детекта владеет safe in-scope ремонтом: product writes разрешены только в union `Scope Included`/
`Files` items фазы и для доказанного bounded incidental repair. Design-режим остаётся read-only.

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

**Layout v2 — production after audit (P6.2).** Journal append несёт session identity, затем
команда регенерирует применимые `plan-views.py state|status|decisions|closure|bundle` и подтверждает
их `--check`; в item-spec outcome-поля не дописываются. Если audit фиксирует terminal escalation,
она оставляет return-evidence с одним из `new`/`repeat`/`unqualifiable`; `unqualifiable` никогда не
маскируется как `new`. Для producer-closing evidence downstream outcome (`green`/`red`/`unknown`)
записывается отдельным closing command, а audit только проверяет его item-scoped carrier.

**Compiler (P2.7/P2.11).** `task:plan-exec`'s Pre-mutation (шаг 2) И Pre-final (шаг 7, штатный
путь самозакрытия) — а для item'ов, закрытых реконсиляцией, `task:plan-close`'s Pre-final (шаг
4) — ИСПОЛНЯЕМЫЕ write-site (не проза): каждый закрытый item обязан нести в Completion Notes
напечатанные результаты ОБЕИХ границ (`pre_mutation` И `pre_final` коды) — читай ИХ как источник
истины предиката, не пересчитывай вручную вторым способом. Гейт закрытия бинарен
(`pre_mutation == "allow" and pre_final == "allow"`, D76): `n/a` НЕ зелёное — item со статусом
`🟢`/`🟠`, чьи напечатанные коды не оба `allow`, = находка Major (status-rule обманут). `pre_final`
утверждает свойство ФОРМЫ спеки, не качество исполнения (D77) — не путай это со status-rule
material/process ниже. `plan_lint.py`'s tiered-portability находки — та же дисциплина
(`plan-portability-v1.md`, D47).

`plan-audit` — профиль **«ревью плана»** таксономии `quality/artifact-review`: конституция соответствия
= схема plan-protocol (канон 2.5+) + DoR; измерения (RAG-groundedness несущих, структурная полнота,
непротиворечивость D-лога, вынос Open Questions, гейты) — в чеклисте. Профили doc/code — `task:review`.

**Режим `<PLAN-ID> design` — pre-exec ревью ВСЕГО плана (финальный гейт утверждения).**
Запускается ДО старта исполнения (аналог task:review для плана): git/код не сверяется —
проверяется сам план. Чеклист режима (вердикт GREEN/ATTENTION/RED + список находок):
1. **Покрытие брифа:** каждая мысль `brief/00-brief.md` (+refinements) покрыта фазой/item'ом
   или явно отклонена D-записью — таблица «мысль → носитель» с дырами; непокрытая мысль = Major.
2. **Слепые/серые зоны:** adversarial-проход «что НЕ покрыто ни одной фазой, но нужно для цели
   плана» (интеграции, миграции данных, регрессы, обратная совместимость, деплой, доки).
3. **Слои знаний связны (SKILL §16):** brief/ есть и непуст (гейт линтера); несущие факты имеют
   RAG-маркеры и живут в findings/, синтез — в research/, D-записи ссылаются на слои; несущий
   факт только в чате = Major.
4. **Контракты фаз согласованы:** «Потребляет» каждой фазы производится предыдущими; coupling-
   поверхность из D-лога не противоречит фазам; Routing покрывает все items.
5. **plan-lint зелёный** + DoR детализированных фаз; **дизайн-бюджет исполнен**: Meta
   `Design Passes: k/N` — k≥N по Update Log-строкам «Design pass …» (недобор без D-записи
   владельца = Major).
6. **Roadmap исполним (SKILL §8):** `roadmap.md` есть (план детализирован — иначе ERROR линтера),
   §3 несёт обязательные `Batch`/`Review` и покрывает каждый item; batch phase-local/adjacent,
   имеет единый Exec и доказанный reuse-выигрыш; `solo` называет конкретную hard/economy boundary;
   покрывает ВСЕ items без дыр, батчи обоснованы (сцепленный scope + одна модель), у каждого
   solo — причина «почему нельзя объединить», у batch/workflow-групп — готовые launch-block'и,
   гейты владельца — только там, где решение реально его; roadmap не противоречит §3 Routing.
   Проверяй orchestration shared line-scoped predicate: explicit negation того же statement не
   требует workflow, но отдельное positive `scriptPath`/multi-agent declaration требует.
7. **D-лог: `Consequences` у отменяющих/заменяющих записей (SKILL §6).** Каждая D-запись,
   объявляющая `supersedes D#`/отмену/замену ранее принятого решения, несёт инлайн-подполе
   `**Consequences:**` внутри ячейки `Решение` — независимо от того, включён ли `Closure
   Protocol` (машинный `plan_lint.py`-гейт покрывает только подкласс при включённом протоколе
   и дате ≥ cutoff, SKILL §6); отсутствие — Minor находка design-ревью (дисциплина, не только
   машинный гейт).
В design-режиме findings возвращаются владельцу один раз; повторный review нужен только после
material scope/SHA/risk change, а не из-за bookkeeping-правки.
Остальные пункты ниже (git-сверка, no-op, Completion Notes) относятся к режиму `Pn` — в
`design` их пропусти.

1. **Две ступени — дешёвая ПЕРЕД дорогой.** **ПЕРВЫЙ вход ступени 1** (режим `Pn`, если план
   несёт `## 0. Meta` → `Closure Protocol | v1`) — отчёт закрытия `plans/<PLAN-ID>/closure/<Pn>.json`
   (P8.1/D42, схема — `snippets/closure-template.md` канона): читаешь его ДО грепов и чтения прозы.
   Что он даёт: (а) `evidence`/`evidence_class` каждого item'а и гейта — команды перепрогоняются
   ТОБОЙ на `git.head_sha` отчёта, расхождение с заявленным классом (`real` там, где прогон не
   воспроизводится, либо `synthetic`, выданный за результат) = находка **Major**; (б)
   `inputs_sha256["phases/<Pn>.md"]` ≠ фактическому хешу файла сейчас ⇒ **ТЗ фазы правился после
   закрытия** — проверь, не съехал ли scope (`git log -p` по файлу фазы после `closed_at`); (в)
   `limitations[]`/`external_side_effects[]` — заявленные границы сдачи, сверяются с Completion
   Notes. Отчёта нет при включённом протоколе — это ERROR линтера, не твоя находка; протокол не
   включён — пункт пропускается, ступень 1 идёт как ниже. Затем — **конфликт-скан** (детерминированный),
   ПЕРВОЙ, самой дешёвой командой — **`plan-lint.py --conflicts`** (без аргумента-плана, roadmap
   `plan-audit-loop.md` §A.1, 2026.07.31-SKM-LEAN P5.9): сверяет реестры-константы `plan_lint.py`
   (шесть статусов, 16 полей item'а, закрытый enum форм `Next`, три значения `Context`, литералы
   `i18n-keep`, регекс-носители launch-block'а, v2-carriers) с их объявлениями в `SKILL.md` — тот же класс
   «канон ↔ `plan_lint.py`», что дал БОЛЬШИНСТВО окупающихся находок трёх RED-раундов
   `plan-audit-loop.md` (слип перевода `Items 🟢/всего` → `Items 🟢/total`), ловится за секунды. Следом —
   остальные ступени скана: `validate.sh` затронутых пакетов · тесты линтера · EN-only canon weight gate ·
   `plan-lint plans/<PLAN-ID> --baseline <sha до фазы>`. Затем — adversarial-чтение **свежим
   контекстом**: Completion Notes писал исполнитель сам себе — суди по git/коду (`git log`/`git diff` по
   `Files` каждого item'а: slice, не файлы целиком).

2. **Правила остановки.** Гейт не имеет права стоить дороже дефекта, который ловит.
   - **Scope-граница.** Мандат — «выполнены ли **Deliverables фазы** по её `Scope Included`», а НЕ
     «найди всё плохое в артефакте». Находка вне scope фазы законна, но идёт Minor/Nit и вердикт НЕ красит.
   - **Порог severity: severity НАХОДКИ ≠ вердикт ФАЗЫ.** `RED` — только когда сломан ПРОДУКТ фазы:
     правило/код, ломающие потребителей; no-op под 🟢; невоспроизводимая Validation; ложное утверждение о
     факте. Детерминированный non-material дефект бухгалтерии плана исправь inline текущим root,
     регенерируй owner-carrier и один раз повтори узкий gate в том же attempt. Только неустранимый
     либо out-of-scope остаток не красит phase verdict. В phase-режиме `ATTENTION` не terminal
     escape: исправимый остаток чинится, non-gating остаток репортится под `GREEN`. «При сомнении
     ставь ВЫШЕ» (п. 4) — про severity НАХОДКИ, не про ВЕРДИКТ.
   - **Один owning root.** Номер захода = число блоков `## Audit Pn` в `phases/Pn.md` + 1 и
     печатается всегда, но routine `audit → repair-run → second audit → AUDIT-CAP` запрещён.
     Safe in-scope finding, включая material `🟠`, немедленно чинится в этом root; после каждого
     ремонта повтори exact item Validation, append honest item evidence через journal owner,
     регенерируй views и пересобери candidate. Verdict разрешён только для последнего rebound
     candidate. Первый same fingerprint меняет tactic; лишь повтор или новый material risk
     разрешает один `isolated-child-return`, который возвращается в этот же root.
   - **Настоящая граница.** Out-of-scope non-product observation записывается как non-gating и не
     красит verdict. Acceptance failure — работа owning root, а не terminal label. Authority/
     public-frozen сигнал сначала проходит `plan_authority`; delegated продолжает repair, и только
     `approval_required`/`denied` дают exact waiting/terminal continuation. Safety сигнал сначала
     проходит `plan_blocking`; только action `terminal-block` после distinct `JUSTIFIED` терминален.
     Ни сложность, ни длительность тестов, ни stale provider projection не являются остановкой.

3. **Чеклист** (по каждому пункту — вердикт с доказательством: `file:line` + прогон):
   - каждая `🟢`/`🟠` сверяется с git/кодом: правки реально существуют и делают заявленное
     (**no-op detection** — статус закрыт, а содержательного диффа нет);
   - **committed vs working-tree**: `🟢` при некоммиченных `Files` = находка (рабочее дерево ≠ история:
     cold-start по `git log` «закрытую» работу не увидит);
   - **scope drift**: диффы вне `Files`/`Scope Included` items фазы (сделано то, чего план не просил);
   - дублирующиеся шаги между items (одно «сделано» дважды — признак слепого исполнения);
   - **Validation реально прогнана**: КАЖДЫЙ пункт поля `Validation` закрытого item'а прогоняешь сам НА
     ЗАКОММИЧЕННОМ дереве item'а (`git show <ref>:<файл>`), а не на веру и не на дереве момента аудита;
     расхождение с заявленным = находка; item, закрытый `🟢` БЕЗ отчёта по своей Validation, = находка;
   - **write-site реально исполнен (P2.7/P2.11, F1-дисциплина)**: item, закрытый ПОСЛЕ P2.7
     (командные тела несут исполняемый Pre-mutation/Pre-final), без напечатанных `pre_mutation`
     И `pre_final` кодов ОБЕИХ границ в Completion Notes = находка (общая фраза «контракт
     скомпилирован» без результата — ссылка на модуль, не доказательство, ровно F1); проверь код
     сам на закоммиченном item'е тем же вызовом, что несёт `plan-exec.md`/`plan-close.md`, с
     маршрутом ИСПОЛНИТЕЛЯ (D75), не своим пином `opus/xhigh`; **item `🟢`/`🟠` с напечатанным
     кодом ≠ `allow` на любой из границ (включая `pre_final: n/a`) = находка Major** (D76: `n/a` не
     зелёное, закрытие на нём — рецидив F1);
   - **status-rule** (§6): item `🟢` с непустыми Known Deviations — сверь по предикату **material** (Scope
     выполнен не полностью/иначе · Validation осталась красной · затронут public contract / SemVer сверх
     ТЗ · acceptance не выполнен · workaround ЖИВЁТ В КОДЕ · item-коммит несёт дифф вне `Files`): material
     под `🟢` = находка Major; `🟠` без единого material-триггера = находка (обесценивание статуса);
   - **топология и гигиена коммита** (§6/§8): `git show --stat <item-коммит>` — файлы вне `Files` item'а →
     находка Major + статус обязан быть `🟠` (carve-out: `plans/<PLAN-ID>/**` и `plans/ACTIVE.md` посторонним
     диффом НЕ считаются); item-коммит несёт ФЛИП СТАТУСА/бухгалтерию плана = бандл шагов 1 и 6 —
     process-отклонение, и БЕЗ записи в Known Deviations это находка («тихое умолчание»); плейсхолдер вместо
     реального хеша item-коммита в `handoff.md` либо строка item'а в `## 6. Update Log` без этого хеша =
     находка (карта «коммит → item» рвётся);
   - **честность lint-отчёта** (§8; гейт закрытия = `K = 0`, а не `N = 0`): перепрогони `plan-lint
     plans/<PLAN-ID> --baseline <sha bookkeeping-коммита item'а>` и сверь с опубликованным счётом
     `N ERROR / M WARN — новых …: K`; расхождение = находка Major (прецедент: заявлено 78 при факте 79);
   - **якорь дерева** (§8): КАЖДОЕ число в Completion Notes / Validation / Known Deviations / Update Log
     перепрогоняется ЕГО ЖЕ командой на закоммиченном дереве item'а; число без якоря
     `<число> (на <git-ref>)` либо невоспроизводимое = **ложное утверждение**, находка;
   - **протухший `## Phase Handoff`** (§3): фаза `🟡`/`⬜`/`🔴`, блок утверждает закрытие и не несёт
     первой строкой `> УСТАРЕЛ — фаза реопенена <D#>` = находка (линтер даёт WARNING; ты проверяешь
     СОДЕРЖАНИЕ: блок описывает фактическое состояние фазы или прошлое);
   - **`Last Updated`** (§8, шаг 2): поле `## 0. Meta` старше даты последней строки `## 6. Update Log`
     = находка (машинного гейта нет by design);
   - **развилки** (§3/§4): развилка `## Обсуждение` без строки `**Статус:**` = находка; статус
     ≠ `Resolved → D#` без записи в `open-questions.md` = находка;
   - **cross-plan notification** (§11): item бампнул замороженный контракт (semver) — обновлены ли строка
     `Exported` донора и `Consumed` КАЖДОГО потребителя в том же корне `plans/`; нет = находка;
   - **RAG-маркеры несущих** (§7 — enum ТРЁХ значений): каждый load-bearing факт/вердикт в Intent/Why/
     Implementation Rules items и в D-логе несёт РОВНО один — `RAG:✅ <дата/суть>` · `RAG:—` (repo-grounded
     факт / внутреннее правило) · `[UNVERIFIED]`. Несущий пункт БЕЗ маркера = находка; `RAG:—` на ВНЕШНЕМ
     факте (версия/API библиотеки, «ещё актуально», рынок, чужой сервис/MCP) = та же находка;
   - workarounds из `.claude/runs/*.json` (телеметрия devloop: `devloop{workarounds,deferred,
     open_questions}`) отражены в Pending Work/Known Deviations items — обходка, осевшая только в
     телеметрии, = скрытое отклонение;
   - `handoff.md` и `## Phase Handoff` достаточны для холодного старта (агент без этого чата поймёт, где
     правда и что делать дальше); агрегат Known Deviations фазы собран ИЗ ПОЛЕЙ items, а не пересказом;
   - **DoR-ретроспектива**: фаза ушла в exec с незакрытыми `[NEEDS CLARIFICATION]` = находка;
   - **routing-adherence**: модель/effort фактического исполнения (Update Log / Completion Notes) ≠ строке
     §3 Routing без записи в Known Deviations = находка; у item'а с `Exec = manual` ФАКТИЧЕСКАЯ
     модель/effort обязана быть НАЗВАНА в отчёте (самоатрибуция машинно не проверяема — её отсутствие и
     есть находка).

4. **Детект ≠ гейтинг.** Репортишь ВСЕ находки: `severity ∈ {Blocker,Major,Minor,Nit}` +
   `confidence ∈ {high,med,low}` (уверенность в самой находке — чтобы владелец мог ранжировать;
   низкая уверенность — повод пометить, а не отбросить) + лейбл
   `issue/suggestion/question/nitpick` (ось `quality/artifact-review`) + `file:line` + `failure_scenario`
   (сценарий поломки); при сомнении ставь ВЫШЕ. Вердикт фазы — по порогу п. 2, не по максимуму severity.

5. **Production и final verdict.** Сначала для каждого safe repair выполни two-commit topology
   owning item'а, его exact Validation и Pre-mutation/Pre-final; затем через owners запусти
   `plan-views.py state|status|decisions|closure|bundle` и их `--check`. Получи candidate до и
   после через `task.plan_gates.phase_candidate_fingerprint(...)`; `audit_fixer_rebind(before, after)`
   обязан отличить product/item-state изменение от audit bookkeeping. Только после последней
   rebinding append-блок `## Audit Pn — <YYYY-MM-DD>` в КОНЕЦ `phases/Pn.md`: строка
   `**Вердикт: <GREEN|ATTENTION|RED>**`, findings/repair evidence и `### Что запускать`.
   Launch-block живёт именно здесь, а не только в чате. **Журнал (D21, P1.1):** на один final
   candidate append одну запись — `python3 -m task.journal append --plan-dir plans/<PLAN-ID> --plan <PLAN-ID>
   --item <Pn — режим фазы|design — режим design> --command plan-audit --actor opus/xhigh
   --session-id "$(python3 packages/task/scripts/plan-session.py current --id)"
   --result <audit-green|audit-red> --fingerprint <SHA-256 candidate scope + terminal item heads +
   material risk> --note "audit-fixer, кандидат <fingerprint>, вердикт <вердикт>"`.
   В phase-режиме writer отклоняет `audit-attention`. `audit-red` дополнительно требует
   `--decision-json` с exact reducer action, reason/evidence IDs и continuation; без него append
   обязан вернуть `AUDIT_TERMINAL_EVIDENCE_REQUIRED`. Design-режим сохраняет собственную
   read-only шкалу GREEN/ATTENTION/RED.

6. Находка, достойная повышения в скилл/правило экосистемы (повторяемый анти-паттерн исполнителя, дыра
   протокола), — пометь `PROMOTE-CANDIDATE` в тексте finding'а.

**Handoff delivery receipt.** После записи verdict и final handoff, но до `final`, вызови
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/plan-delivery.py" --plan-dir plans/<PLAN-ID>
--subject <design|Pn> --kind handoff`. Receipt связывает ответ с exact persisted `Next`;
ненулевой exit запрещает `final` до repair. Финал печатает `Delivery receipt:
<compact JSON>` и `Рекомендация следующего шага:` с exact `recommendation` receipt.

**AUDIT-ROOT-TERMINAL (routing/cost boundary).** После записи terminal verdict и обязательных
carrier'ов этот audit root ЗАВЕРШАЕТСЯ: он не исполняет successor command, даже если тот
совместим по capability или уже ready. Для каждого runnable successor из audit launch-block
ставь `Context: cold-start-root: audit-root-terminal`, сначала provider-neutral semantic Next,
затем native fresh launch block с selector'ами маршрута successor. Это fresh routed root, а не
просьба переключить модель внутри audit session. Граница не ограничивает автономность внутри
совместимого execution route и не меняет семантику routing overshoot.

**Expected output:** в phase-режиме вердикт `GREEN` (acceptance сходится после inline repairs;
non-gating observations перечислены) либо `RED` (только reducer-confirmed authority/block boundary).
`ATTENTION` остаётся только у read-only design-режима. Далее: **номер захода** + фактический счёт линтера с якорем дерева
(`N ERROR / M WARN (на <git-ref>)`) + findings (severity · confidence · item · `file:line` ·
failure_scenario) + rebound candidate fingerprint. Затем launch-block (форма канона §8): таблица `| Batch |
Model | Thinking | Context | Суть | Команда |` — строка `Команда` несёт голую команду; `GREEN` без находок,
чей следующий шаг выражается ОДНОЙ командой, — строка есть весь ответ, code-block не заводится.
`RED` (а в design-режиме также `ATTENTION`) несёт SCOPE-PAYLOAD (ниже) — там code-block ОБЯЗАТЕЛЕН дословно как раньше
(четыре строки не умещаются в ячейку). Следующий item с `Exec = manual` — форма «ЗАПУСК ВРУЧНУЮ»:
`Model`/`Thinking` из Routing, строка `Команда` = `—`, code-block ОБЯЗАТЕЛЕН и несёт ГОЛЫЙ ПРОМПТ
item'а, не slash-команда, копипаст без правок. Тот же launch-block дословно — подсекцией
`### Что запускать` в конце твоего audit-блока (п. 5).

**Phase `RED` → SCOPE-PAYLOAD только для reducer-confirmed границы.** Safe finding не получает
repair successor: audit-fixer исчерпывает classifier и чинит его в текущем root. Acceptance
failure сам по себе не boundary. Payload разрешён только для exact waiting/terminal continuation,
который вернул `plan_authority` либо `plan_blocking`, и обязан совпасть с `decision.continuation`
journal event. Под continuation, в том же code-block'е, четыре строки фиксированного порядка:

```
<exact waiting:/terminal: continuation из reducer evidence>

РЕЖИМ: доказанная граница audit-fixer; НЕ ordinary repair-run и НЕ второй audit
ВХОД: plans/<PLAN-ID>/phases/Pn.md → блок `## Audit Pn — <дата>`; прочитать ПЕРВЫМ
СКОУП: 1) <…> 2) <…> 3) <…>   — по одному пункту на находку/шаг, только то, что чинится
НЕ ТРОГАТЬ: <ТЗ/Scope/Files/Validation закрытых items, чужие фазы — что оставить как есть>
```

`СКОУП:` выводится из доказанной boundary. `НЕ ТРОГАТЬ:` обязателен: дорогая ошибка принимающей
сессии — не «сделает мало», а «переделает всё». `GREEN` не несёт payload: audit-fixer уже устранил
safe findings. `plan-lint` гейтит присутствие четырёх строк в audit-блоке.

Команду выбрать по вердикту:
- `GREEN` → `/task:plan-close <PLAN-ID> Pn`; close сам проверяет rebound candidate fingerprint;
- phase `RED` → exact `waiting:`/`terminal:` continuation из reducer evidence. Прямой
  `design-phase`, `design-item`, `exec-items` либо `run-items` после phase RED запрещён: после
  authority response исходный owning root возобновляется и сам заканчивает repair. Ordinary Next
  никогда не создаёт repair-run, design-pass или second audit.

Model/Thinking — из §3 Routing плана (канон §9). В terminal audit successor Context всегда
`cold-start-root: audit-root-terminal` по AUDIT-ROOT-TERMINAL выше; вне этого случая действуют
три значения enum'а §8: `continue-root` (authoritative root может продолжить) ·
`isolated-child-return` (bounded reviewer возвращает evidence в тот же root) ·
`cold-start-root` (новый root перечитывает committed carriers; обязателен один reason из канона).
