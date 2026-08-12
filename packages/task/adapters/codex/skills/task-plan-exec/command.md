<!-- Generated Codex runtime projection; do not edit as source.
Canonical source: packages/task/commands/plan-exec.md
Canonical SHA-256: sha256:f133d8dc993dc2fedb76ccf74ec7cddc07bf06451cd8e0b18f15a6d2d61d15bf
Adapter: task.codex-command/1.0.7
-->
## Native Codex launch-block — mandatory for every handoff

`$ task:…` is an invocation inside the **current** Codex session, not a fresh launch.
When handing off a plan step, print a separate `Native Codex launch-block` which explicitly
pins the repository cwd, the mapped model, reasoning effort, approval policy, and sandbox:

```bash
codex -C <repo-cwd> -m <model-selector> -c 'model_reasoning_effort="<effort-selector>"' -a never -s danger-full-access '$ task:<command> <arguments>'
```

Derive the class and effort from the next item's Routing before rendering it; for `plan-run`,
do not reuse the preceding session's route. Current Codex mapping: economy=gpt-5.6-luna, implementation=gpt-5.6-terra, frontier=gpt-5.6-sol;
low=low, medium=medium, high=high, xhigh=xhigh. Keep the provider-neutral launch-block too, but never hand off only
`$ task:…` or an unpinned `codex` command.

Это ИСПОЛНЕНИЕ item'а мастер-плана (plan-протокол). Ввод пользователя: «$ARGUMENTS».
Модель/effort запинены (implementation/medium) — не переключай вручную. Команда самодостаточна:
весь протокол ниже, скилл `plan-protocol` дочитывай только при явной ссылке из плана.
Несколько item'ов в аргументах — исполняй последовательно, каждый по полному циклу 1–8.
**Батч §3 Routing** (item'ы одной группы `Batch`) — та же серия: последовательно, полный цикл
каждому; глубина ревью батча = МАКСИМУМ риска участников (`Review=full` у любого → весь батч на
его глубину, plan-protocol §9 «Батчинг подфаз»). Глубина reviewer-стадии одиночного item'а
следует колонке `Review` §3 (пусто → дефолт `full`, plan-protocol §9 «Адаптивная глубина ревью»).

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

`Blocked` и escalation — не реакция на signal. Снача воспроизведи минимальный signal,
классифицируй его и запиши nonterminal journal result: `routing-rejected`,
`decision-pending`, `local-repair` или `block-candidate`. Procedural/transient/tool-noise,
dependency-not-ready, unrelated-pre-existing и bounded local reversible defect автоматически
чинятся в том же attempt; `local-repair` не меняет status/attempt, после него
повторяется original Validation carrier.

Если остался material block candidate, собери closed `block-candidate/v1` capsule.
Для external-класса RAG обязателен в 100% случаев: `rag.status=verified` и непустые
digest-qualified `evidence_ids`; без этого action — `gather-rag`, а не stop. Затем ровно один
свежий reviewer в `isolated-child-return`, чьи actor/context отличаются от executor,
применяет `prompts/block-confirmation-rubric-v1.md`. Root валидирует capsule и вызывает
`task.plan_blocking.evaluate()`; reviewer даёт evidence, но не authorization. Только action
`terminal-block` после `JUSTIFIED` разрешает 🔴/escalation. `AVOIDABLE` → local repair,
`INSUFFICIENT_EVIDENCE` → сбор evidence, `OUT_OF_SCOPE|MALFORMED` → repair capsule; все три
ветки nonterminal и продолжают owning root.

1. **Порядок чтения — РОВНО такой, ничего сверх.** Сначала прочитай поле `Layout` в `## 0. Meta`;
   по дереву файлов раскладка НЕ выводится. `Layout` отсутствует → v1:
   1) `plans/<PLAN-ID>/plan.md` — Context, Execution Rules, **§3 Routing (читать ОБЯЗАТЕЛЬНО — п. 2)**,
      Status Board;
   2) `plans/<PLAN-ID>/handoff.md` — где мы;
   3) `plans/<PLAN-ID>/phases/Pn.md` — Phase Context + твой item Pn.m целиком;
   4) файлы из **Required Reads** item'а — в указанном порядке.
   `Layout: v2` → РОВНО пять обязательных слотов:
   1) `plans/<PLAN-ID>/plan.md` — identity, Context, Execution Rules и §3 Routing;
   2) `plans/<PLAN-ID>/phases/<Pn>/<Pn>.md` — только Phase Context;
   3) `plans/<PLAN-ID>/phases/<Pn>/<Pn.m>.md` — полное ТЗ выбранного item;
   4) `plans/<PLAN-ID>/bundles/<Pn.m>.json` — объявленные digest-qualified inputs;
   5) `plans/<PLAN-ID>/phases/<Pn>/<Pn.m>.state.md` — byte-fresh item state.
   В v2 `handoff.md` НЕ входит в обязательный путь: состояние выбранного item берётся только из
   свежего item state. Повторное чтение уже прочитанного ЗАПРЕЩЕНО (экономия контекста); «почитаю
   ещё по репо на всякий случай» — тоже. Всё нужное обязан нести план; не несёт — см. п. 5.

