# Уточнения владельца

## 2026-07-22 — bounded D104 live-admission repair design

- Owner invoked exactly: `task:plan-design 2026.07.19-DUAL-PROVIDER P6` in bounded repair
  design mode.
- Input is limited to the P6.8 live-preflight finding and D103/D104 transfer records.
- The session must explain the non-green no-write result and specify only the owning P2/P5/P6
  route. It must not execute package repair, live apply/repair, P7.2 rerun, P7.3+, FOREMAN,
  fleet, tag or push, and must not begin P6 close/audit.

RAG:— (owner-grounded: exact invocation and scope payload 2026-07-22).

## 2026-07-22 — D103 bootstrap-transfer design approval

- Owner approved exactly: `APPROVE D103 P2/P5/P6 BOOTSTRAP-TRANSFER DESIGN AS WRITTEN; AUTHORIZE ONLY A BOUNDED REMEDIATION PLAN, NOT LIVE APPLY OR P7.3+`.
- Authority covers only re-design of the owning P2/P5/P6 remediation chain and its plan
  carriers. It does not authorize package-source implementation, a live apply/repair,
  P7.3+, FOREMAN, fleet, tag or push.
- The live inventory remains closed: root `.codex/hooks.json` is SHA-256
  `7d7538d021228e8e61d124f4b60b6db04434f8121de30b8672f05e4bf038c3db`,
  `.codex/hooks/lifecycle.py` is missing and the live P2 lock record is absent.

RAG:— (owner-grounded: exact approval in this session 2026-07-22; repo-grounded:
`research/23-p7.2-live-preflight-remediation-design.md`).

## 2026-07-22 — D104 bootstrap-transfer implementation approval

- Owner approved exactly: `APPROVE D104 BOOTSTRAP-TRANSFER IMPLEMENTATION AS WRITTEN IN research/23 § Candidate Owner Decision D104; RUN P2.6→P5.8→P6.7→P6.8 SEQUENTIALLY; NO LIVE APPLY/REPAIR, P7.2 RERUN, P7.3+, FOREMAN, FLEET, TAG OR PUSH`.
- The authorization freezes only the D104 candidate in `research/23`: P2 contract `1.2.0`,
  exact admission/preimage/backup/rollback and the sequential package-source ownership.
- P2/P5/P6 may use disposable roots and no-write checks as specified. Any live apply/repair,
  P7.2 rerun, P7.3+, FOREMAN, fleet, tag or push remains outside authority.

RAG:— (owner-grounded: exact approval in this session 2026-07-22; repo-grounded:
`research/23-p7.2-live-preflight-remediation-design.md`).

## 2026-07-19 — синтаксис запуска task-команд в ChatGPT/Codex

- В текущей ChatGPT/Codex surface task-команда запускается через `$ task:plan-design …`:
  после символа `$` обязателен пробел. Рекомендация в Claude-форме `/task:plan-design …`
  здесь приводит к сообщению «команда не найдена».
- Финальные рекомендации и `handoff.md`, адресованные текущей Codex-сессии, должны давать
  копируемую команду в форме `$ task:…`. Внутренний semantic command ID не меняется.
- Долгоживущий provider-neutral command/invocation contract проектируется в P4; P3 отвечает
  только за доставку skill/plugin identity и не переписывает task semantics.

RAG:— (owner-grounded: прямое уточнение владельца в сессии 2026-07-19).

## 2026-07-20 — автономное contract-preserving продолжение active plan

- Для активного `2026.07.19-DUAL-PROVIDER` формальный Owner Approval не является паузой,
  если решение evidence-backed, сохраняет frozen contracts и остаётся в уже объявленном scope.
- Агент фиксирует такое решение в D-log/plan carriers и продолжает execution; эскалирует только
  изменение frozen contract, расширение authority или genuine owner-level fork.

RAG:— (owner-grounded: прямое распоряжение владельца в текущей сессии 2026-07-20).

