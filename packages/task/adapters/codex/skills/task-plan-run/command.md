<!-- Generated Codex runtime projection; do not edit as source.
Canonical source: packages/task/commands/plan-run.md
Canonical SHA-256: sha256:128990b1688a079d35e4aca5cfa7b44f0ffe5a89cb64a64252cf6374ccc4057f
Adapter: task.codex-command/1.0.10
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

## Codex current-route binding — provider-specific

Before the first product-journal mutation, capture the effective route for this exact command:

```bash
export TASK_CODEX_ROUTE_EVIDENCE="$(PYTHONPATH="$(codex plugin marketplace list --json | python3 -c 'import json,sys,pathlib; data=json.load(sys.stdin); roots=[item["root"] for item in data.get("marketplaces", []) if item.get("name")=="swissknifeman" and (pathlib.Path(item["root"])/"packages/task/lib/task").is_dir()]; len(roots)==1 or sys.exit("task runtime unavailable: expected one marketplace root with packages/task/lib/task"); print(roots[0]+"/packages/task")')/lib"   python3 -m task.route_evidence_codex capture   --expected-invocation '$ task:plan-run <arguments>' --expected-cwd <repo-cwd>)"
```

Replace `<arguments>` and `<repo-cwd>` with the exact current invocation payload and repository
cwd. A non-zero exit is `ROUTE-UNVERIFIABLE`; do not start or mutate the product item.

For Codex, `task.route_evidence_codex.capture_current(...)` resolves the current
`CODEX_THREAD_ID` first and validates the latest provider-written `turn_context`: concrete
model, reasoning effort, cwd, approval policy, sandbox policy, and the exact current Task
prompt. The resulting actual-route record carries `source="provider-thread-state"` and
`source_version="codex-turn-context-v1"`.

This path is valid both after a full native launch and after the Codex clear command, which
starts a fresh chat inside the same CLI process. A model or reasoning change before product
journal start is therefore checked from the current chat state, never from stale process argv.
If persisted thread state is genuinely absent, exact ancestor argv remains a compatibility
fallback with `source="cli-flag"`. Malformed/mismatched thread state fails closed; config,
doctor output, actor prose, and self-attestation remain forbidden substitutes.

This provider binding defines how Codex satisfies the D24 write-site checks in the canonical
command below. The projected contract snippets consume exactly
`json.loads(os.environ["TASK_CODEX_ROUTE_EVIDENCE"])`; do not recreate route evidence from
placeholders, `codex doctor`, configuration, or agent prose. Its fresh-native-only wording constrains the `cli-flag` compatibility fallback;
its private-rollout prohibition forbids manual probing but not this validated adapter-owned
read; neither rule prohibits a verified cleared chat or overrides current `turn_context`
evidence.

Это ИСПОЛНЕНИЕ item'а мастер-плана под моделью сессии (D18) — третий режим `plan-exec`,
БЕЗ пина `model`/`effort`: они наследуются из настроек текущей сессии владельца.
Ввод пользователя: «$ARGUMENTS».

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

**Путь чтения делегируемого item.** Сначала прочитай поле `Layout` в `## 0. Meta`;
исполняется только явный `Layout | v2` (отсутствующий или `v1` возвращает
`PLAN_LAYOUT_V1_RETIRED`). РОВНО пять обязательных слотов:

1. `plans/<PLAN-ID>/plan.md` — identity, Context, Execution Rules и §3 Routing;
2. `plans/<PLAN-ID>/phases/<Pn>/<Pn>.md` — только Phase Context;
3. `plans/<PLAN-ID>/phases/<Pn>/<Pn.m>.md` — полное ТЗ выбранного item;
4. `plans/<PLAN-ID>/bundles/<Pn.m>.json` — объявленные digest-qualified inputs;
5. `plans/<PLAN-ID>/phases/<Pn>/<Pn.m>.state.md` — byte-fresh item state.

В v2 `handoff.md` НЕ входит в обязательный путь: состояние выбранного item берётся только из
fresh item state. Повторное чтение запрещено.