2. **Предусловия.** **Дом:** `## 0. Meta` несёт `Home: repo:<путь>`, а ты запущен НЕ в этом репо
   (в Brain/зеркале) — ошибка запуска: стоп и отчёт с правильным домом (голая команда перезапуска из
   `<путь>`); SSOT плана во время exec = репо, зеркало не исполняется (скилл `plan-protocol` §12).
   Статус item'а — `⬜ Not started` или `🟡 In progress`; иначе стоп и отчёт (терминальный item не
   переисполняется), **кроме bounded audit repair-forward**. Это исключение действует только когда
   фаза ещё не закрыта, последний `## Audit Pn` имеет `RED`/`ATTENTION`, его findings явно называют
   этот item, стабильное ТЗ item'а не изменено, а обязательный Pre-mutation ниже возвращает `allow`
   (`observed_rounds < audit_rounds_max`). Тогда это ровно один repair attempt под прежним ТЗ:
   journal start с новым attempt возвращает item в `🟡 In progress`; `plan-design`/реопен фазы не
   запускаются. После второго аудита Pre-mutation возвращает `LOOP_BUDGET_EXCEEDED`, поэтому третьего
   repair/audit цикла нет. **Phase-first:** item фазы N+1 не исполняется, пока фаза N не терминальна
   (все её items 🟢/🟠/⛔) — иначе стоп + отчёт, какая фаза держит.

   **Routing-гейт (ДО п. 3 — заблокированный item в 🟡 не остаётся).** Найди строку item'а в `plan.md`
   §3 Routing (секции/строки нет → дефолт SSOT-матрицы: `plan-exec` = implementation/medium). Колонка **Exec** —
   enum `plan-exec` | `manual` | `plan-design`; пуста → **деривация** по тир-порядку (модели `economy <
   implementation < frontier ≈ frontier`, effort `low < medium < high < xhigh < max`; недостающее в ячейке берётся из
   матрицы ролей скилла §9): `model ≤ implementation` И `effort ≤ medium` → `plan-exec`; `model > implementation` ИЛИ
   `effort > medium` → `manual`. Ветки:
   - `Exec = manual` (задан ИЛИ выведен) → item НЕ исполняется командой: СТОП, отчёт
     `ROUTING-BLOCKED: Pn.m — предписано <model/effort>, команда пинит implementation/medium`,
     launch-block формы «ЗАПУСК ВРУЧНУЮ» (п. 8). Статус item'а НЕ меняется.
   - `Exec = plan-exec`, Routing НИЖЕ пина (economy и/или low) → исполнять (перебор безвреден),
     process-отклонение — в Known Deviations; статус остаётся 🟢 (п. 7).
   - `Exec = plan-exec` ПРОТИВОРЕЧИТ model/effort (заполненная Exec перебивает деривацию только
     в сторону строгости) → СТОП, отчёт `ROUTING-INCONSISTENT: Pn.m — Exec=plan-exec при
     <model/effort>`; правит `plan-design`. Статус НЕ меняется.
   - `Exec = plan-design` → item не исполняется: СТОП, ре-дизайн (п. 5).
   - Routing неоднозначен (строки на item нет, «frontier ИЛИ frontier», проза без модели) И item —
     design/contract-класса (сработал бы любой триггер эскалации п. 5) → **СТОП. При сомнении —
     СТОП** (fail-safe: цена ложного стопа — перезапуск, цена ложного прохода — RED-аудит).
   Гейт — ЧТЕНИЕ §3 глазами, не парсинг (форм Routing во флоте много, regex запрещён). Разрешение
   владельца РЕПЛИКОЙ в чате гейт не снимает: оно выражается ЗАПИСЬЮ `Exec = plan-exec` в §3.

   **Pre-mutation — Task Contract (P2.7, ОБЯЗАТЕЛЬНЫЙ шаг, не условный).** Компилятор
   `packages/task/lib/task/task_contract.py` владеет precedence/conflict/hash/portability
   логикой (`task-contract-v1.md` §Pre-mutation predicate, 12 упорядоченных reason codes
   поверх `plan-portability-v1.md`) — эта команда его ЗОВЁТ, а не пересказывает логику
   второй прозой: собери контракт и проверь его ПЕРЕД ЛЮБОЙ мутацией, для КАЖДОГО item'а
   без исключения — условная формулировка F1 (шаг «если контракт где-то уже собран») и
   любой её синоним ЗАПРЕЩЕНЫ. CLI-форма `task_contract build` держит `route.actual`
   неразрешённым по конструкции (байт-детерминированность между процессами, докстринг
   модуля) — передать ей живой route нечем, флага нет; поэтому шаг зовёт тот же компилятор
   его же документированным Python API (`build(..., actual_route=…)` — тот же параметр,
   которым self-conformance P2.6 уже пользовался), а не переизобретает предикат вторым
   способом:

   ```
   PYTHONPATH="$(codex plugin marketplace list --json | python3 -c 'import json,sys,pathlib; data=json.load(sys.stdin); roots=[item["root"] for item in data.get("marketplaces", []) if item.get("name")=="swissknifeman" and (pathlib.Path(item["root"])/"packages/task/lib/task").is_dir()]; len(roots)==1 or sys.exit("task runtime unavailable: expected one marketplace root with packages/task/lib/task"); print(roots[0]+"/packages/task")')/lib" python3 - <<'PY'
   import sys
   from task import task_contract, route_evidence
   contract = task_contract.build("plans/<PLAN-ID>", "<Pn.m>", actual_route=route_evidence.capture_actual(
       "<provider-attested model_class>", "<provider-attested effort>",
       source="provider-doctor", model="<provider-attested model>"))
   result = task_contract.evaluate(contract)
   print(result)
   sys.exit(0 if result["pre_mutation"] == "allow" else 1)
   PY
   ```

   `<PLAN-ID>`/`<Pn.m>` — те же, что «$ARGUMENTS». Значения `actual_route` берутся ТОЛЬКО
   из provider-attested environment API; command pin/selector/actor не являются actual evidence.
   Если API не даёт модель или effort, вызови `capture_actual(None, None,
   source="self-attested")`, напечатай `unknown/unknown` и остановись до мутации: selector
   остаётся только частью fresh launch, а не подменой доказательства.
   **Зелёное:** `pre_mutation: 'allow'` (exit 0) — продолжай п. 3.
   **Отказ по коду** (`result["pre_mutation"]`, первый упавший — единственный):

   | Код | Класс | Действие |
   |:--|:--|:--|
   | `ROUTE_UNDERSHOOT` | реальный (route ниже required) | СТОП: гейт п. 2 уже обязан был это поймать раньше — расхождение прозы и компилятора = D#-запись + `ROUTING-INCONSISTENT` |
   | `AUTHORITY_BOUNDARY` | реальный (owner-gate не выдан) | СТОП: эскалация п. 5 (owner-gate) |
   | `LOOP_BUDGET_EXCEEDED` | реальный (финальный разрешённый аудит уже состоялся) | СТОП: `AUDIT-CAP`-путь, решение владельца; третий repair/audit не запускать |
   | `PORTABILITY_EXTERNAL_INPUT` / `PORTABILITY_INPUT_MISSING` | реальный (item несёт внешний/недостающий execution input) | СТОП: эскалация п. 5 (дефект спеки item'а), правит `plan-design` |
   | `VERSION_HASH_MISMATCH` / `CONFLICT_UNRESOLVED` / `CONFLICT_PRECEDENCE_VIOLATION` / `NEXT_CHANGED_WITHOUT_TRANSITION` / `CAPABILITY_UNSUPPORTED` / `SLICE_INCOMPLETE` / `COLD_START_INCOMPLETE` | структурный (`build()` этого не производит при корректной работе) | СТОП: D#-запись, реопен-кандидат P2.6 (владелец `build`), НЕ тихая правка здесь |

   Модуль `task.task_contract`/`task.route_evidence` недоступен (`ModuleNotFoundError` —
   standalone-раскладка вне монорепо, PYTHONPATH не резолвится) → СТОП с явным текстом «шаг
   недоступен: `task.task_contract` не импортируется» — fail-closed, а не «продолжай как
   раньше».

3. **До работы:** пометь `**Status:** 🟡 In progress` у item'а И строку в таблице
   `## Phase Status` (статусы — 6 канонических строк байт-в-байт, копируй из плана).
   **Журнал (D21, P1.1, хелпер `lib/task/journal.py`):** следом append старт-запись —
   сначала один раз получи observed `session_id` через `plan-session.py current --id` и вычисли
   `run_id = task.journal.derive_run_id(plan_id, item_id, attempt, session_id)`; затем
   `PYTHONPATH="$(codex plugin marketplace list --json | python3 -c 'import json,sys,pathlib; data=json.load(sys.stdin); roots=[item["root"] for item in data.get("marketplaces", []) if item.get("name")=="swissknifeman" and (pathlib.Path(item["root"])/"packages/task/lib/task").is_dir()]; len(roots)==1 or sys.exit("task runtime unavailable: expected one marketplace root with packages/task/lib/task"); print(roots[0]+"/packages/task")')/lib" python3 -m task.journal append --plan-dir plans/<PLAN-ID>
   --plan <PLAN-ID> --item <Pn.m> --command <plan-exec|plan-run — фактически вызванная
   команда> --actor <model>/<effort>
   --session-id <session_id> --run-id <run_id> --attempt <N> --result in-progress`
   (`<model>/<effort>` — модель/effort
   ЭТОГО исполнения: pinned implementation/medium у `plan-exec`, фактическая сессии у `plan-run`).
   Хелпера/каталога плана нет (standalone-раскладка вне монорепо) — предупреди и пропусти
   (не блокер, как `plan-lint`).

4. **Исполнение — СТРОГО в Scope Included.** Implementation Rules и Code Guidance item'а —
   жёсткие рамки, не рекомендации. Заметил «улучшить бы заодно» — запиши в **Pending Work**
   item'а, НЕ делай. Любой failure signal проходит `observe → minimal reproduce → classify → act → verify`.
   Procedural/transient/dependency-not-ready/unrelated-pre-existing остаются в том же attempt:
   safe fallback, локальная обратимая repair, bounded wait или независимое продолжение. Только
   воспроизведённые acceptance/safety/authority границы останавливают затронутый item. Recon/диагноз-deliverable item'а (если Deliverables
   его декларируют) кладётся в `plans/<PLAN-ID>/findings/<Pn>-<slug>.md`.

