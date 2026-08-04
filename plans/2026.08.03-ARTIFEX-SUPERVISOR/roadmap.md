# Roadmap исполнения — 2026.08.03-ARTIFEX-SUPERVISOR

**Обновлён:** 2026-08-04 · **Соответствует plan.md:** v0.9.7 · **Статус:** P0/P1/P2.1–P2.4 terminal;
D70's frozen breaker transition is implemented without changing P1 bytes. Следующий запуск —
`$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P2.5` в implementation/high session.

## Карта исполнения

Все исходные 32 items сохраняют `Exec = manual`: effort `high`/`xhigh` превышает минимум
`plan-exec`, а contract/security/recovery/public-package классы требуют full review. Батчей и
workflow-групп нет: фазы — последовательные producer chains, а объединение full-review items в
одну skip-confirmation сессию запрещено plan-protocol. Вне item count есть один обязательный
package prerequisite carrier — `artifacts/design/task-authority-carrier-01.md`; он ремонтирует
write-site, от которого зависят все 32 item, но не является Artifex product deliverable.

| Item | Batch | Запуск | Model class/Effort | Гейт владельца | Примечание |
|:--|:--|:--|:--|:--|:--|
| P0.1 | solo | `waiting: latest Audit design verdict = GREEN AND TASK-AUTHORITY-CARRIER-01 State = terminal → manual: frontier/high` | frontier/high | — | exact two-conjunct structural wait; no runnable bypass; baseline/reuse spec and deliverable unchanged |
| P0.2 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P0.2` | frontier/high | — | compiles already-frozen D4–D6; grants no new authority |
| P0.3 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P0.3` | implementation/high | — | provider auth/readiness is a non-waivable evidence prerequisite |
| P0.4 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P0.4` | frontier/high | — | ecosystem-core threat model; consumes P0.1–P0.3 |
| P0.5 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P0.5` | frontier/high | — | compiles already-frozen D14/D25 rubric; changing it needs a later D# |
| P1.1 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P1.1` | frontier/high | — | public durable-state contract; first contract producer |
| P1.2 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P1.2` | frontier/high | — | public slice contract; consumes P1.1 |
| P1.3 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P1.3` | frontier/high | — | authority contract/security boundary; consumes P1.2 |
| P1.4 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P1.4` | frontier/high | — | provider-neutral public envelope; consumes P1.2/P1.3 |
| P1.5 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P1.5` | frontier/high | — | economy/privacy plus aggregate contract freeze |
| P2.1 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P2.1` | implementation/high | — | D69 test-only terminal-fixture repair; preserve production compiler and P2.3 scope |
| P2.2 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P2.2` | implementation/high | — | durable store/lock/replay; consumes P2.1 |
| P2.3 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P2.3` | implementation/high | — | authority evaluator/security boundary; consumes P2.1/P2.2 |
| P2.4 | solo | terminal `a94e4877` | implementation/high | — | D70 scheduler/reconcile/budget mapping over frozen `budget_exhausted`; P1 bytes unchanged |
| P2.5 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P2.5` | implementation/high | — | aggregate prototype CLI/manifest; consumes whole P2 chain |
| P3.1 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P3.1` | implementation/high | — | provider readiness is evidence; current Codex mapper and empirical boundary |
| P3.2 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P3.2` | implementation/high | — | provider readiness is evidence; current Claude mapper follows P3.1 seam |
| P3.3 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P3.3` | implementation/high | — | two-provider conformance; consumes both adapters |
| P3.4 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P3.4` | implementation/high | — | process/timeout/privacy runner and aggregate adapter gate |
| P4.1 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P4.1` | implementation/high | — | independent fault matrix and injector freeze |
| P4.2 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P4.2` | implementation/high | — | no-rerun reconcile/idempotency; consumes P4.1 |
| P4.3 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P4.3` | implementation/high | — | Git worktree/integration/rollback boundary; consumes recovery |
| P4.4 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P4.4` | implementation/high | — | hook integrity GREEN is non-waivable evidence; consumes integrated candidate |
| P4.5 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P4.5` | implementation/high | — | owner queue/telemetry and exact assurance aggregate |
| P5.1 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P5.1` | frontier/high | — | irreversible trial/baseline/order freeze |
| P5.2 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P5.2` | implementation/high | — | provider readiness is evidence; exact reversible live three-slice pilot |
| P5.3 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P5.3` | implementation/high | — | composed recovery/provider-failure pilot; consumes P5.2 |
| P5.4 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P5.4` | frontier/high | `G-OWNER-P5.4-SINGLE` only for single-provider GO | five-pair economic adjudication; ordinary two-provider/NO-GO branch needs no grant |
| P6.1 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P6.1` | frontier/high | `G-OWNER-P6.1-PACKAGE` and/or `G-OWNER-P6.1-ROUTER` only when selected | product-home/authority freeze; absent grant selects refusal, never implied approval |
| P6.2 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P6.2` | implementation/high | consumes the exact terminal P6.1 grant carrier when selected | branch-locked integration or roadmap return; creates no new grant |
| P6.3 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P6.3` | implementation/high | — | GO operations or bounded NO-GO zero-surface evidence; consumes P6.2 |
| P6.4 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P6.4` | frontier/xhigh | — | distinct cold independent audit; never co-session with P6.2/P6.3 |

