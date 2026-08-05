# Roadmap исполнения — 2026.08.03-ARTIFEX-SUPERVISOR

**Обновлён:** 2026-08-05 · **Соответствует plan.md:** v0.20.0 · **Статус:** P1/P2 terminal;
P3 закрыта `🟠` (6 🟢, 2 🟠); P4 закрыта `🟠` (2 🟢, 6 🟠). Audit pass 2 остаётся
историческим RED; D98/D103 и прямое owner-указание закрывают его bounded forward remediation с
детерминированными GREEN gates, без третьего audit/design pass. D105–D106 снимают P5.1
owner/stale-leaf blockers; следующий item — resume P5.1, затем P5.2→P5.4 до одного анализа фазы.

## Current execution launch — P5.1

**Next:** run-items: task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P5.1

| Параметр | Значение |
|:--|:--|
| Model class | frontier |
| Effort | high |
| Capabilities | repository-code-edit · trial-admission-materialization · generation-aware-validation |
| Context | same-session — item |
| Суть | Resume frozen P5.1 checkpoint, verify historical/current generations and materialize all 14 D105-bound admissions. |
| Команда | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P5.1` |

| Model | Thinking | Approval policy | Sandbox | CWD | Context | Суть | Команда |
|:--|:--|:--|:--|:--|:--|:--|:--|
| gpt-5.6-sol | high | never | danger-full-access | `/home/vostrikov/projects/packages/swissknifeman` | `same-session — item` | Resume P5.1 under D105–D106 and close all business admissions | `codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c 'model_reasoning_effort="high"' -a never -s danger-full-access 'Run $ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P5.1. Read research/33-p5-last-pass-generation-gate.md, phases/P5.md, plan.md, roadmap.md and handoff.md first. Resume checkpoint 17cf14cd under D105-D106; preserve P4 history and unrelated dirty worktree; close P5.1 and hand directly to P5.2 without a design/audit checkpoint.'` |

## Карта исполнения

Все 41 items имеют `Exec = manual`: effort `high`/`xhigh` выше жёсткого пина `plan-exec`, а
contract/security/recovery/public-package классы требуют full review. Батчей и workflow-групп нет:
каждая фаза — последовательная producer chain. Терминальные items ниже не имеют runnable launch;
D98 открыл текущий product execution path с P3.5 без audit 11.

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
| P3.4 | terminal-history | 🟠 Done with deviations | implementation/high | — | audit F1–F6 disproved runtime/evidence closure; historical record remains visible and remediation is forward-only |
| P3.5 | remediation | 🟠 Done with deviations | implementation/high | — | `b7c7c1a0` binds the runtime, but its foreign `scheduler.py` path requires plan-design before P3.6 |
| P3.6 | terminal | 🟢 Done | implementation/high | — | `ea141189` provides real indexed readiness and strict immutable-P2/current-P3 hash proof |
| P3.7 | terminal | 🟢 Done | implementation/high | — | Task invariant repair and read-only closure fan-in closed |
| P3.8 | terminal | 🟢 Done | implementation/high | consumes exact D86 output + D95 resolver-valid Harness source/test/lock grant | G1 Artifex package promotion closed |
| P4.1 | terminal | 🟢 Done | implementation/high | — | D99 baseline plus immutable six-contract fault matrix and injector freeze |
| P4.2 | terminal-history | 🟠 Done with deviations | implementation/high | — | foreign `test_scheduler.py` plus delayed/corrective closure provenance; P4.7 reconciles forward |
| P4.3 | terminal | 🟢 Done | implementation/high | — | linked-worktree integration; consumes recovery |
| P4.6 | terminal-history | 🟠 Done with deviations | implementation/high | D79 exact scoped repair | hook repair is real; claimed full Harness gate is red on `10422237` |
| P4.4 | terminal-history | 🟠 Done with deviations | implementation/high | — | runtime `activity.py` enforcement lay outside Files |
| P4.5 | terminal-history | 🟠 Done with deviations | implementation/high | D102 is historical malformed provenance | protected change/G2 lacks pre-mutation resolver authority |
| P4.7 | terminal-history | 🟠 Done with deviations | implementation/high | — | product remediation retained; audit-2 forward fix repairs committed-tree/fixture/generator/provenance gaps without rewriting item history |
| P4.8 | terminal-history | 🟠 Done with deviations | implementation/high | exact D104/Layer-0 owner grant | G2 successor remains valid; unresolved historical route provenance is explicit and not reconstructed |
| P5.1 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P5.1` | frontier/high | D105 exact `G-OWNER-P5-BUSINESS` active | resume `17cf14cd`, apply D106 historical/current gate and produce all per-trial admissions before close |
| P5.2 | solo | `waiting: P5.1 terminal with business admission index → manual: implementation/high` | implementation/high | consumes `G-OWNER-P5-BUSINESS` only through P5.1 carriers | reversible live three-slice pilot; P3 smoke inputs refuse |
| P5.3 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P5.3` | implementation/high | consumes indexed business admissions | recovery/provider-failure pilot; no local mint/reset |
| P5.4 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P5.4` | frontier/high | business admissions required; no single-provider terminal waiver | five paired waves over unchanged G2; G3 pins exact measured digest; only literal frozen `GO` closes |
| P6.1 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P6.1` | frontier/high | revalidates D86/D95 package generation + consumes D87/D96 root grants | require current G2/G3 identity; freeze exact P6.2/P6.3 rows and D93 root authorization order |
| P6.2 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P6.2` | implementation/high | exact D87 output + D96 resolver-valid Harness source/test/lock grant; protected G2 runtime immutable | produce G4 through exact root plan→apply `AGENTS.md,CLAUDE.md`→check without runtime migration |
| P6.3 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P6.3` | implementation/high | — | produce G5: install/update/doctor, default-off operations, compatibility, rollback, docs and changelog |
| P6.4 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P6.4` | frontier/xhigh | — | distinct cold G1→G5 finished-product/instruction audit; RED keeps plan open |

