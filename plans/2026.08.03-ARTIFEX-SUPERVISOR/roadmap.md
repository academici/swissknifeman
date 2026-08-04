# Roadmap исполнения — 2026.08.03-ARTIFEX-SUPERVISOR

**Обновлён:** 2026-08-04 · **Соответствует plan.md:** v0.10.5 · **Статус:** P1.6/P2.6 и
фазы P1/P2 терминальны; P3 терминальна с deviations: D80 устранил no-tool conflict, а D81
разделил immutable P2 snapshot и additive current P3 snapshot без изменения D74/D77.
Следующий шаг — независимый audit P3; provider readiness остаётся non-green evidence с нулевой
активностью и не ослабляет runner/evidence acceptance.

## Immediate P3 audit

**Next:** audit-phase: task:plan-audit 2026.08.03-ARTIFEX-SUPERVISOR P3

| Параметр | Значение |
|:--|:--|
| Model class | frontier |
| Effort | xhigh |
| Capabilities | repository-plan-read · evidence-audit · provider-adapter review |
| Context | cold-start — plan-step |
| Суть | Независимо проверить P3 closure и честность provider/P1.6 deviations |
| Команда | `$ task:plan-audit 2026.08.03-ARTIFEX-SUPERVISOR P3` |

```text
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c model_reasoning_effort="xhigh" -a never -s danger-full-access

$ task:plan-audit 2026.08.03-ARTIFEX-SUPERVISOR P3
```

## Карта исполнения

Все 35 items имеют `Exec = manual`: effort `high`/`xhigh` выше жёсткого пина `plan-exec`, а
contract/security/recovery/public-package классы требуют full review. Батчей и workflow-групп нет:
каждая фаза — последовательная producer chain. Терминальные items ниже не имеют runnable launch;
текущий путь исполнения начинается с независимого аудита P3.

| Item | Batch | Запуск | Model class/Effort | Гейт владельца | Примечание |
|:--|:--|:--|:--|:--|:--|
| P0.1 | terminal | 🟢 Done | frontier/high | — | baseline/reuse freeze закрыт; Task authority prerequisite terminal |
| P0.2 | terminal | 🟢 Done | frontier/high | — | owner mandate/authority cases закрыты |
| P0.3 | terminal | 🟢 Done | implementation/high | — | provider probe matrix закрыта |
| P0.4 | terminal | 🟢 Done | frontier/high | — | threat/pre-mortem freeze закрыт |
| P0.5 | terminal | 🟢 Done | frontier/high | — | acceptance rubric закрыт |
| P1.1 | terminal | 🟢 Done | frontier/high | — | frozen `supervisor-run-v1` |
| P1.2 | terminal | 🟢 Done | frontier/high | — | frozen `slice-manifest-v1` |
| P1.3 | terminal | 🟢 Done | frontier/high | — | frozen `authority-policy-v1` |
| P1.4 | terminal | 🟢 Done | frontier/high | — | frozen `worker-envelope-v1` |
| P1.5 | terminal | 🟢 Done | frontier/high | — | frozen `economy-evidence-v1` and original aggregate |
| P1.6 | terminal | 🟢 Done | frontier/high | D74 recorded | frozen additive admission contract and separate provider-specific no-write task/grant carriers |
| P2.1 | terminal | 🟢 Done | implementation/high | — | terminal compiler/source reconciliation |
| P2.2 | terminal | 🟢 Done | implementation/high | — | terminal durable store |
| P2.3 | terminal | 🟢 Done | implementation/high | — | terminal authority evaluator |
| P2.4 | terminal | 🟢 Done | implementation/high | — | terminal scheduler and D70 budget transition |
| P2.5 | terminal | 🟢 Done | implementation/high | — | terminal provider-free CLI/aggregate |
| P2.6 | terminal | 🟢 Done | implementation/high | — | terminal two-provider smoke manifest→grant→replay→admissions and provider-free dispatch seam |
| P3.1 | terminal | 🟢 Done | implementation/high | — | terminal pure Codex mapper |
| P3.2 | terminal | 🟢 Done | implementation/high | — | terminal pure Claude Code mapper |
| P3.3 | terminal | 🟢 Done | implementation/high | — | terminal two-provider parity freeze |
| P3.4 | terminal | 🟠 Done with deviations | implementation/high | — | D80 native-tool projection/refusal + D81 historical-P2/current-P3 manifest proof; P1.6 provenance and provider readiness are explicit non-green follow-up evidence |
| P4.1 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P4.1` | implementation/high | — | six-contract admission/dispatch fault matrix and injector freeze |
| P4.2 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P4.2` | implementation/high | — | dispatch-aware no-rerun recovery; consumes P4.1 |
| P4.3 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P4.3` | implementation/high | — | linked-worktree integration; consumes recovery |
| P4.6 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P4.6` | implementation/high | D79 exact scoped repair | one worktree-local hook repair plus exact GREEN recheck; no package-source edit |
| P4.4 | solo | `waiting: P4.6 terminal GREEN → manual: implementation/high` | implementation/high | — | independently recheck hook GREEN, then task/admission/authority/privacy security evidence |
| P4.5 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P4.5` | implementation/high | — | owner/telemetry and admission-aware assurance aggregate |
| P5.1 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P5.1` | frontier/high | `G-OWNER-P5-BUSINESS` after request/catalog hashes | freeze trials/shadow; pause for owner hash-bound dispatch grant; produce all per-trial admissions before close |
| P5.2 | solo | `waiting: P5.1 terminal with business admission index → manual: implementation/high` | implementation/high | consumes `G-OWNER-P5-BUSINESS` only through P5.1 carriers | reversible live three-slice pilot; P3 smoke inputs refuse |
| P5.3 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P5.3` | implementation/high | consumes indexed business admissions | recovery/provider-failure pilot; no local mint/reset |
| P5.4 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P5.4` | frontier/high | business admissions required; `G-OWNER-P5.4-SINGLE` only for single-provider GO | five candidate admissions + paired economics; verdict grant never authorizes dispatch |
| P6.1 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P6.1` | frontier/high | `G-OWNER-P6.1-PACKAGE` and/or `G-OWNER-P6.1-ROUTER` only when selected | product-home authority freeze; absent grant selects refusal |
| P6.2 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P6.2` | implementation/high | consumes exact terminal P6.1 grant when selected | branch-locked integration or roadmap return |
| P6.3 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P6.3` | implementation/high | — | GO operations or bounded NO-GO zero-surface evidence |
| P6.4 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P6.4` | frontier/xhigh | — | distinct cold independent audit |