5. **Эскалация после block gate.** Material-триггеры (закрытый enum): многопакетный рефакторинг · неясная архитектура ·
   public contract/SemVer · protected generated assets · конфликт правил · неясные acceptance.
   Сам триггер создаёт `block-candidate`, но не блок. Только `task.plan_blocking` action
   `terminal-block` из раздела выше разрешает оставить ТРИ greppable-артефакта и остановиться:
   - blockquote в item: `> 🔴 ESCALATION Pn.m: <причина> | trigger: <из enum> | нужен: plan-design`;
   - `**Status:** 🔴 Blocked` у item'а (и в Phase Status) + `**Escalation Needed:** yes`;
   - **при `Closure Protocol | v1` (opt-in, D44/P8.3):** строка `Возобновление: <точная
     команда>` в **Pending Work** — точная команда, которой продолжится работа (обычно
     `$ task:plan-design <PLAN-ID> Pn.m`), а не «пропущено»; локального шага продолжения
     не существует в принципе (внешний блокер) → `Возобновление: — (внешний блокер:
     <что именно ждём>)`, выдумывать команду запрещено;
   - обнови `handoff.md` (Next: $ task:plan-design <PLAN-ID> Pn.m; причина — в Open risks);
   - финальная строка отчёта: `ESCALATION-REQUIRED: Pn.m — <причина>`.
   - **Журнал (D21, P1.1):** append финал-запись тем же вызовом, включая
     теми же `--session-id <session_id> --run-id <run_id> --attempt <N>`: `--result escalated --friction escalation
     --note "<причина эскалации, ≤1 строка>"` (те же `--plan-dir/--plan/--item/--command/--actor`,
     что старт-запись п. 3).