## 2026-07-19 — границы design-захода P4

- Детализировать только P4; соседние фазы не разворачивать.
- Package code в design-заходе не исполнять.
- `plans/2026.07.18-FOREMAN` и fleet не менять.

RAG:— (owner-grounded: прямое ограничение запуска P4 в сессии 2026-07-19).

## 2026-07-19 — границы design-захода P5

- Детализировать только P5; P6/P7 и соседние фазы не разворачивать.
- Cold-start источниками считать явно переданный набор plan/P4/P5/brief/research/contracts;
  read-only recon `packages/harness` допустим только для конкретизации design.
- Package code/items не исполнять; допустимы только правки plan artifacts и plan-lint.
- `plans/2026.07.18-FOREMAN`, `plans/ACTIVE.md`, root bootstrap surfaces и fleet не менять.

RAG:— (owner-grounded: прямое ограничение запуска P5 в сессии 2026-07-19).

## 2026-07-19 — границы design-захода P6

- Детализировать только P6; P7 и соседние фазы не разворачивать.
- Cold-start источниками считать явно переданный набор plan/P5/P6/brief/research/contracts;
  read-only recon `packages/maind`, `packages/analyst`, `core` и current harness run-report
  допустим только для конкретизации исполняемого design.
- Package code/items в design-заходе не исполнять; допустимы только чтение, правки plan
  artifacts и plan-protocol bookkeeping/plan-lint.
- `plans/2026.07.18-FOREMAN`, `plans/ACTIVE.md`, root bootstrap surfaces и fleet не менять.

RAG:— (owner-grounded: прямое ограничение запуска P6 в сессии 2026-07-19; допустимый
read-only recon вытекает из требования детализировать executable P6 без исполнения code).

## 2026-07-19 — границы design-захода P7 и roadmap/model correction

- Детализировать только P7; package code/items не исполнять, FOREMAN/fleet не менять.
- Cold-start источниками считать явно переданный набор plan/P6/P7/brief/research/contracts.
- Полная детализация P7 завершает все фазы, поэтому создать `2026.07.19-DUAL-PROVIDER/roadmap.md`
  по каноническому формату; `plans/2026.07.18-FOREMAN/roadmap.md` использовать только как
  read-only образец и не изменять.
- Routing и roadmap должны называть подходящие актуальные модели ChatGPT/Codex как
  исполнителей плана, а не Claude model names.
- Для финального cross-phase design/verification использовать мощный ChatGPT/Codex tier:
  GPT-5.6 Sol с xhigh reasoning; prescribed implementation направлять на GPT-5.6 Terra.

RAG:— (owner-grounded: прямые уточнения владельца в сессии 2026-07-19). Актуальная
model-family проверена отдельно в `findings/P7-openai-model-routing-2026-07-19.md`.

## 2026-07-19 — границы finish design pass 3/3

- Выполнить финальный cross-phase reconcile P0–P7 по явно переданному cold-start набору:
  plan/roadmap, все phase files, brief и ключевые research syntheses.
- Сверить phase contracts, конечность/порядок Required Reads, per-item Routing и owner gates;
  завершить design pass 3/3 и подготовить следующий независимый design audit.
- Package code/items не исполнять; допустимы только plan artifacts, bookkeeping,
  verification capture и plan-lint.
- `plans/2026.07.18-FOREMAN/**` и fleet не менять.

RAG:— (owner-grounded: прямой запуск `task:plan-design 2026.07.19-DUAL-PROVIDER finish`
в сессии 2026-07-19).

## 2026-07-19 — remediation после RED design-аудита

- `AGENTS.md` должен быть семантическим Codex-аналогом `CLAUDE.md` на root и package
  уровнях. Оба представления строятся из общего канона правил; байтовая идентичность
  не требуется, provider-specific additions разрешены как явные extensions.
