# Roadmap исполнения — 2026.08.03-ARTIFEX-SUPERVISOR

**Обновлён:** 2026-08-04 · **Соответствует plan.md:** v0.13.0 · **Статус:** P1/P2 и
P3.1–P3.4 остаются terminal history; D82–D84 держат P3 reopened, D88 добавил P3.8 и состояние
`3/8`: standalone `packages/artifex` появляется до P4/P5, а D85–D87 сохраняют обязательный
finished-product outcome и инвалидируют прежний finish.

## Immediate cross-phase reconciliation

**Next:** manual: frontier/high — finish (шаг-не-item)

| Параметр | Значение |
|:--|:--|
| Model class | frontier |
| Effort | high |
| Capabilities | repository-plan-write · subprocess-test |
| Context | NEW SESSION — шаг-не-item |
| Суть | Пересогласовать ранний P3.8 package boundary, P4/P5 consumers и суженный P6 со всем P0→P6 graph |
| Команда | — |

```text
$ task:plan-design 2026.08.03-ARTIFEX-SUPERVISOR finish

РЕЖИМ: cross-phase finish после owner-outcome correction; НЕ execution items
ВХОД: plan.md D85–D88; brief/14-owner-finished-product-guarantee.md; research/27-finished-product-outcome-reconcile.md; phases/P3.md P3.8; phases/P4.md; phases/P5.md; phases/P6.md
СКОУП: 1) reconcile P3.8 package producer→P4/P5 consumers 2) verify exact package/router/install/test/docs/ops terminal predicate 3) prove P6 performs no runtime migration 4) rebuild roadmap/handoff and hand off to cold design audit
НЕ ТРОГАТЬ: frozen P1/P2 carriers; terminal P3.1–P3.4 history; P3.5–P3.8/P4–P6 implementation; unrelated dirty worktree
```

## Карта исполнения

Все 39 items имеют `Exec = manual`: effort `high`/`xhigh` выше жёсткого пина `plan-exec`, а
contract/security/recovery/public-package классы требуют full review. Батчей и workflow-групп нет:
каждая фаза — последовательная producer chain. Терминальные items ниже не имеют runnable launch;
текущий product execution path снова откроется с P3.5 только после нового finish и literal GREEN
cold design audit.

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
| P3.7 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P3.7` | implementation/high | — | consumes P3.6; repair Task invariant regression and rerun closure fan-in |
| P3.8 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P3.8` | implementation/high | consumes exact D86 package grant | promote the GREEN runtime into standalone `packages/artifex`; P4/P5 consume only package paths |
| P4.1 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P4.1` | implementation/high | — | six-contract admission/dispatch fault matrix and injector freeze |
| P4.2 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P4.2` | implementation/high | — | dispatch-aware no-rerun recovery; consumes P4.1 |
| P4.3 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P4.3` | implementation/high | — | linked-worktree integration; consumes recovery |
| P4.6 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P4.6` | implementation/high | D79 exact scoped repair | one worktree-local hook repair plus exact GREEN recheck; no package-source edit |
| P4.4 | solo | `waiting: P4.6 terminal GREEN → manual: implementation/high` | implementation/high | — | independently recheck hook GREEN, then task/admission/authority/privacy security evidence |
| P4.5 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P4.5` | implementation/high | — | owner/telemetry and admission-aware assurance aggregate |
| P5.1 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P5.1` | frontier/high | `G-OWNER-P5-BUSINESS` after request/catalog hashes | freeze trials/shadow; pause for owner hash-bound dispatch grant; produce all per-trial admissions before close |
| P5.2 | solo | `waiting: P5.1 terminal with business admission index → manual: implementation/high` | implementation/high | consumes `G-OWNER-P5-BUSINESS` only through P5.1 carriers | reversible live three-slice pilot; P3 smoke inputs refuse |
| P5.3 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P5.3` | implementation/high | consumes indexed business admissions | recovery/provider-failure pilot; no local mint/reset |
| P5.4 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P5.4` | frontier/high | business admissions required; no single-provider terminal waiver | five paired waves; only literal frozen `GO` (release-ready) closes, `NO-GO` keeps P5 open for forward remediation |
| P6.1 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P6.1` | frontier/high | revalidates D86 package + consumes D87 router grant | freeze remaining root router/install/doctor/generated/docs/operations scope around the existing P3.8 package |
| P6.2 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P6.2` | implementation/high | exact D87 scope; D86 package stays immutable except scoped launcher/config integration | add umbrella route and root integration without migrating or duplicating runtime code |
| P6.3 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P6.3` | implementation/high | — | install/update/doctor, default-off operations, compatibility, rollback, docs and changelog |
| P6.4 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P6.4` | frontier/xhigh | — | distinct cold finished-product audit; RED keeps plan open |