## Последовательность successor-contract remediation

1. P1.6 and P2.6 are terminal; P1/P2 are closed.
2. P3.4 and P3 are terminal; run `$ task:plan-audit 2026.08.03-ARTIFEX-SUPERVISOR P3` before P4.1.
3. Execute P4.1→P4.2→P4.3→P4.6→P4.4→P4.5, then P5–P6 sequentially.

### P3 — closed phase awaiting independent audit

**Next:** audit-phase: task:plan-audit 2026.08.03-ARTIFEX-SUPERVISOR P3

| Параметр | Значение |
|:--|:--|
| Model class | frontier |
| Effort | xhigh |
| Capabilities | repository-plan-read · evidence-audit · provider-adapter review |
| Context | cold-start — plan-step |
| Суть | Проверить P3 evidence, deviations и closure перед P4 |
| Команда | `$ task:plan-audit 2026.08.03-ARTIFEX-SUPERVISOR P3` |

```text
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c model_reasoning_effort="xhigh" -a never -s danger-full-access

$ task:plan-audit 2026.08.03-ARTIFEX-SUPERVISOR P3
```

## Authority Gate Contract

Только следующие четыре маркера являются новыми owner grants этого плана. Проверяемый carrier —
более поздняя, чем D64, строка Decision Log в `plan.md`, которая дословно содержит указанный
`[OWNER-GRANT:<gate-id>]`, называет разрешённую ветвь и scope, ссылается на явное сообщение
repository owner и не отозвана более поздним D#. D74/D75 и команды `finish`/audit не являются
ни одним из этих grants.

| Gate ID | Защищённый переход | Exact predicate | Без carrier |
|:--|:--|:--|:--|
| `G-OWNER-P5-BUSINESS` | P5.1 материализует grants/admissions для P5.2–P5.4 | строка D# позже D78 содержит marker, SHA-256 `trial-catalog-v1.json` и `business-grant-request-v1.json`, exact providers/roots/max-dispatches/per-trial caps, explicit owner source; D78 itself is not a grant | P5.1 pauses after proposal hashes; no business admission/provider call |
| `G-OWNER-P5.4-SINGLE` | P5.4 выпускает single-provider `GO` | exact marker разрешает named provider/scope | single-provider GO запрещён; two-provider/NO-GO остаётся legal |
| `G-OWNER-P6.1-PACKAGE` | P6.1 выбирает `artifex-package` | exact marker разрешает sixth package и finite scope | branch refuses before terminalization |
| `G-OWNER-P6.1-ROUTER` | P6.1 ставит `root_router=approved` | exact marker отдельно разрешает root group/launcher scope | `root_router=unchanged` |

Provider readiness, terminal validators, security/hook integrity and literal GREEN независимого
design audit остаются evidence gates: D# не заменяет отсутствующее или non-green доказательство.
Tag/push/publish/release не входят в roadmap и требуют отдельного позднего разрешения.

## Завершённый package prerequisite

`artifacts/design/task-authority-carrier-01.md` имеет `State: terminal`, а независимый reviewer
сохранил literal GREEN. Этот prerequisite уже потреблён terminal P0.1 и не имеет runnable launch в
текущем roadmap. Исторические producer/reviewer attempts остаются в carrier/review evidence; они не
повторяются после D75.