- Нужен исполнимый carrier общего instruction contract: canonical source, root/package
  projections, managed sections, extensions, provenance/source hash и gates semantic
  parity/drift/repair/backward compatibility.
- Механизм должен быть создан в P5/P6; P7 только проверяет self-host, cleanup и release.
- Restart durability трассируется на фактические P6.5/P6.6 carriers, не P6.4.
- Journal остаётся append-only: старые строки не переписываются, незавершённые lifecycle
  pairs получают terminal backfill/correction records.
- В этом remediation package code/items, package tests и plan-lint не запускаются;
  без нового anchored plan-lint нельзя заявлять GREEN. FOREMAN, ACTIVE и fleet не менять.

RAG:— (owner-grounded: прямой remediation-запуск после audit-red 2026-07-19).

## 2026-07-19 — remediation повторного design audit, F1 journal lifecycle

- Режим — remediation audit-r2, не execution; первым входом является
  `findings/design-audit-2026-07-19-r2.md` F1.
- Owner-gated устранить противоречие append-only history и strict per-line schema;
  выбрать исполнимую нециклическую correction/supersession semantics либо явное
  provenance-preserving exception.
- Синхронизировать journal writer/schema/linter/plan lifecycle и получить current anchored
  `0 ERROR / 0 WARN`; затем подготовить новый design audit, не запускать P0.1.
- Не менять P0.1–P7.4 implementation/items, `plans/2026.07.18-FOREMAN/**`, `plans/ACTIVE.md`,
  fleet и unrelated changes; instruction remediation P5.6→P7 не менять, кроме journal-gate ссылок.

RAG:— (owner-grounded: прямой запуск remediation audit-r2 2026-07-19).

## 2026-07-20 — точечная remediation design audit r3, F1 same-plan invariant

- Режим — remediation audit-r3, не execution; первым входом является
  `findings/design-audit-2026-07-19-r3.md` F1.
- Связать event и exception `plan_id` с canonical ID текущего plan directory в writer и
  linter; mismatch остаётся non-exemptable ERROR и не подавляется sidecar.
- Добавить writer/linter negative tests для foreign event/sidecar IDs и exact field-set;
  воспроизвести current `0 ERROR / 0 WARN` и wrong-plan nonzero.
- Lifecycle canon/research/D# синхронизировать только при изменении contract; подготовить
  новый design audit без запуска P0.1.
- Не менять P0.1–P7.4 implementation/items, package seams вне task journal/linter/tests и
  plan-protocol journal lifecycle, FOREMAN, ACTIVE, fleet, instruction remediation P5.6→P7
  и unrelated user changes.

RAG:— (owner-grounded: прямой запуск remediation audit-r3 2026-07-20).

## 2026-07-20 — substantive approval P1.1 provider-config F1–F6

- Владелец дал точный ответ `APPROVE P1.1 PROVIDER-CONFIG F1-F6 AS WRITTEN`.
- Approval атомарно принимает весь F1–F6 set candidate SHA-256
  `3ecc108a41ee111c79dbd792ecb45fabfe63024981db724233feefabc1f0c2c3`; partial approval
  или содержательная редакция не подразумеваются.
- Решению назначен D70; contract замораживается как v1.0.0. Разрешены только lifecycle
  freeze metadata и plan carriers, утверждённые F1–F6 bytes остаются неизменными.
- D70 открывает P1.2 против frozen input, но не разрешает P1.2 implementation внутри P1.1,
  provider output/live carrier writes, FOREMAN, fleet или dirty main changes.

RAG:— (owner-grounded: exact substantive approval в сессии 2026-07-20; repo-grounded:
`root/contracts/provider-config-contract.md`, `plan.md` D70).

## 2026-07-20 — remediation prerequisite P0.2, command-surface inventory

- P0.1 ошибочно сузил command-surface inventory до 11 файлов
  `packages/task/commands/*.md`.