6. **Validation.** Прогони КАЖДУЮ команду из поля **Validation** item'а; зафиксируй результат
   (команда → passed/failed + суть вывода). Красное — чини в рамках Scope; не чинится в рамках —
   это `🟠 Done with deviations` с Known Deviations либо эскалация, НЕ молчаливый пропуск.
   **Всплывшая ошибка → фикс-предложение СРАЗУ (plan-protocol §8, C3/D6).** Material-остаток
   (Validation красная вне Scope, lint N−K>0, посторонний дифф, найденный дефект) — отчёт несёт
   конкретное remediation-предложение (что + launch-block под фикс + 1 строка «почему») ПОВЕРХ
   записи в Known Deviations/Pending Work, а не пассивное «готов к следующему, были ошибки».

7. **ЗАКРЫТИЕ ОБЯЗАТЕЛЬНО** — без него работа НЕ выполнена, даже если код написан.

   **Pre-final — Task Contract (P2.2/P2.11, ОБЯЗАТЕЛЬНЫЙ шаг, штатный путь — М5).** `plan-exec`
   закрывает item САМ (эта топология) — граница pre-final ОБЯЗАНА пересекаться ЗДЕСЬ, а не только
   в реконсилирующем `task:plan-close Pn.m`, который на штатном пути exec'а не вызывается. Маршрут
   `actual_route` — маршрут ИСПОЛНИТЕЛЯ item'а (D75), подтверждённый provider environment API;
   own pin/selector ЭТОЙ команды не заменяет это доказательство. Одна сборка контракта покрывает
   оба предиката, `evaluate()` считает их за один вызов:

   ```
   PYTHONPATH="$(codex plugin marketplace list --json | python3 -c 'import json,sys,pathlib; data=json.load(sys.stdin); roots=[item["root"] for item in data.get("marketplaces", []) if item.get("name")=="swissknifeman" and (pathlib.Path(item["root"])/"packages/task/lib/task").is_dir()]; len(roots)==1 or sys.exit("task runtime unavailable: expected one marketplace root with packages/task/lib/task"); print(roots[0]+"/packages/task")')/lib" python3 - <<'PY'
   import sys
   from task import task_contract, route_evidence
   contract = task_contract.build("plans/<PLAN-ID>", "<Pn.m>", actual_route=route_evidence.capture_actual(
       "<provider-attested model_class>", "<provider-attested effort>",
       source="provider-doctor", model="<provider-attested model>"))
   result = task_contract.evaluate(contract)
   print(result)
   sys.exit(0 if result["pre_mutation"] == "allow" and result["pre_final"] == "allow" else 1)
   PY
   ```

   **Гейт бинарен** (та же таблица код→действие, что `plan-close.md`'s Pre-final шаг 4): зелёное —
   РОВНО `pre_mutation == "allow"` И `pre_final == "allow"`; `n/a` и любой `block:*` — красное,
   item НЕ закрывается этим шагом (эскалация п.5 / D#-запись по классу кода — реальный vs
   структурный, та же таблица, что `plan-close.md`'s шаг 4). Как минимум ОДНО поле
   `Deliverables`/Validation обязано резолвиться в публично проверяемый факт (реальная команда,
   реальный вывод), не только внутренний byte/hash-green результат (D30) — это то, что
   `pre_final == "allow"` подтверждает машинно. **Граница предиката (D77, М3):** `pre_final`
   утверждает свойство ФОРМЫ спеки item'а (публично проверяемый acceptance на детерминированном
   классе доказательства), а НЕ то, что item исполнен ХОРОШО — вердикт material/process остаётся
   за status-rule ниже, этот код его не заменяет.

   Модуль `task.task_contract`/`task.route_evidence` недоступен (standalone-раскладка вне
   монорепо) → СТОП с явным текстом «шаг недоступен: `task.task_contract` не импортируется» —
   fail-closed.

   **Топология — ДВА коммита (единственная; шаги 1–6 строго в этом порядке):**
   1) **Item-коммит.** Дифф Scope (код/артефакты) ТОЛЬКО по путям `Files` item'а — файлы плана в него
      НЕ входят; `validate.sh` затронутого пакета зелёный ДО коммита; Conventional Commits (рус.)
      `тип(scope): суть (Pn.m)`; `git add <пути из Files>`. Внутри шага дифф может собираться
      НЕСКОЛЬКИМИ атомарными коммитами — item-коммит ЗАВЕРШАЮЩИЙ, ИМЕННО его хеш идёт в handoff
      (шаг 3). Фикс по ревью — коммит СВЕРХ топологии (не `amend`: трассируемость).
   2) **Bookkeeping плана.** `**Status:**` item'а → `🟢 Done` / `🟠 Done with deviations` (status-rule
      ниже) · **Completion Notes** — только факты (файлы, тесты, прогнанные команды и их вывод; без
      оценок «всё отлично») + **строка `write-site: pre_mutation: <код> · pre_final: <код>`** (D88/
      P10.1) — коды БЕРУТСЯ из результата шага 7 Pre-final выше (`result["pre_mutation"]`/
      `result["pre_final"]`), пишутся ЭТОЙ ОДНОЙ строкой (не прозой врассыпную — `plan_lint.py`
      матчит только её построчно), обязательна на закрытии `🟢`/`🟠` · **Pending Work** (из п. 4,
      или «—») · **Known Deviations** · строка в
      `## Phase Status` фазы · `## 4. Phase Index & Status Board` в `plan.md` (счётчик `Items 🟢/всего`,
      статус фазы) · строка в `## 6. Update Log` («Что» ≤ 2 строк, формат `<item> закрыт: <1 строка
      сути> — детали см. phases/Pn.md <item> Completion Notes`; пересказ Completion Notes ЗАПРЕЩЁН) ·
      **`Last Updated`** в `## 0. Meta` = дата закрытия item'а · **Журнал (D21, P1.1)**: append
      финал-запись (те же `--plan-dir/--plan/--item/--command/--actor/--session-id/--run-id`, что старт-запись п. 3)
      `--result <closed-green|closed-deviations — по статусу выше> --attempt <N — 1-based счётчик
      попыток ЭТОГО item'а> --friction <из закрытого списка §2.1: deviation при непустых Known
      Deviations, retry при attempt>1, no-op если прогон не сдвинул статус, иначе пусто> --note
      "<1 строка сути закрытия>"` — файл `journal.jsonl` входит в carve-out `plans/<PLAN-ID>/**`
      (коммитится тем же `git add plans/<PLAN-ID>` шага 6, отдельного коммита не даёт).
      Terminal append идемпотентен: повтор с тем же run/fingerprint возвращает существующий
      `journal.jsonl:<line>` и не добавляет вторую terminal строку.
   `--note` обязана быть не длиннее 300 символов: writer отказывает ДО записи; полный отчёт
      живёт в Completion Notes/findings. Historical long note не переписывается, а owner status
      проецирует её коротким указателем `journal.jsonl:<line>` (D141).

      **Layout v2 — производство закрытия (P6.2).** После каждого terminal journal event, но до
      lint'а, команда НЕ дописывает пять полей исхода или доску в item-spec: она запускает
      `plan-views.py state|status|decisions|closure|bundle`, затем `--check` каждого применимого
      генератора. Для закрывающегося producer запускается `plan-downstream.py --record` с хешем
      уже созданного item-коммита: `green`, `red` и `unknown` ВСЕГДА материализуются item-scoped
      finding'ом с парой `consumer_spec_sha256 × producer_commit`; `red` не закрывается. Перед
      terminal escalation записывается return-evidence с `new`/`repeat`/`unqualifiable`, причём
      `unqualifiable` не читается как `new`. `closure/<Pn>.json` пишется только при `Closure
      Protocol | v1`; генерируемый `<Pn>.closed.md` регенерируется всегда — это два разных
      носителя. При `Layout: v1` сохраняется прежний порядок этого шага дословно.

      **Contracts (§11).** Item, бампающий ЗАМОРОЖЕННЫЙ контракт (semver-bump секции `## 7.
      Contracts` донора — секция опознаётся по ЗАГОЛОВКУ, не по номеру; плана без неё правило не
      касается), В ТОМ ЖЕ bookkeeping-коммите обновляет: (а) строку `Exported` донора (Версия +
      Уведомлены); (б) строку `Consumed` КАЖДОГО плана-потребителя В ТОМ ЖЕ корне `plans/`
      (`Замечено` + `Реакция`) — обязанность адресована ИМЕННО item'у, не «плану вообще». Потребитель
      в ДРУГОМ репо линтером не проверяется: запись в `open-questions.md` донора + строка в Open
      risks его `handoff.md` (кросс-репо push — задача шины, mAInd, не plan-протокола).
   3) **Перезапись `handoff.md` целиком** (схема ниже). Хеш item-коммита handoff берёт ИЗ ШАГА 1 —
      коммит уже в истории (`git rev-parse --short HEAD`), поэтому хеш РЕАЛЬНЫЙ. Плейсхолдер
      вместо хеша (`<Pn.m>`, «TBD», пустая ячейка) — дефект, а не форма.
   4) **`python3 "$(codex plugin marketplace list --json | python3 -c 'import json,sys,pathlib; data=json.load(sys.stdin); roots=[item["root"] for item in data.get("marketplaces", []) if item.get("name")=="swissknifeman" and (pathlib.Path(item["root"])/"packages/task/lib/task").is_dir()]; len(roots)==1 or sys.exit("task runtime unavailable: expected one marketplace root with packages/task/lib/task"); print(roots[0]+"/packages/task")')/scripts/plan-lint.py" plans/<PLAN-ID> --baseline HEAD`** —
      ПОСЛЕ шага 3, на итоговом дереве. Прогон ДО перезаписи handoff ЗАПРЕЩЁН: закрывающий item сам
      меняет handoff, и счёт «до» не описывает состояние коммита. (Нет переменной/скрипта — предупреди.)
   5) **Счёт публикуется С АТРИБУЦИЕЙ:** `N ERROR / M WARN — новых от диффа item'а: K`
      (K — детерминированно: `--baseline HEAD`). • K > 0 — чинится ДО коммита bookkeeping'а;
      • N − K > 0 (остаточные ошибки плана вне Scope item'а) — НЕ замалчиваются: строка в Pending
      Work item'а + Open risks handoff'а. «Зелёный lint» гейта закрытия = **K = 0**, а не N = 0.
   6) **Bookkeeping-коммит:** `git add plans/<PLAN-ID> plans/ACTIVE.md` — только файлы плана.
   Item без диффа кода (Scope = сам план) идёт той же топологией: шаг 1 коммитит `Files` item'а,
   шаг 6 — бухгалтерию. Слить шаги 1 и 6 в один коммит (бандл) = process-отклонение: 🟢 + запись в
   Known Deviations + ЧИНЯЩИЙ коммит с реальным хешем в handoff (права на плейсхолдер бандл не даёт).

   **Коммит-гигиена.** `git add -A` и `git commit -a` ЗАПРЕЩЕНЫ: дерево может нести чужой дифф
   (владелец правит код параллельно) — он уедет в item-коммит незамеченным. Коммит собирается ПО ЯВНЫМ
   ПУТЯМ. Посторонний дифф исполнитель НЕ трогает (не коммитит, не стэшит, не ревертит, не «прибирает»)
   — он НАЗЫВАЕТ его в отчёте (п. 8). Carve-out: `plans/<PLAN-ID>/**` и `plans/ACTIVE.md` — штатная
   часть закрытия (шаг 6), в `Files` не перечисляются и посторонним диффом не считаются.

   **Status-rule.** Непустые Known Deviations САМИ ПО СЕБЕ статус item'а НЕ меняют.
   `🟠 Done with deviations` ОБЯЗАТЕЛЕН при **material**-отклонении (любое из): Scope Included выполнен
   не полностью или иначе, чем предписано · Validation осталась красной · затронут public contract /
   SemVer / замороженный контракт СВЕРХ ТЗ item'а · acceptance-критерий не выполнен · принят workaround,
   который ЖИВЁТ В КОДЕ/артефакте (а не в процессе исполнения) · item-коммит несёт дифф вне `Files`
   item'а (считается только по НЕплановым путям — carve-out выше), верен сам дифф или нет.
   `🟢 Done` сохраняется при **process**-отклонении, но запись в Known Deviations ОБЯЗАТЕЛЬНА: перебор
   тира (исполнено моделью/effort ВЫШЕ предписанных Routing), бандлинг коммитов, порядок правок,
   стилистика отчёта. Тихое умолчание = дефект (находка аудита).
   Дефект САМОГО ТЗ (правило ТЗ ошибочно или невыполнимо) — тоже НЕ отклонение исполнителя: он
   эскалирует (п. 5: конфликт правил / неясные acceptance), владелец или `plan-design` вносит новый D#
   и СИНХРОНИЗИРУЕТ Scope Included item'а с решением; закрытие идёт по ОБНОВЛЁННОМУ ТЗ → 🟢 + запись в
   Known Deviations (что изменено, каким D#). Правка ТЗ по ходу БЕЗ D# — material-отклонение (scope
   drift), даже если результат «лучше». **Routing-adherence:** недобор модели/effort снят гейтом п. 2
   (структурно невозможен), остаётся ПЕРЕБОР — та же запись (`исполнено <факт> вместо <из Routing>`).

   **Якорь дерева для чисел.** Любое ЧИСЛО в Completion Notes / Validation / Known Deviations /
   Update Log (счётчик `grep`, число ERROR/WARN, коммитов, файлов) приводится с якорем дерева:
   `<число> (на <git-ref>)` — и с командой, которой получено. Якорь чисел о диффе Scope — **item-коммит**
   (шаг 1; bookkeeping его не меняет); чисел о файлах ПЛАНА (грепы по `phases/Pn.md`, счёт lint) —
   **bookkeeping-коммит** (шаг 6): считай на дереве, которое КОММИТИШЬ (после `git add` правок шагов
   2–3), а не на дереве момента написания. Число без якоря либо не воспроизводимое своей же командой
   на закоммиченном дереве = **ложное утверждение**, даже если в момент написания было верным.

   **Схема `handoff.md`** (шаг 3): `# HANDOFF — <ISO-дата> — after Pn.m`, затем **Next:** (launch-block
   п. 8 — таблица `Batch / Model / Thinking / Context / Суть` + голая команда ИЛИ голый промпт отдельным
   code-block'ом, копипаст без правок; самодостаточен из холодной сессии: plan-ID + cold-start reads;
   скелет — `snippets/launch-block-template.md` скилла) / **Done:** / **Remaining:** / **Sources of
   truth:** / **Open risks:** / **Workarounds/Deferred/Open questions:** (workarounds · deferred ·
   open_questions; «—» если нет).

