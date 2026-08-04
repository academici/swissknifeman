# Roadmap исполнения — 2026.08.03-ARTIFEX-SUPERVISOR

**Обновлён:** 2026-08-04 · **Соответствует plan.md:** v0.10.3 · **Статус:** post-D76
audit remediation F1–F3 завершена по D77–D79. Последний design audit RED предшествует этим
исправлениям и не разрешает исполнение; следующий шаг — новый cold design audit. После его literal
GREEN первым producer остаётся P1.6.

## Immediate design-audit gate

**Next:** audit-design: task:plan-audit 2026.08.03-ARTIFEX-SUPERVISOR design

| Параметр | Значение |
|:--|:--|
| Model class | frontier |
| Effort | xhigh |
| Capabilities | plan-audit · adversarial-design-review |
| Context | cold-start — plan-step |
| Суть | Независимо проверить post-D79 35-item smoke/business-admission/hook topology, DoR и roadmap перед P1.6 |
| Команда | `$ task:plan-audit 2026.08.03-ARTIFEX-SUPERVISOR design` |

```text
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c model_reasoning_effort="xhigh" -a never -s danger-full-access

$ task:plan-audit 2026.08.03-ARTIFEX-SUPERVISOR design
```

## Карта исполнения

Все 35 items имеют `Exec = manual`: effort `high`/`xhigh` выше жёсткого пина `plan-exec`, а
contract/security/recovery/public-package классы требуют full review. Батчей и workflow-групп нет:
каждая фаза — последовательная producer chain. Терминальные items ниже не имеют runnable launch;
новый путь исполнения начинается только с P1.6 после design GREEN.

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
| P1.6 | solo | `waiting: latest Audit design after D79 verdict = GREEN → manual: frontier/high` | frontier/high | D74 recorded | freeze separate no-write smoke task/grant carriers and additive admission contract; then close P1 |
| P2.1 | terminal | 🟢 Done | implementation/high | — | terminal compiler/source reconciliation |
| P2.2 | terminal | 🟢 Done | implementation/high | — | terminal durable store |
| P2.3 | terminal | 🟢 Done | implementation/high | — | terminal authority evaluator |
| P2.4 | terminal | 🟢 Done | implementation/high | — | terminal scheduler and D70 budget transition |
| P2.5 | terminal | 🟢 Done | implementation/high | — | terminal provider-free CLI/aggregate |
| P2.6 | solo | `waiting: P1.6 terminal AND P1 closed → manual: implementation/high` | implementation/high | — | materialize two provider-specific smoke manifest→grant→replay→admissions plus provider-free dispatch; then close P2 |
| P3.1 | terminal | 🟢 Done | implementation/high | — | terminal pure Codex mapper |
| P3.2 | terminal | 🟢 Done | implementation/high | — | terminal pure Claude Code mapper |
| P3.3 | terminal | 🟢 Done | implementation/high | — | terminal two-provider parity freeze |
| P3.4 | solo | `waiting: P2.6 terminal AND P2 closed → manual: implementation/high` | implementation/high | — | implement write-heavy runner, then consume only two indexed no-write smoke admissions; after completion close P3 |
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

1. Fresh `$ task:plan-audit 2026.08.03-ARTIFEX-SUPERVISOR design` returns literal GREEN.
2. Execute P1.6, then `$ task:plan-close 2026.08.03-ARTIFEX-SUPERVISOR P1`.
3. Execute P2.6, then `$ task:plan-close 2026.08.03-ARTIFEX-SUPERVISOR P2`.
4. Execute P3.4, then `$ task:plan-close 2026.08.03-ARTIFEX-SUPERVISOR P3`.
5. Execute P4.1→P4.2→P4.3→P4.6→P4.4→P4.5, then P5–P6 sequentially.

### P1.6 — first producer after design GREEN

**Next:** waiting: latest Audit design after D79 verdict = GREEN → manual: frontier/high

| Параметр | Значение |
|:--|:--|
| Model class | frontier |
| Effort | high |
| Capabilities | repository-plan-read · contract-freeze · evidence-recompute |
| Context | same-session — item |
| Суть | После fresh design GREEN заморозить additive admission contract и отдельные provider-specific no-write smoke task/grant carriers |
| Команда | — |

```text
# НЕ раньше: latest Audit design after D79 verdict = GREEN
$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P1.6
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