- Pass-1 число 32 воспроизводится точно как top-level package command surfaces:
  task 11 + skiller 5 + harness 6 + maind 8 + analyst 2.
- Историю terminal P0.1 сохранить; до freeze P0.2 добавить отдельный исполняемый correction
  carrier.
- После carrier согласовать glossary/scenario wording и owner gate с различием общего
  Command Surface и package-specific Task Command.

RAG:— (owner-grounded: прямой escalation/remediation-запуск 2026-07-20).

## 2026-07-20 — Codex harness modes и project rollout

- Codex-настройки не должны оставаться разовым ручным bootstrap-файлом: канонический writer
  принадлежит `harness`, как и существующая раскатка настроек Claude Code.
- Общий profile catalog обязан независимо моделировать trust, approval policy и sandbox
  boundary, а provider adapters — материализовать полные нативные конфиги Claude Code/Codex.
- Оператор явно выбирает режим проекта. Минимальная матрица должна покрывать controlled,
  autonomous workspace и trusted full-access; последний для Codex означает
  `approval_policy = "never"` + `sandbox_mode = "danger-full-access"`.
- Выбранный режим распространяется штатными `harness`/umbrella
  `integrate|onboard|sync` operations на явно выбранные проекты, с dry-run/check/repair,
  идемпотентностью, provenance и сохранением user-owned секций.
- Для self-hosted `swissknifeman` целевой bootstrap — trusted full-access без запросов.
  Для fleet нет неявного наследования full-access: каждый project selection остаётся явным.
- P5 производит profile catalog и оба provider-native renderer'а; P6 подключает их к
  onboard/sync, P7 проверяет live self-host. Отдельный обходной writer создавать нельзя.

RAG:— (owner-grounded: прямое уточнение владельца в сессии 2026-07-20).

## 2026-07-22 — P7 item-by-item Codex launch console

- P6 завершена и не переоткрывается; следующий execution scope — только P7.
- P7.1–P7.4 выполняются как четыре отдельные Codex-сессии с моделью
  и effort из Routing; одна долгая Sol-сесия и generic subagents запрещены.
- После GREEN каждого item executor обязан закончить отчёт точной следующей
  copy-paste командой из `roadmap.md`: native `/clear`, новый routed Codex process,
  semantic `$ task:...`, model и effort.
- Внутри-item owner gate не открывает новую сессию: executor доводит isolated
  evidence до готового exact D#, выдаёт одну точную approval-строку и продолжает
  тот же item после ответа владельца.
- Все item пишут последовательно в cumulative `codex/p7-integration`; dirty root, P6,
  FOREMAN, fleet, unrelated projects и push не затрагиваются.

RAG:— (owner-grounded: требование item-by-item запуска с `/clear`, model/effort и
следующей командой; repo-grounded: `plan.md` §3 Routing, `phases/P7.md`).

## 2026-07-22 — обязательная новая сессия на каждый item P7

- Рабочий маршрут касается только P7.1–P7.4; закрытые predecessor phases не являются
  предметом повторного дизайна, исполнения или аудита.
- Каждый item P7 запускается отдельной полной shell-командой `codex ...` в новом процессе;
  `resume --last`, продолжение в текущем чате и автоматический переход без новой команды
  не считаются новой сессией.
- После terminal GREEN исполнитель не запускает successor сам: финальный ответ обязан
  предложить полный copy-paste launch-block следующего item с cwd, model, effort,
  approval и sandbox. После P7.4 аналогично предлагается отдельная команда P7 close;
  после close — следующий разрешённый GREEN-gated маршрут.
- Owner gate внутри P7.2/P7.3/P7.4 остаётся внутри соответствующей item-сессии:
  новая сессия нужна между items, а не между подготовкой exact approval и ответом владельца.

RAG:— (owner-grounded: прямое требование владельца 2026-07-22; repo-grounded:
`plan.md` §3 Routing, `phases/P7.md`, `roadmap.md`).

