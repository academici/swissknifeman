# Roadmap исполнения — 2026.08.03-ARTIFEX-SUPERVISOR

**Обновлён:** 2026-08-05 · **Соответствует plan.md:** v0.17.0 · **Статус:** P1/P2 и
P3.1–P3.4 остаются terminal history; D82–D84 держат P3 reopened, D88 добавил P3.8 и состояние
`3/8`; D89–D90 держат G1→G5 generation/generator topology, D93–D94 закрывают audit-8
execution/validation gaps, а D95–D97 дают exact resolver-valid Harness source/test/lock grants до
consumers; D98 закрывает design-audit loop и открывает P3.5; package/root projections идут только
через plan→apply→check, P3.7 не мутирует P3.6.

## Current execution launch — D98 audit-loop closure

**Next:** run-items: task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P3.5

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | high |
| Capabilities | repository-plan-write · subprocess-test · git-commit |
| Context | same-session — item |
| Суть | Исполнить P3.5 под committed-spec и exact route gates; design audit не повторять |
| Команда | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P3.5` |

| Model | Thinking | Approval policy | Sandbox | CWD | Context | Суть | Команда |
|:--|:--|:--|:--|:--|:--|:--|:--|
| gpt-5.6-terra | high | never | danger-full-access | `/home/vostrikov/projects/packages/swissknifeman` | `NEW SESSION — item` | P3.5 execution; D98 forbids another pre-exec design audit | `codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access 'NEW SESSION: Run $ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P3.5. Read plans/2026.08.03-ARTIFEX-SUPERVISOR/plan.md, phases/P3.md P3.5, roadmap.md and handoff.md. D98 closes the pre-exec design-audit loop; do not run task:plan-audit design. Enforce committed-spec and exact implementation/high route gates. Implementation writes are limited to P3.5 Files; bookkeeping writes are limited to canonical plan/journal/handoff closure carriers. Preserve unrelated dirty worktree, run all P3.5 validation, self-close with the two-commit protocol, then continue autonomously to the next roadmap item unless a genuine safety/authority/frozen-contract/acceptance gate blocks.'` |

## Карта исполнения

Все 39 items имеют `Exec = manual`: effort `high`/`xhigh` выше жёсткого пина `plan-exec`, а
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
| P3.5 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P3.5` | implementation/high | — | exact indexed admission→adapter preflight→bounded normalized activity; committed-spec gate |
| P3.6 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P3.6` | implementation/high | — | consumes P3.5; real readiness probe and strict immutable-P2/current-P3 hash proof |
| P3.7 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P3.7` | implementation/high | — | consumes P3.6 read-only; temp-isolated fresh probe, before/after clean carrier check and Task invariant repair |
| P3.8 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P3.8` | implementation/high | consumes exact D86 output + D95 resolver-valid Harness source/test/lock grant | exact Artifex plan→apply→check, atomic stage-1 commit, full gpt-5.6-terra/high package-cwd Codex continuation, then G1 runtime/baseline |
| P4.1 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P4.1` | implementation/high | — | six-contract admission/dispatch fault matrix and injector freeze |
| P4.2 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P4.2` | implementation/high | — | dispatch-aware no-rerun recovery; consumes P4.1 |
| P4.3 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P4.3` | implementation/high | — | linked-worktree integration; consumes recovery |
| P4.6 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P4.6` | implementation/high | D79 exact scoped repair | one worktree-local hook repair plus exact GREEN recheck; no package-source edit |
| P4.4 | solo | `waiting: P4.6 terminal GREEN → manual: implementation/high` | implementation/high | — | independently recheck hook GREEN, then task/admission/authority/privacy security evidence |
| P4.5 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P4.5` | implementation/high | — | owner/telemetry and admission-aware G2 current-package assurance aggregate |
| P5.1 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P5.1` | frontier/high | `G-OWNER-P5-BUSINESS` after request/catalog hashes | freeze trials/shadow; pause for owner hash-bound dispatch grant; produce all per-trial admissions before close |
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
4. Literal P3 acceptance unlocks P4. Execute P4.1→P4.2→P4.3→P4.6→P4.4→P4.5, then P5→mandatory P6 sequentially; no audit checkpoint may schedule a third automatic pass.

### P3 — reopened forward remediation

**Next:** run-items: task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P3.5

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | high |
| Capabilities | repository-plan-write · subprocess-test |
| Context | same-session — item |
| Суть | Закрыть P3.5 runtime binding перед evidence/hash remediation |
| Команда | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P3.5` |

```text
$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P3.5

РЕЖИМ: remediation item execution; committed-spec gate обязателен
ВХОД: plans/2026.08.03-ARTIFEX-SUPERVISOR/phases/P3.md → P3.5 + Audit P3 F1/F4
СКОУП: exact indexed admission → adapter preflight → bounded normalized worker; CLI binding/tests
НЕ ТРОГАТЬ: frozen P1/P2; terminal P3.1–P3.4 history; P3.6–P3.8; P4–P6; unrelated dirty worktree
```

## Authority Gate Contract

Только следующие пять active markers являются owner grants этого плана. Проверяемый carrier —
более поздняя, чем D64, строка Decision Log в `plan.md`, которая дословно содержит указанный
`[OWNER-GRANT:<gate-id>]`, называет разрешённую ветвь и scope, ссылается на явное сообщение
repository owner и не отозвана более поздним D#. D74/D75 и команды `finish`/audit не являются
ни одним из этих grants.

| Gate ID | Защищённый переход | Exact predicate | Без carrier |
|:--|:--|:--|:--|
| `G-OWNER-P5-BUSINESS` | P5.1 материализует grants/admissions для P5.2–P5.4 | строка D# позже D78 содержит marker, SHA-256 `trial-catalog-v1.json` и `business-grant-request-v1.json`, exact providers/roots/max-dispatches/per-trial caps, explicit owner source; D78 itself is not a grant | P5.1 pauses after proposal hashes; no business admission/provider call |
| `G-OWNER-P6.1-PACKAGE` | P3.8 materializes mandatory `artifex-package`; P6.1 revalidates it | D86 exact marker разрешает `packages/artifex/**` and finite package-owned outputs only | P3.8 remains non-terminal; P4/P5 cannot start |
| `G-OWNER-P3.8-HARNESS-INSTRUCTIONS-R2` | P3.8 stage 1 adds the Artifex instruction owner and shared-lock generation | D95 exact record + Layer-0 message matches every Harness source/test/lock path in P3.8 `Files`; consumer is P3.8 only | no Harness source/projection mutation; P3.8 remains open |
| `G-OWNER-P6.1-ROUTER` | P6.1 фиксирует `root_router=approved`; P6.2 consumes outputs | D87 exact marker разрешает additive `swissknifeman artifex` and exact root installer/doctor/generated outputs | P6.1 remains non-terminal; no rootless terminal product |
| `G-OWNER-P6.2-HARNESS-ROOT-INSTRUCTIONS-R2` | P6.1 freezes and P6.2 changes exact root instruction producers/shared lock | D96 exact record + Layer-0 message matches every Harness source/test/lock path in P6.2 `Files`; consumer is P6.1→P6.2 only | no root source/projection mutation; P6.1/P6.2 remains open |

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
| G2 | P4.5 assurance | P5 and P6.1 pre-write | P5 is read-only; P6.2 protects runtime subset and produces G4 |
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
