# Roadmap исполнения — 2026.08.03-ARTIFEX-SUPERVISOR

**Обновлён:** 2026-08-10 · **Соответствует plan.md:** v0.27.1 · **Статус:** P1/P2 terminal;
P3 закрыта `🟠` (6 🟢, 2 🟠); P4 закрыта `🟠` (2 🟢, 6 🟠). Audit pass 2 остаётся
историческим RED; D98/D103 и прямое owner-указание закрывают его bounded forward remediation с
детерминированными GREEN gates, без третьего audit/design pass. **P5 = 2/8 `🟢` (P5.6, P5.7); P5.1,
P5.2, P5.3 закрыты `🟠`; P5.5 реопенен `🟡` четвёртый раз; P5.8 и P5.4 — `⬜`.** P5.4 дважды
остановился ДО первого диспатча на pre-intent-гейте (оба раза 0 provider-процессов, 0 потраченных
допусков). Второй стоп (D132–D135) не вскрыл ни одного дизайн-вопроса: пакет не знал уже выданного
гранта D125 (`GRANT_BATCHES` + захардкоженная ветка) и два гейта остались без владельца — работа
producer-side, отданная P5.5 и новому P5.8. Первый re-design (2026-08-06) нашёл три блокера сверх
восьми: кандидатская полоса пишет usage булево, а не целыми (F9); ни один провайдер не отдаёт все
семь полей `economy-evidence-v1`, поэтому в режиме `parity` `GO` недостижим по построению (F10); у
codex-песочницы нет работающего компенсирующего контроля на этом ядре (F11). Владелец выбрал все
четыре рекомендации (`brief/35-…`) → D123 (single-provider claude-code + аддитивный
`economy-evidence-v2`), D124 (baseline = прямой headless-вызов того же слайса без супервизора),
D125 (`G-OWNER-P5.4-PAIRED-WAVES`, десять строк, поднятые бюджеты), D126 (все пять волн на
claude-code, codex исключён), D127 (топология из пяти items). Фаза выросла до восьми items: новые
P5.6 (починка четырёх generation-stale гейтов) и P5.7 (заморозка `economy-evidence-v2` +
восьмиконтрактный аддитивный манифест), третьи реопены P5.5 (измеренный economy-конверт в фолдах) и
P5.1 (v3-набор носителей). Ни один v1/v2-байт, ни строка замороженного контракта, ни pin `2.1.222`
(D120) не двигаются; пять неиспользованных `p5.4-wave-*` D105-строк списаны явно и истекают
`2026-08-12` неистраченными.

## Current execution status — pause lifted after final acceptance successor

**Next:** manual: implementation/high

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | high |
| Capabilities | repository-code-edit · deterministic-validator-repair |
| Context | NEW SESSION — item |
| Суть | P5.5 (четвёртый реопен): зарегистрировать в `business_dispatch.GRANT_BATCHES` уже выданный грант D125 и перенести литерал ветки ВНУТРЬ строки батча, доказать живым validate-only швом на всех трёх наборах, перезаморозить G2B седьмой раз с записью реестра тем же коммитом. 0 provider-процессов, 0 потраченных допусков. |
| Команда | — (Exec = manual: нет однокомандного эквивалента) |

```text
$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P5.5
```

Порядок оставшейся работы: **P5.5 → P5.8 → P5.4** (D123–D127-цепочка P5.6 → P5.7 → P5.5 → P5.1
исполнена; второй pre-intent-стоп P5.4 вскрыл три производственных дефекта, ни одного дизайнерского).
Workflow-скрипт
`workflows/wf-artifex-supervisor-p52-pilot.js` относится к уже закрытому P5.2 и в оставшейся
цепочке не запускается; P5.4 несёт собственный раннер `artifacts/P5/run-battle-waves.py` (пять
пар — кандидат через шов Artifex, baseline прямым headless-вызовом). Пин
`SKM_CLAUDE_BIN=/home/vostrikov/.local/share/claude/versions/2.1.222` остаётся обязательным (D120)
и перепроверяется перед каждым из десяти диспатчей.

## Карта исполнения