## Готовые launch-block'и первого producer и P0.1

### TASK-AUTHORITY-CARRIER-01 — обязательный package prerequisite

Полный executable contract, owned surface, acceptance matrix и terminal predicate находятся в
`artifacts/design/task-authority-carrier-01.md`. После design GREEN producer создаёт только scoped
implementation commit и `ready-for-review` evidence; он не меняет `State`. P0.1 не является его
заменой.

**Next:** manual: implementation/high

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | high |
| Capabilities | repository-code-edit · task-contract-evaluate · provider-artifact-regenerate |
| Context | cold-start — plan-step |
| Суть | Устранить foreign-D50 fail-open в Task, доказать positive/negative и ordinary 32-build cases, затем передать независимому reviewer |
| Команда | — |

```text
codex -C /home/vostrikov/projects/packages/swissknifeman/packages/task -m gpt-5.6-terra -c model_reasoning_effort="high" -a never -s danger-full-access

$ task:dev /home/vostrikov/projects/packages/swissknifeman/plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/design/task-authority-carrier-01.md

РЕЖИМ: отдельный implementation/high producer prerequisite, НЕ Artifex item execution и НЕ terminal review
ВХОД: абсолютный carrier path выше; /home/vostrikov/projects/packages/swissknifeman/plans/2026.08.03-ARTIFEX-SUPERVISOR/plan.md D64–D66 и последний Audit design (заход 3); AGENTS.md от repo root до packages/task
СКОУП: исполнить Required repair и Acceptance matrix; создать scoped implementation commit; записать hash и exact producer results только в Producer evidence при State=waiting; вернуть exact reviewer/terminalizer launch из carrier, не исполняя его в этой сессии
НЕ ТРОГАТЬ: State; Independent verification; task-authority-carrier-01-review.md; P0.1–P6.4 statuses/deliverables; Artifex product implementation; unrelated dirty worktree; provider/pilot/hook/package-home/docs/fleet/Brain/release state
```

### TASK-AUTHORITY-CARRIER-01 — независимый reviewer/terminalizer

Запускать только после `Producer evidence: ready-for-review`. Это отдельная cold session;
producer не может вызвать её как self-review/subagent и не может писать GREEN/RED evidence.

**Next:** manual: frontier/xhigh

| Параметр | Значение |
|:--|:--|
| Model class | frontier |
| Effort | xhigh |
| Capabilities | repository-read · adversarial-code-review · task-contract-evaluate · plan-evidence-write |
| Context | cold-start — plan-step |
| Суть | Независимо перепроверить commit, durable-записать GREEN/RED и terminalize только на полном GREEN |
| Команда | — |

