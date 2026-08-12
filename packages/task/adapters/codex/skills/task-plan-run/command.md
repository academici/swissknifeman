<!-- Generated Codex runtime projection; do not edit as source.
Canonical source: packages/task/commands/plan-run.md
Canonical SHA-256: sha256:cc5d7077a56446dbd4d5c0c2c697181a0b8869cc7d2a227479ab74eba7fbeda1
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

## Codex current-route binding — provider-specific

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
command below. Its fresh-native-only wording constrains the `cli-flag` compatibility fallback;
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

Наследуй `plan-exec.md` Continue-first block gate без ослаблений: signal снача становится
nonterminal `routing-rejected|decision-pending|local-repair|block-candidate`; малый reversible
дефект автофиксится и original Validation повторяется. Material-кандидат перед
любым 🔴 проходит closed `block-candidate/v1` → verified RAG для 100% external-случаев
→ ровно один отличный от executor reviewer в `isolated-child-return` →
`task.plan_blocking.evaluate()`. Только `terminal-block` после `JUSTIFIED` разрешает
Blocked/escalation; любой другой action продолжает repair/evidence в owning root.

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

Прочти `packages/task/commands/plan-exec.md` ЦЕЛИКОМ и исполни его пункты 1–8 ДОСЛОВНО,
с ТРЕМЯ отличиями:

- Модель/effort НЕ запинены: действуют настройки сессии владельца.
- **Pre-mutation/Pre-final write-site (D24).** `plan-run` принимается только в свежем Codex
  thread, созданном ровно native launch-block из текущего handoff: `-m <model-selector>` и
  `-c 'model_reasoning_effort="<effort-selector>"'` обязаны покрывать минимум §3 Routing.
  В оба вызова НЕ переписывай selector/effort из памяти или handoff: получи один typed record
  через `task.route_evidence_codex.capture_current(expected_invocation="$ task:plan-run
  <arguments>", expected_cwd="<repo-cwd>")`. Adapter идёт по ancestor process chain до
  owning Codex process, читает его исходный argv, сверяет exact Task prompt/cwd/`-a never`/
  `-s danger-full-access`, резолвит `-m`/`model_reasoning_effort` через committed
  `command-routing.json` и связывает запись с provider session identity; его record уже несёт concrete
  selector как `model` и `source="cli-flag"`. Ошибка `ROUTE_LAUNCH_UNAVAILABLE|MISMATCH` —
  nonterminal route-evidence gap до product journal start, а не повод подставить config/doctor
  либо фабриковать undershoot. Это **launch provenance**, а не thread telemetry: не называй его
  provider-attested actual route, не читай private rollout и не подставляй `config.toml`, actor
  или свободную самоаттестацию. После `select the session model class` или иной смены маршрута thread нельзя продолжать
  item: запусти новый native block до journal start.
  Шаг остаётся обязательным в обеих точках `plan-exec.md`; `plan-run` меняет только разрешённый
  источник для fresh-session launch provenance, не условия предиката.
- Routing-гейт п.2 сверяет launch-provenance модель/effort с §3 Routing item'а (тир-порядок —
  plan-protocol §9). Недобор → ДО product journal start допиши provenance-event
  `--result routing-rejected --friction routing-blocked` (он не state transition и не attempt),
  напечатай exact native launch-block и останови только текущий dispatch; product status
  не меняется. Перебор → исполнять, запись в
  Known Deviations (§6 `plan-exec.md`). Exec = plan-design → СТОП, ре-дизайн.
  Routing reject до product work никогда не создаёт `blocked|escalated`: route correction —
  durable dispatch evidence, а не исход продукта.

**Граница честности.** `cli-flag` доказывает выбранные параметры свежего native запуска, а не
наблюдает фактический runtime thread. Документированного programmatic current-thread API с обеими
осями в Codex нет; поэтому `plan-run` не требует несуществующий provider probe и не выдаёт
launch provenance за telemetry. Если требуется independently observed runtime route, используй
строгий `plan-exec` с provider-attested source. `plan-run` не принимает config, actor, текст
прошлого handoff или самоаттестацию как substitute для текущего fresh native launch.

Всё остальное (эскалация, validation, топология закрытия, status-rule, якорь дерева,
launch-block) — БЕЗ ИЗМЕНЕНИЙ из `plan-exec.md`; повторно здесь не транскрибируется
(правило двух SSOT).

Каждая journal-запись, которую `plan-run` наследует из `plan-exec.md`, передаёт тот же
`--session-id "$(python3 packages/task/scripts/plan-session.py current --id)"`; resolver обязан
найти ровно один provider adapter, иначе append не выполняется. Это provider-neutral правило:
raw runtime identity принадлежит только adapter'у, а не canonical command. Перед start вычисли
`run_id = task.journal.derive_run_id(plan_id, item_id, attempt, session_id)` и передай тот же
непустой `--run-id` в start и terminal; повторный terminal close возвращает существующий pointer
и не дописывает journal.