## Последовательность successor-contract remediation

1. P1.6/P2.6 and P1/P2 remain terminal; do not rewrite their carriers.
2. D98 closes the ten-pass pre-exec design loop; do not run audit 11. Start P3.5 under its committed-spec gate.
3. Execute P3.5→P3.6→P3.7→P3.8, close P3 and apply the two-pass/two-repeat ceiling to its phase audit checkpoint.
4. Audit P4 pass 1 reopened the historical chain; P4.7→P4.8 and close completed. Audit pass 2
   remains historical RED, then bounded forward remediation closed its mechanical/product gates
   GREEN under D98/D103. No third audit/design pass is authorized; continue P5→mandatory P6.

### P3 — closed forward remediation

P3 закрыта `🟠 Done with deviations`: P3.4 сохраняет stale P1.6 parent hash/non-green readiness,
P3.5 — foreign `scheduler.py` path; P3.6–P3.8 закрыли evidence, Task fan-in и G1 package
promotion. D98 запрещает audit 11; D99 сохраняет оба deviation и задаёт generation-aware
terminal baseline; следующий runnable producer — P4.2.

## Authority Gate Contract

Только следующие шесть active markers являются owner grants этого плана. Проверяемый carrier —
более поздняя, чем D64, строка Decision Log в `plan.md`, которая дословно содержит указанный
`[OWNER-GRANT:<gate-id>]`, называет разрешённую ветвь и scope, ссылается на явное сообщение
repository owner и не отозвана более поздним D#. D74/D75 и команды `finish`/audit не являются
ни одним из этих grants.