Все 45 items имеют `Exec = manual`: effort `high`/`xhigh` выше жёсткого пина `plan-exec`, а
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
| P5.6 | terminal | 🟢 Done | implementation/high | — (никакого гранта не требует) | `⬜` расэскалирован D128–D131, доведён до DoR: generation-aware починка `validate-shadow.py` (+переезд историчного гварда), `validate-package-promotion.py` (якорь `367e477a` из git, исправленный `--prototype`), `validate-repository-pilot.py` (+развод кодов выхода `0`/`2`/`1`), перенос P4-якоря на `3533234c` и реестр G2B-генераций. Приёмка (c) — exit `2`, не `0` |
| P5.7 | terminal | 🟢 Done | frontier/high | D123 разморозил P1-контрактный набор ровно на один аддитивный successor | `economy-evidence-v2@2.0.0` заморожен + аддитивный восьмиконтрактный `contract-manifest-v2.json` |
| P5.1 | terminal-history | 🟠 Done with deviations | frontier/high | D125 `G-OWNER-P5.4-PAIRED-WAVES` — десять строк, expiry `2026-09-30`; D105/D122 не тронуты | третий реопен закрыт: аддитивный v3-набор — пять `candidate` + пять `baseline` строк, все claude-code, поднятые бюджеты |
| P5.5 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P5.5` | implementation/high | D125 уже выдан владельцем; нового гранта не требуется — регистрация уже выданной власти | реопенен `🟡` ЧЕТВЁРТЫЙ раз (D132): строка `D125` в `GRANT_BATCHES` + `branch` внутрь каждой строки батча, seam-admission smoke на трёх наборах, седьмая переморозка G2B с записью реестра тем же коммитом |
| P5.8 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P5.8` after terminal P5.5 | implementation/high | — (никакого гранта не требует; D134 авторизует одну правку P4-валидатора) | `⬜` новый (D133): три бесхозных гейта — `validate-recovery-pilot.py` на ledger-membership, `validate-assurance.py` two-sided, `None`-гвард в `lane_units`; затем публикует ПОЛНЫЙ прогон pre-intent-гейта P5.4 |
| P5.2 | terminal-history | 🟠 Done with deviations | implementation/high | D122 три заменяющие строки истрачены | `0/3 accepted`, все три `PROVIDER_PROTOCOL_UNKNOWN`; три живые починки шва (`--allowedTools`, `item.started`, `errors`) закоммичены, но ни одним допущенным диспатчем не подтверждены |
| P5.3 | terminal-history | 🟠 Done with deviations | implementation/high | 6 реальных D105-допусков истрачены | crash/resume/duplicate/timeout/schema/third-state evidence получено |
| P5.4 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P5.4` after terminal P5.5 (4-й реопен) и P5.8 | frontier/high | D125 (десять диспатчей) + D123 (`single-provider` scope, `owner_grant_ref`) | `⬜` пере-скоупен: пять пар кандидат/baseline на claude-code, адъюдикация по `economy-evidence-v2`; G3 пиннит измеренный G2B, закрывает только литеральный `GO` |
| P6.1 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P6.1` | frontier/high | revalidates D86/D95 plus G2B/G3 and consumes D87/D96 | freeze exact P6.2/P6.3 rows and D93 root authorization order |
| P6.2 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P6.2` | implementation/high | exact D87+D96; protected G2B runtime immutable | produce G4 through exact root plan→apply `AGENTS.md,CLAUDE.md`→check without runtime migration |
| P6.3 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P6.3` | implementation/high | — | produce G5: install/update/doctor, default-off operations, compatibility, rollback, docs and changelog |
| P6.4 | solo | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P6.4` | frontier/xhigh | — | distinct cold G1→G2→G2B→G3→G4→G5 finished-product/instruction audit; RED keeps plan open |

## Последовательность successor-contract remediation

1. P1.6/P2.6 and P1/P2 remain terminal; do not rewrite their carriers.
2. D98 closes the ten-pass pre-exec design loop; do not run audit 11. Start P3.5 under its committed-spec gate.
3. Execute P3.5→P3.6→P3.7→P3.8, close P3 and apply the two-pass/two-repeat ceiling to its phase audit checkpoint.
4. Audit P4 pass 1 reopened the historical chain; P4.7→P4.8 and close completed. Audit pass 2
   remains historical RED, then bounded forward remediation closed its mechanical/product gates
   GREEN under D98/D103. No third audit/design pass is authorized; continue P5→mandatory P6.
5. P5.2 proved terminal G2 cannot consume D105 and Codex cannot launch. D107 freezes that result;
   D108–D109 add exact P5.5 G2B production before unchanged-ID P5.2→P5.3→P5.4. P4/G2/P5.1 stay
   immutable, and P6 consumes the same G2B pin.

### P3 — closed forward remediation

P3 закрыта `🟠 Done with deviations`: P3.4 сохраняет stale P1.6 parent hash/non-green readiness,
P3.5 — foreign `scheduler.py` path; P3.6–P3.8 закрыли evidence, Task fan-in и G1 package
promotion. D98 запрещает audit 11; D99 сохраняет оба deviation и задаёт generation-aware
terminal baseline; следующий runnable producer — P4.2.

## Authority Gate Contract

Только следующие восемь active markers являются owner grants этого плана. Проверяемый carrier —
более поздняя, чем D64, строка Decision Log в `plan.md`, которая дословно содержит указанный
`[OWNER-GRANT:<gate-id>]`, называет разрешённую ветвь и scope, ссылается на явное сообщение
repository owner и не отозвана более поздним D#. D74/D75 и команды `finish`/audit не являются
ни одним из этих grants.

| Gate ID | Защищённый переход | Exact predicate | Без carrier |
|:--|:--|:--|:--|
| `G-OWNER-P5-BUSINESS` | P5.1 материализует grants/admissions для P5.2–P5.4 | D105 содержит marker, exact catalog/request SHA-256, providers, 14 roots, max-dispatches, per-trial caps и `brief/22-p5-last-pass-fast-track.md`; D78 itself is not a grant | P5.1 pauses after proposal hashes; no business admission/provider call |
| `G-OWNER-P5-G2B-SUCCESSOR` | P5.5 produces additive G2B contract/runtime/provider/assurance | D108 exact marker, branch, Files, two-link D105 G2-predecessor→current-G2B projection, provider versions, two probe roots/caps, unchanged expiry/budget, zero D105 usage and acceptance; consumer P5.5 only | no package/contract mutation or capability probe; P5.2–P6 remain gated |
| `G-OWNER-P5.2-RETRY` | P5.2 re-runs the repository pilot after the carrier fix | D122 exact marker, three named replacement trial IDs, one slice each, `reusable:false`, `claude-code` `timeout_ms` `600000` and every other cap byte-equal to v1; minted by P5.1 into an additive v2 set; `brief/34-p5.2-zero-accept-owner-decision-2026-08-06.md` is the Layer-0 carrier | no fourth slice, no retry of a started attempt, no D105 consumption, no expiry extension |
| `G-OWNER-P5-G2B-PROBE-R2` | P5.5 adds the missing worker-output schema and runs the final replacement canary pair | D111 exact marker, branch, consumer, one schema path, two R2 roots, provider versions, zero-process preflight, zero D105 use, no retry/fallback/pilot and full acceptance; D112 supersedes only Codex cap semantics with one fresh exec, Artifex `120000ms`/`<=8192`/`<=16`, conditional strict-config-proven `rollout_budget=2000`, no max-turn/money CLI claim and measured usage; `brief/26` + `brief/27` are the Layer-0 carriers | no schema path, R2 call or P5.5 resume; P5.2–P6 remain gated |
| `G-OWNER-P5.4-PAIRED-WAVES` | P5.1 чеканит v3-набор, P5.4 тратит десять диспатчей | D125 exact marker, branch, десять trial ID (`p5.4w-*`/`p5.4b-*`), только `claude-code`, `max_slices:1`, `reusable:false`, восемь значений caps, expiry `2026-09-30T23:59:59Z`; `brief/35-p5.4-economic-adjudication-owner-decisions-2026-08-06.md` — Layer-0 носитель | нет одиннадцатой строки, нет `codex`-строки, нет retry начатой попытки, нет потребления D105/D122, нет продления D105-expiry |
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
| G2 | P4.8 D104 requalification successor (historical predecessor: P4.5/`23f71d34`) | immutable P3 readiness/smoke generation; P5 business use refused by D107 | consumes terminal P4.7 and exact current Artifex bytes; any business/native successor is a distinct forward generation under a new owner grant and never rewrites G2/P4 history |
| G2B | P5.5 D108 additive business successor | P5.2–P5.4 and P6.1 pre-write | pins G2 predecessor, exact business contract/provider surface/current package digest; no D105 pilot use in production |
| G3 | P5.4 `GO` | P6.1 pre-write | pins exact unchanged G2B bytes; evidence only |
| G4 | P6.2 D96 root generation + integration | P6.3 start | pins exact D93 plan/apply/check/lock transition and structural router/installer successor; no runtime migration |
| G5 | P6.3 operations | P6.4 audit | finished current product; cold audit validates G1→G2→G2B→G3→G4→G5 |

Historical carriers are never regenerated against evolved current bytes.
`packages/artifex/{CLAUDE.md,AGENTS.md}` and root `CLAUDE.md`/`AGENTS.md` are generated/validated
under their exact D95/D96 Harness instruction owner scopes via D93 plan→apply→check; direct
projection edits are forbidden, and the shared lock is never an `--authorize` target.

## Завершённый package prerequisite

`artifacts/design/task-authority-carrier-01.md` имеет `State: terminal`, а независимый reviewer
сохранил literal GREEN. Этот prerequisite уже потреблён terminal P0.1 и не имеет runnable launch в
текущем roadmap. Исторические producer/reviewer attempts остаются в carrier/review evidence; они не
повторяются после D75.