## Последовательность successor-contract remediation

1. P1.6/P2.6 and P1/P2 remain terminal; do not rewrite their carriers.
2. Run `$ task:plan-design 2026.08.03-ARTIFEX-SUPERVISOR finish`, then cold `$ task:plan-audit 2026.08.03-ARTIFEX-SUPERVISOR design`.
3. Only literal design GREEN exposes P3.5. Execute P3.5→P3.6→P3.7→P3.8, close P3 and run its cold phase audit.
4. Only literal P3 GREEN unlocks P4. Execute P4.1→P4.2→P4.3→P4.6→P4.4→P4.5, then P5→mandatory P6 sequentially.

### P3 — reopened forward remediation

**Next:** waiting: new finish + cold design audit GREEN → manual: implementation/high — P3.5

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | high |
| Capabilities | repository-plan-write · subprocess-test |
| Context | same-session — item |
| Суть | Закрыть P3.5 runtime binding перед evidence/hash remediation |
| Команда | — |

```text
$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P3.5

РЕЖИМ: remediation item execution; committed-spec gate обязателен
ВХОД: plans/2026.08.03-ARTIFEX-SUPERVISOR/phases/P3.md → P3.5 + Audit P3 F1/F4
СКОУП: exact indexed admission → adapter preflight → bounded normalized worker; CLI binding/tests
НЕ ТРОГАТЬ: frozen P1/P2; terminal P3.1–P3.4 history; P3.6/P3.7; P4–P6; unrelated dirty worktree
```

## Authority Gate Contract

Только следующие три active markers являются owner grants этого плана. Проверяемый carrier —
более поздняя, чем D64, строка Decision Log в `plan.md`, которая дословно содержит указанный
`[OWNER-GRANT:<gate-id>]`, называет разрешённую ветвь и scope, ссылается на явное сообщение
repository owner и не отозвана более поздним D#. D74/D75 и команды `finish`/audit не являются
ни одним из этих grants.

| Gate ID | Защищённый переход | Exact predicate | Без carrier |
|:--|:--|:--|:--|
| `G-OWNER-P5-BUSINESS` | P5.1 материализует grants/admissions для P5.2–P5.4 | строка D# позже D78 содержит marker, SHA-256 `trial-catalog-v1.json` и `business-grant-request-v1.json`, exact providers/roots/max-dispatches/per-trial caps, explicit owner source; D78 itself is not a grant | P5.1 pauses after proposal hashes; no business admission/provider call |
| `G-OWNER-P6.1-PACKAGE` | P3.8 materializes mandatory `artifex-package`; P6.1 revalidates it | D86 exact marker разрешает `packages/artifex/**` и finite package-owned projections | P3.8 remains non-terminal; P4/P5 cannot start |
| `G-OWNER-P6.1-ROUTER` | P6.1 фиксирует `root_router=approved` | D87 exact marker разрешает additive `swissknifeman artifex` и exact installer/doctor/generated/docs projections | P6.1 remains non-terminal; no rootless terminal product |

Provider readiness, terminal validators, security/hook integrity and literal GREEN независимого
design audit остаются evidence gates: D# не заменяет отсутствующее или non-green доказательство.
`G-OWNER-P5.4-SINGLE` retired by D85: single-provider evidence may inform remediation/rollout scope,
but cannot terminalize P5 or waive provider parity. Tag/push/publish/release не входят в roadmap и
требуют отдельного позднего разрешения.

## Завершённый package prerequisite

`artifacts/design/task-authority-carrier-01.md` имеет `State: terminal`, а независимый reviewer
сохранил literal GREEN. Этот prerequisite уже потреблён terminal P0.1 и не имеет runnable launch в
текущем roadmap. Исторические producer/reviewer attempts остаются в carrier/review evidence; они не
повторяются после D75.