| Gate ID | Защищённый переход | Exact predicate | Без carrier |
|:--|:--|:--|:--|
| `G-OWNER-P5-BUSINESS` | P5.1 материализует grants/admissions для P5.2–P5.4 | D105 содержит marker, exact catalog/request SHA-256, providers, 14 roots, max-dispatches, per-trial caps и `brief/22-p5-last-pass-fast-track.md`; D78 itself is not a grant | P5.1 pauses after proposal hashes; no business admission/provider call |
| `G-OWNER-P6.1-PACKAGE` | P3.8 materializes mandatory `artifex-package`; P6.1 revalidates it | D86 exact marker разрешает `packages/artifex/**` and finite package-owned outputs only | P3.8 remains non-terminal; P4/P5 cannot start |
| `G-OWNER-P3.8-HARNESS-INSTRUCTIONS-R2` | P3.8 stage 1 adds the Artifex instruction owner and shared-lock generation | D95 exact record + Layer-0 message matches every Harness source/test/lock path in P3.8 `Files`; consumer is P3.8 only | no Harness source/projection mutation; P3.8 remains open |
| `G-OWNER-P6.1-ROUTER` | P6.1 фиксирует `root_router=approved`; P6.2 consumes outputs | D87 exact marker разрешает additive `swissknifeman artifex` and exact root installer/doctor/generated outputs | P6.1 remains non-terminal; no rootless terminal product |
| `G-OWNER-P6.2-HARNESS-ROOT-INSTRUCTIONS-R2` | P6.1 freezes and P6.2 changes exact root instruction producers/shared lock | D96 exact record + Layer-0 message matches every Harness source/test/lock path in P6.2 `Files`; consumer is P6.1→P6.2 only | no root source/projection mutation; P6.1/P6.2 remains open |
| `G-OWNER-P4.8-G2-REQUALIFICATION` | P4.8 requalifies the historical P4.5 protected diff and publishes the G2 successor | D104 exact branch/scope plus `brief/21-p4-audit1-final-remediation.md` Layer-0 record; preflight must return owner-gate `allow/allow` | no protected mutation and no terminal G2; P4/P5 stay closed |

Provider readiness, terminal validators and security/hook integrity остаются evidence gates: D#
не заменяет отсутствующее или non-green доказательство. D98 отменяет только повторный pre-exec
design audit; later audit checkpoints obey the two-pass/two-repeat ceiling.
`G-OWNER-P5.4-SINGLE` retired by D85: single-provider evidence may inform remediation/rollout scope,
but cannot terminalize P5 or waive provider parity. Tag/push/publish/release не входят в roadmap и
требуют отдельного позднего разрешения.

## Generation chain

| Generation | Producer | Current through | Successor rule |
|:--|:--|:--|:--|
| G1 | P3.8 D95 generation + package promotion | P3.8 close | pins stage-1 source/guides/lock commit and terminal item commit; historical Git/blob baseline after first P4 package edit |
| G2 | P4.8 D104 requalification successor (historical predecessor: P4.5/`23f71d34`) | P5 and P6.1 pre-write | consumes terminal P4.7 and exact current Artifex bytes; P5 is read-only; P6.2 protects runtime subset and produces G4 |
| G3 | P5.4 `GO` | P6.1 pre-write | pins exact unchanged G2 bytes; evidence only |
| G4 | P6.2 D96 root generation + integration | P6.3 start | pins exact D93 plan/apply/check/lock transition and structural router/installer successor; no runtime migration |
| G5 | P6.3 operations | P6.4 audit | finished current product; cold audit validates G1→G5 |

Historical carriers are never regenerated against evolved current bytes.
`packages/artifex/{CLAUDE.md,AGENTS.md}` and root `CLAUDE.md`/`AGENTS.md` are generated/validated
under their exact D95/D96 Harness instruction owner scopes via D93 plan→apply→check; direct
projection edits are forbidden, and the shared lock is never an `--authorize` target.

## Завершённый package prerequisite

`artifacts/design/task-authority-carrier-01.md` имеет `State: terminal`, а независимый reviewer
сохранил literal GREEN. Этот prerequisite уже потреблён terminal P0.1 и не имеет runnable launch в
текущем roadmap. Исторические producer/reviewer attempts остаются в carrier/review evidence; они не
повторяются после D75.