8. **Terminal delivery receipt — до `final`, без исключений.** После terminal journal
   append, persisted state и перезаписи `handoff.md` выполни
   `python3 "$(codex plugin marketplace list --json | python3 -c 'import json,sys,pathlib; data=json.load(sys.stdin); roots=[item["root"] for item in data.get("marketplaces", []) if item.get("name")=="swissknifeman" and (pathlib.Path(item["root"])/"packages/task/lib/task").is_dir()]; len(roots)==1 or sys.exit("task runtime unavailable: expected one marketplace root with packages/task/lib/task"); print(roots[0]+"/packages/task")')/scripts/plan-delivery.py" --plan-dir plans/<PLAN-ID>
   --subject <Pn.m> --kind terminal`. Код `FINAL_BEFORE_TERMINAL_FORBIDDEN`, missing/stale
   journal/state/handoff или ненулевой exit запрещают `final`: диспатч остаётся активным
   и возвращается в repair/reconciliation. В `final` выведи строку
   `Delivery receipt: <compact JSON>` и отдельно `Рекомендация следующего шага:` с exact
   `recommendation` из receipt; сокращённое «Next Pn.m» не заменяет persisted recommendation.

9. **Expected output — фиксированный формат (по блоку на item):**
   ```
   ### Pn.m — <Title>
   Status: 🟢 Done | 🟠 Done with deviations | 🔴 Blocked
   Completed: <что сделано, 1–3 строки>
   Pending Work: <…|—>
   Files Changed: <список путей>
   Commits: <item-коммит: hash — subject; bookkeeping: hash — subject>
   Validation: passed|failed — <команды и суть>
   Lint: N ERROR / M WARN — новых от диффа item'а: K
   Посторонний дифф в дереве: <файлы> | нет
   Known Deviations: <…|—>
   Escalation Needed: no|yes (тогда финальная строка ESCALATION-REQUIRED: …)
   Launch-block (следующий шаг):
   | Параметр | Значение |
   |:--|:--|
   | Batch | <stable ID из Routing / solo> |
   | Model | <implementation|frontier|economy|frontier> |
   | Thinking | <effort> — <причина в 3–8 слов> |
   | Context | <РОВНО одно из трёх значений enum'а ниже> |
   | Суть | <1 строка: что делает следующий шаг> |
   | Команда | `<голая команда>` — ТОЛЬКО сама команда, без повторного `select the session model class`/`select the session effort` |

   <опционально, ТОЛЬКО когда следующий шаг реально отличается от того, что строка `Команда`
   способна выразить (Exec = manual — нет single-command эквивалента, scope-payload
   находок/реопена, форма ОЖИДАНИЕ — guard-строка): голый промпт ИЛИ полная команда с
   scope-payload — ОТДЕЛЬНЫМ code-block'ом, копипаст без правок>
   ```
   При `ROUTING-BLOCKED` / `ROUTING-INCONSISTENT` (п. 2) блок несёт ТОЛЬКО эту строку + launch-block:
   работа не начиналась, статуса/коммитов/lint'а нет.

   **Material-остаток → фикс-предложение, не только Known Deviations (plan-protocol §8, C3/D6).**
   Непустые `Known Deviations`/остаточный `N−K>0` — отчёт называет конкретный фикс (что чинит) и,
   когда этот фикс — самое ценное следующее действие, **Launch-block ниже указывает на него**
   (`$ task:plan-design <ID> Pn.m` ре-дизайн либо follow-up fix-item), а не молча на следующий item.

   **Launch-block** — не статичный шаблон, а разовая оценка СЛЕДУЮЩЕГО шага по факту его текста в
   `phases/Pn.md` (уже прочитан в п. 1), `plan.md` §3 Routing И `plans/<PLAN-ID>/roadmap.md`
   (SKILL §8): launch-block всегда показывает `Batch`; если roadmap существует и следующий шаг
   входит в batch/workflow-группу —
   launch-block несёт КОМАНДУ ГРУППЫ (`$ task:plan-run <ID> Pn.a-Pn.b` / `native orchestration carrier for the referenced plan-owned workflow script`),
   а не одиночный item. После закрытия item команда сохраняет тот же Batch и адресует только
   оставшийся adjacent-суффикс; расхождение roadmap↔Routing — эскалация, не молчаливый выбор:
   - Следующий item, `Exec = plan-exec` → строка `Команда` = `$ task:plan-exec <PLAN-ID> Pn.k`
     (весь ответ, code-block не заводится); Model/Thinking — из Routing (дефолт `implementation/medium`).
   - Следующий item с **`Exec = manual`** (§9 скилла) → форма **«ЗАПУСК ВРУЧНУЮ»**: `Next` =
     `«ЗАПУСК ВРУЧНУЮ: <model/effort>»`; `Model`/`Thinking` — **предписанные Routing**, НЕ
     implementation/medium; строка `Команда` = `—` (нет single-command эквивалента); code-block
     ОБЯЗАТЕЛЕН (не опционален для этого случая) и несёт **ГОЛЫЙ ПРОМПТ item'а** (копипаст без
     правок), а НЕ slash-команду (`$ task:plan-exec` пинит implementation/medium и по гейту п. 2 обязан
     такой item отклонить — команда в code-block'е была бы инструкцией нарушить гейт); `Context` =
     `continue-root`. Либо: `select session model class <M>` + `select session effort <E>` + `$ task:plan-run <ID>
     Pn.m` (D18) — тем же обязательным code-block'ом (три строки не умещаются в ячейку таблицы).
   - Следующая фаза ещё скелет (16 полей не заполнены) → `$ task:plan-design <PLAN-ID> Pn`, не
     `plan-exec` (упадёт на предусловии). Если текущая фаза терминальна, НЕ используй
     `plan-close` как пробную команду: вычисли `phase_candidate_fingerprint(...)`, затем единый
     `task.plan_gates.phase_audit_policy(..., candidate_snapshot=candidate["snapshot"])`.
     `audit_required=true` → `audit-phase: task:plan-audit <PLAN-ID> Pn`;
     `audit_required=false` → `close: task:plan-close <PLAN-ID> Pn`. Handoff обязан копировать
     `next_exact` и сохранить `code` политики; свободная оценка объёма или отклонений поверх
     результата запрещена.
   - **`Context` — РОВНО одно из ТРЁХ значений** (`plan-protocol` §8): `continue-root`
     (authoritative root продолжает в текущем бюджете/capabilities) · `isolated-child-return`
     (bounded reviewer/worker возвращает evidence; root остаётся authoritative) ·
     `cold-start-root` (root не может безопасно продолжить; указывается ровно один canonical
     reason). Тип команды сам по себе не является основанием для cold start.