Разреши источник через
`task.command_catalog.package_command_path("task:plan-exec")`, прочти возвращённый canonical
`plan-exec.md` ЦЕЛИКОМ и исполни его пункты 1–8 ДОСЛОВНО,
с ТРЕМЯ отличиями:

- Модель/effort НЕ запинены: действуют настройки сессии владельца.
- **Pre-mutation/Pre-final write-site (D24).** `plan-run` принимается только при provider-bound
  evidence текущего Task invocation. В обеих точках вызови provider-neutral
  `task.route_evidence.capture_launch(expected_invocation="task:plan-run <arguments>",
  expected_cwd="<repo-cwd>")`; provider выбирается из session identity, а raw state читает только
  additive adapter. Codex adapter проверяет native argv (`-C`, `-m`, effort, `-a never`,
  `-s danger-full-access`) и связывает `cli-flag` provenance с owning thread. Claude Code adapter
  выбирает ровно JSONL текущего `CLAUDE_CODE_SESSION_ID`, находит exact `<command-name>` +
  `<command-args>` и берёт concrete model/effort/cwd из route-bearing assistant event после него.
  Ни один adapter не имеет fallback на config, actor, handoff prose или самоаттестацию.
  Ошибка `ROUTE_LAUNCH_UNAVAILABLE|ROUTE_LAUNCH_MISMATCH` и любой unknown axis означают
  `ROUTE-UNVERIFIABLE`: это nonterminal route-evidence gap до product journal start, а не
  undershoot и не `blocked`.

  Перед start построй `route-run-receipt/v1` через `task.route_evidence.build_run_receipt(...)`,
  передай `task.route_evidence.start_decision(receipt)` как decision той же `in-progress` записи.
  Перед terminal append заново загрузи receipt из journal по `run_id`, повтори `capture_launch()`
  и вызови `verify_run_receipt(..., current_evidence=<fresh>)`. Несовпавшие model/effort/thread/
  cwd/invocation либо истёкший receipt запрещают terminal append и требуют fresh dispatch; смена
  маршрута внутри run никогда не маскируется новым receipt.
- Routing-гейт п.2 сверяет launch-provenance модель/effort с §3 Routing item'а (тир-порядок —
  plan-protocol §9). Недобор → ДО product journal start допиши provenance-event
  `--result routing-rejected --friction routing-blocked` (он не state transition и не attempt),
  напечатай exact provider launch-block и останови только текущий dispatch; product status
  не меняется. Перебор → исполнять, запись в
  Known Deviations (§6 `plan-exec.md`). Exec = plan-design → СТОП, ре-дизайн.
  Routing reject до product work никогда не создаёт `blocked|escalated`: route correction —
  durable dispatch evidence, а не исход продукта.

**Граница честности.** Codex `cli-flag` доказывает параметры свежего native запуска, Claude Code
`provider-thread-state` — route-bearing event текущей provider-сессии. Оба являются provenance
с явно названной силой, а не взаимозаменяемой telemetry. Canonical команда принимает только общий
record contract и не читает provider-private формат напрямую.

Всё остальное (D24 same-root audit-fixer, эскалация, validation, топология закрытия, status-rule, якорь дерева,
launch-block) — БЕЗ ИЗМЕНЕНИЙ из `plan-exec.md`; повторно здесь не транскрибируется
(правило двух SSOT).

Каждая journal-запись, которую `plan-run` наследует из `plan-exec.md`, передаёт тот же
`--session-id "$(python3 packages/task/scripts/plan-session.py current --id)"`; resolver обязан
найти ровно один provider adapter, иначе append не выполняется. Это provider-neutral правило:
raw runtime identity принадлежит только adapter'у, а не canonical command. Перед start вычисли
`run_id = task.journal.derive_run_id(plan_id, item_id, attempt, session_id)` и передай тот же
непустой `--run-id` в start и terminal; повторный terminal close возвращает существующий pointer
и не дописывает journal.