```text
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c model_reasoning_effort="xhigh" -a never -s danger-full-access

TASK-AUTHORITY-CARRIER-01 REVIEW/TERMINALIZE

РЕЖИМ: отдельный cold frontier/xhigh reviewer/terminalizer; Task implementation read-only
ВХОД: plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/design/task-authority-carrier-01.md Producer evidence и implementation commit; plans/2026.08.03-ARTIFEX-SUPERVISOR/plan.md D64–D66 и последний Audit design (заход 3); plans/2026.08.03-ARTIFEX-SUPERVISOR/roadmap.md; packages/task/AGENTS.md; packages/task/configs/command-routing.json
СКОУП: независимо повторить полный terminal predicate; всегда записать committed task-authority-carrier-01-review.md с literal GREEN/RED; RED оставляет State=waiting и возвращает producer launch; только полный GREEN позволяет reviewer'у обновить Independent verification и State=terminal; P0.1 не запускать
НЕ ТРОГАТЬ: packages/task implementation/generated artifacts; Producer evidence; P0.1–P6.4 statuses/deliverables; Artifex product implementation; unrelated dirty worktree; provider/pilot/hook/package-home/docs/fleet/Brain/release state
```

### P0.1 — structural waiting

**Next:** waiting: latest Audit design verdict = GREEN AND TASK-AUTHORITY-CARRIER-01 State = terminal → manual: frontier/high

| Параметр | Значение |
|:--|:--|
| Model class | frontier |
| Effort | high |
| Capabilities | repository-plan-read · evidence-recompute |
| Context | same-session — item |
| Суть | После обоих structural gates выполнить неизменённый P0.1; provider-native launch создаёт отдельную routed session |
| Команда | — |

```text
# НЕ раньше: latest Audit design verdict = GREEN AND TASK-AUTHORITY-CARRIER-01 State = terminal
$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P0.1
```

## Authority Gate Contract

Только следующие три маркера являются новыми owner grants этого плана. Проверяемый carrier —
более поздняя, чем D64, строка Decision Log в `plan.md`, которая дословно содержит указанный
`[OWNER-GRANT:<gate-id>]`, называет разрешённую ветвь и scope, ссылается на явное сообщение
repository owner и не отозвана более поздним D#. Текущий remediation-запрос разрешает только
редактирование дизайна и не является ни одним из этих grants.

| Gate ID | Защищённый переход | Exact predicate | Без carrier |
|:--|:--|:--|:--|
| `G-OWNER-P5.4-SINGLE` | P5.4 выпускает single-provider `GO` | exact `[OWNER-GRANT:G-OWNER-P5.4-SINGLE]` D# разрешает named provider/scope | single-provider GO запрещён; two-provider/NO-GO adjudication остаётся legal |
| `G-OWNER-P6.1-PACKAGE` | P6.1 выбирает `artifex-package` | exact `[OWNER-GRANT:G-OWNER-P6.1-PACKAGE]` D# разрешает sixth package и его finite scope | branch refuses before terminalization; `roadmap-only|task-extension|harness-extension` сохраняются |
| `G-OWNER-P6.1-ROUTER` | P6.1 ставит `root_router=approved` | exact `[OWNER-GRANT:G-OWNER-P6.1-ROUTER]` D# отдельно разрешает root group/launcher scope | `root_router=unchanged`; package grant не подразумевает router grant |

P0.2 и P0.5 компилируют уже зафиксированные D4–D6/D14/D25 и не расширяют authority; изменение
их правил всё равно требует нового owner D#, но штатное исполнение неизменённой спецификации — не
новый grant. Provider auth/readiness, terminal producer validators, security/hook integrity и
literal GREEN независимого design-аудита — evidence gates: D# не может заменить отсутствующее или
не-green доказательство.

### Fail-closed prerequisite Task carrier

D64 defect имеет один owning carrier: `artifacts/design/task-authority-carrier-01.md`. Его
`State: terminal` означает не обещание, а committed Task repair, removal чужого D50, exact
positive/negative authority cases, обычные 32/32 Artifex builds без foreign provenance, package
validation и literal GREEN в committed `task-authority-carrier-01-review.md`. Producer не вправе
менять `State`/review evidence, reviewer не вправе чинить Task implementation. Пока хотя бы один
terminal conjunct отсутствует, carrier остаётся `waiting`; пока latest Audit design не GREEN ИЛИ
carrier не terminal, P0.1 остаётся exact `waiting:` выше. Ручная подстановка kwargs, этот текст,
один только audit GREEN и synthetic D# не terminalize carrier и не открывают execution.

Tag/push/publish/release остаются вне roadmap и требуют отдельного позднего разрешения после
terminal P6 и release audit.