## 2026-07-22 — redesign P7.1 после docs-generator escalation

- Владелец запустил `task:plan-design 2026.07.19-DUAL-PROVIDER P7.1` после terminal
  escalation второго execution-attempt: named manifest-backed docs render/check operation
  отсутствует, а ручная capability matrix запрещена.
- Redesign обязан сохранить frozen P0–P6 contracts и устранить корень конфликта, а не
  разрешить hand-authored README или генерацию support truth из actual provider outputs.
- Package implementation в этой design-сессии не выполняется; разрешены только plan
  artifacts, journal bookkeeping и plan-lint. FOREMAN, fleet, live self-host и push остаются
  вне scope.

RAG:— (owner-grounded: semantic invocation 2026-07-22; repo-grounded:
`phases/P7.md` P7.1 escalation, `journal.jsonl`,
`findings/P7.1-capability-manifest-gap-2026-07-22.md`).

## 2026-07-22 — P7.2 post-P6 Owner Approval boundary

- После D107 не переоткрывать P6 и не перекладывать на владельца mechanics, уже
  делегированные D66/D79.
- Свести остаточный P7.2 blocker к двум реальным authority-осям: project provider selection
  и ownership существующего live `.mcp.json`.
- Дать минимальные alternatives, рекомендацию, exact scope/anti-scope и literal Owner reply;
  смешанные варианты, не открывающие P7.2, назвать явно.
- До ответа выполнять только plan-design/bookkeeping: не запускать P7.2, package source/tests,
  provider config/artifacts, apply/repair/rollback, P7.3+, FOREMAN, fleet, tag или push.

RAG:— (repo-grounded: D66/D79/D102–D107,
`research/24-d104-live-admission-repair-design.md`, `phases/P6.md` Audit attempt 4).

## 2026-07-22 — standing delegation resolves P7.2 S1+O1

- Владелец уточнил постоянное правило для AI-пакета: если рекомендованный выбор логически
  определён, contract-preserving, reversible/design-only и уже внутри plan scope, агент
  принимает и записывает его сам, не заставляя владельца повторять approval literal.
- Правило durably stored in mAInd scope `project:swissknifeman` as
  `mem_mrwffj6x_4e58b0e7e65d`; оно явно выбирает рекомендованный `S1+O1` для P7.2 и не
  разрешает live apply/repair/rollback, fleet, FOREMAN, tag, push или anti-scope expansion.
- D108 therefore supersedes the exact-literal wait and the pre-approval sentence “P6 не
  переоткрывается”. Owning seams are reopened explicitly and sequentially: P2.7, then
  P6.11→P6.12, separate close/fresh audits, then a fresh P7.2 rerun.
- Эта сессия materializes plan design only; package source, live config/artifacts, AGENTS,
  FOREMAN, fleet, ACTIVE, tag and push remain untouched.

RAG:— (owner-grounded: mAInd memory `mem_mrwffj6x_4e58b0e7e65d`; repo-grounded: D79,
`research/{25-p7.2-owner-authority-boundary,26-p7.2-s1-o1-remediation-design}.md`).

## 2026-07-22 — D111 accepts GREEN P2 audit-cap result

- Fresh independent Audit P2 attempt 5 returned substantive `GREEN` on committed anchor
  `224f1688`; audit artifact commit is `f9f168a8`.
- Under the standing delegation `mem_mrwffj6x_4e58b0e7e65d`, the logically determined
  audit-cap choice is to accept terminal P2 and continue the already approved D108 route,
  not stop the plan.
- This removes only the satisfied P2 predecessor block from P6.11. It does not authorize
  live config/artifact mutation, P7.2, FOREMAN, fleet, tag or push.

RAG:— (owner-grounded: standing delegation; repo-grounded: final Audit P2 block,
`224f1688`, `f9f168a8`, D108 roadmap).
