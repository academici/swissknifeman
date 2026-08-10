# План

## 0. Meta

| Поле | Значение |
|:--|:--|
| Plan ID | 2026.08.03-ARTIFEX-SUPERVISOR |
| Title | Reliable long-horizon supervisor |
| Document Type | Executable Master Plan |
| Authoring Model | gpt-5.6-terra (bootstrap; effort not exported) · gpt-5.6-sol/high (P0/P1 detail; historical plan provenance) · prescribed semantic route `gpt-5.6-sol/high` (P2–P6 detail, original finish, post-D74 finish, post-D74/post-D76 audit remediations, P3.4 native-tool/successor-manifest remediations, P3 audit reopen, P5→P6 finished-product reconciliation, post-D88 cross-phase finish, audit-8 F1–F4 remediation, audit-9 authority/provenance remediation, audit-10 live-carrier/provenance remediation, D98 owner audit-loop closure, D99 P4.1 generation-aware terminal-validator reconciliation, final P4 audit-1 remediation, P5 last-pass generation-gate/business-grant fast track, D107 frozen-contract reconciliation, D108–D109 whole-P5 successor reconcile, D110 P5.5 probe-recovery design, D111 exact R2 owner grant/reopen, D112 Codex R2 cap-contract refinement; source — `task:plan-design` semantic pin) · gpt-5.6-sol/xhigh (P4 audit-2 bounded forward remediation; actual historical session) · claude-sonnet-5/high (D117 P5.2 self-authorization void remediation; actual session, invoked directly by the repository owner outside the routed selector) · claude-opus-5/high (D119–D120 P5.2 seam-ownership/version-pin design pass, D121–D122 P5.2 task-description-carrier reconciliation, D123–D127 P5.4 economic-adjudication re-design, and D132–D135 P5.4 package-authority remediation; actual sessions, invoked directly by the repository owner outside the routed selector). Actual selector/effort for routed sessions are not independently attested: `codex doctor` reports loaded config, not the already-running session selector. |
| Repository | swissknifeman |
| Related Packages | artifex (new mandatory package) · task · harness · core · analyst · maind |
| Execution Mode | contract-first, phase-first |
| Target Operator Classes | implementation (execution) · economy (recon) · frontier (design/audit) |
| Approval Owner | repository owner |
| Home | repo:swissknifeman |
| visibility | private |
| supersedes | 2026.07.18-FOREMAN (только остаточный supervisor-трек; архив не переписывается) |
| Paused By | 2026.08.07-PLAN-ECONOMY, 2026-08-07 — владелец: исполнение приостановлено до завершения плана оптимизации протокола планов (`task`). Причина — пол холодного старта этого плана 583 КБ ≈ 170к токенов, и любой дальнейший замер супервизора мерил бы болезнь протокола, а не пользу продукта. **Переизмерение P5.4 после снятия паузы обязано идти через РЕАЛЬНЫЕ планы** (`task:plan-design` → `task:dev`/`task:plan-exec`), а не через голые одноразовые задачи: прогон 2026-08-07 померил обвязку без планировщика и потому на вопрос об экономии не отвечает. |
| Design Passes | 8/8 + finish + bounded remediations through D104 + P5 last-pass reconciliation + D107 frozen-contract stop + D108–D109 whole-P5 reconcile + D110 recovery design + D111 exact R2 owner grant/reopen + D112 Codex R2 cap-contract refinement + D113 owner terminalization direction + D117 P5.2 D114–D116 self-authorization void + D118 P5.2 bridge architecture (owner-delegated) + D119–D120 P5.2 seam-ownership reopen and version-pin discipline (owner-selected) + D121–D122 P5.2 task-description-carrier reopen and replacement-row grant (owner-selected) + D123–D127 P5.4 economic-adjudication re-design (four owner selections, two new items, two third reopens) + D132–D135 P5.4 package-authority remediation (D125 batch registration, one new gate-repair item, one fourth reopen; forward-conformance sweep per `brief/37`) — completed denominator unchanged |
| Layout | v2 |
<!-- migration-version: 0.27.0 -->

## 1. Context

Нужен надёжный внешний supervisor для длинных фаз, где владелец заранее задаёт каноны и
границы, а подавляющее большинство рутинных развилок может быть разрешено без его участия.
Это не Workflow и не постоянно растущий главный LLM-контекст. Supervisor компилирует план в
ограниченные слайсы, запускает каждый слайс в свежем worker-контексте, детерминированно
проверяет результат, ведёт durable run state и объединяет редкие owner-гейты в один пакет.

Архивный FOREMAN сохранил имя Artifex и полезные run-folder/driver идеи, но был поглощён
HARNESS-AGNOSTIC: живой Harness получил декларативную execution policy, а не runtime
супервизор. P0–P3 сначала построили и проверили runtime plan-local, но assurance и пилоты не
должны идти против кода, который затем мигрирует в другой путь. Поэтому P3.8 переносит
исправленный runtime в законченный standalone `packages/artifex/` до P4/P5; P4–P5 проверяют уже
этот package SSOT, а P6 добавляет umbrella routing, установку, документацию и эксплуатационный
handoff. План не считается успешно завершённым, пока весь package/public surface и cold audit не GREEN.

## 2. Execution Rules

- Supervisor является внешней детерминированной control loop; Workflow допустим только как leaf adapter, не как источник состояния или решений.
- LLM worker не получает ambient authority: его вывод — недоверенное наблюдение, которое проходит schema, scope, validation и authority gates.
- Один item исполняется за раз; статусы меняются только каноническими командами plan-protocol после принятой проверки.
- Один write lane по умолчанию; параллельность максимум 2 и только для доказанно независимых read-only либо worktree-isolated слайсов; интеграция последовательна.
- Каждый слайс стартует в свежем контексте из минимального immutable bundle; обратно возвращается ограниченный structured envelope и ссылки на артефакты.
- До любого worker/public side effect durable journal получает intent с attempt/idempotency key; после границы — observation; acceptance пишется только после детерминированной проверки.
- Resume сначала сверяет journal, snapshot, source/plan hashes и внешний pre/postimage; неизвестное третье состояние fail-closed эскалируется владельцу.
- AUTO-FIX не может ослабить acceptance, тесты, security, scope, budget или frozen contract.
- Owner-гейты пакетируются; немедленно будят владельца только security, destructive или необратимая граница.
- Никаких новых pip/npm runtime dependencies; внешние проекты используются только как дизайн-паттерны и переписываются на stdlib.
- Неизмеренные token/cost/intervention поля не дают зелёный экономический вердикт.
- `NO-GO`, неизвестная метрика или RED P5/P6 gate оставляют план открытым и назначают forward remediation; успешная terminal closure без `packages/artifex/` запрещена.
- После закрытия item/фазы полностью перезаписать `handoff.md` и append-only обновить `journal.jsonl`.
- D98 закрывает pre-exec design-audit loop после десяти исторических заходов: новый `$ task:plan-audit 2026.08.03-ARTIFEX-SUPERVISOR design` запрещён без нового явного owner D#; P3.5 был его тогдашним Next, текущий runnable producer — P5.5.
- Любой оставшийся audit checkpoint ограничен `AUDIT_ROUNDS_MAX=2` и `SAME_FINDING_MAX=2`: после второго non-GREEN автоматического третьего аудита нет, дефект исправляется вперёд и закрывается детерминированной validation; owner interruption допустим только для реального safety/authority/frozen-contract/acceptance gate.
- D105–D107 preserve the frozen business request and genuine G2 refusal. D108–D112 authorize only P5.5's exact additive G2B contract/runtime/provider/assurance generation, one schema carrier and the finite R2 replacement pair after zero-process preflight; D112 replaces only Codex cap-enforcement claims with the enforceable wrapper/usage contract, no D105 pilot call is legal before P5.5 terminality, and P4/G2/P5.1 history stays immutable.
- **Переходное правило Layout v2 (до P6):** закрытие пункта фиксируется записью в `journal.jsonl`, находкой или решением при необходимости и регенерацией видов; поля исхода в файле ТЗ запрещены и ловятся линтером.

## 3. Routing

| Items | Model class/effort | Exec | Почему |
|:--|:--|:--|:--|
| P0.1 | frontier/high | manual | matched-baseline selection and live-driver reuse verdict retain open comparability decisions |
| P0.2 | frontier/high | manual | owner authority and conflict examples freeze decision semantics |
| P0.3 | implementation/high | manual | bounded empirical probes follow a fixed matrix; provider/security boundaries require high effort but no open architecture |
| P0.4 | frontier/high | manual | ecosystem-core threat model and pre-mortem retain open failure-boundary decisions |
| P0.5 | frontier/high | manual | acceptance rubric and GO/NO-GO evidence freeze are irreversible planning decisions |
| P1.1 | frontier/high | manual | irreversible freeze of durable run/WAL/recovery semantics; public ecosystem-core contract requires full review |
| P1.2 | frontier/high | manual | immutable slice/compiler contract still carries open ownership and refusal decisions; full review |
| P1.3 | frontier/high | manual | authority-class freeze changes which actions may run unattended; full review |
| P1.4 | frontier/high | manual | provider-neutral public envelope freezes parity and failure taxonomy; full review |
| P1.5 | frontier/high | manual | economic/privacy verdict contract and aggregate five-contract freeze are irreversible adjudication inputs; full review |
| P1.6 | frontier/high | manual | new dispatch-admission contract and owner-bounded grant freeze a security/public-contract boundary; full review |
| P2.1 | implementation/high | manual | canonical plan/Task compiler integration against frozen contracts; high effort and full review, no open architecture |
| P2.2 | implementation/high | manual | durability/lock/replay implementation is correctness-critical; high effort and full review |
| P2.3 | implementation/high | manual | prescribed authority evaluator against frozen cases; security/authority boundary requires high effort and full review |
| P2.4 | implementation/high | manual | scheduler/reconcile/budget implementation is correctness-critical; high effort and full review |
| P2.5 | implementation/high | manual | control CLI and aggregate candidate freeze cross durability/security boundaries; high effort and full review |
| P2.6 | implementation/high | manual | prescribed dispatch-admission projection and provider-free CLI seam cross authority/durability boundaries; high effort and full review |
| P3.1 | implementation/high | manual | prescribed Codex mapper crosses current CLI, permission and structured-output boundaries; high effort/full review |
| P3.2 | implementation/high | manual | prescribed Claude mapper crosses current CLI, permission and structured-output boundaries; high effort/full review |
| P3.3 | implementation/high | manual | provider parity/exit conformance implements the frozen P0/P1 matrix; high effort/full review |
| P3.4 | implementation/high | manual | fresh-process, timeout/orphan, privacy and activity-port binding are correctness/security critical; high effort/full review |
| P3.5 | implementation/high | manual | admitted provider activity binding crosses authority, process, privacy and durable-journal boundaries; prescribed forward fix, high effort/full review |
| P3.6 | implementation/high | manual | real readiness evidence and cross-generation hash verification are correctness/provenance critical; high effort/full review |
| P3.7 | implementation/high | manual | affected-package regression repair plus final phase verification require high+ final verification and full review |
| P3.8 | implementation/high | manual | package promotion establishes the sole live runtime before assurance/pilots; package boundary and provenance require high effort/full review |
| P4.1 | implementation/high | manual | exact failure-bank freeze and executable crash harness are correctness-critical; high effort/full review |
| P4.2 | implementation/high | manual | no-rerun recovery and idempotency repair cross durable side-effect boundaries; high effort/full review |
| P4.3 | implementation/high | manual | linked-worktree ownership and serialized integration cross Git write/rollback boundaries; high effort/full review |
| P4.4 | implementation/high | manual | authority, secret, untrusted-output, redaction and effective-hook gates are security-critical; high effort/full review |
| P4.5 | implementation/high | manual | journal-derived owner/telemetry aggregate must preserve every severe/unknown/provider state; high effort/full review |
| P4.6 | implementation/high | manual | exact worktree-local effective-hook repair/recheck changes trusted execution state and must preserve fail-closed evidence; high effort/full review |
| P4.7 | implementation/high | manual | committed-tree Harness repair and historical provenance reconciliation cross generated-doc/test/closure evidence; high effort/full review |
| P4.8 | implementation/high | manual | resolver-valid frozen-contract successor and final G2 requalification cross authority/public assurance boundaries; high effort/full review |
| P5.1 | frontier/high | manual | irreversible trial/baseline/order freeze and archive mapping retain open experiment-design decisions; full review |
| P5.5 | implementation/high | manual | prescribed additive public-contract/runtime/provider/assurance generation against D108–D109; correctness/security critical, full review |
| P5.2 | implementation/high | manual | prescribed three-slice live pilot crosses provider/Git/acceptance boundaries; high effort/full review |
| P5.3 | implementation/high | manual | prescribed composed crash/reconcile/provider-failure pilot is correctness/security critical; high effort/full review |
| P5.6 | implementation/high | manual | prescribed generation-aware repair of four already-designed frozen gates against a settled pattern (D121/D122 rule 6); no open design decision, but the gates guard evidence integrity — high effort/full review |
| P5.7 | frontier/high | manual | `economy-evidence-v2` is an irreversible public-contract freeze that adjudicates every later economic claim; open design decisions on the three unknown rules — full review |
| P5.8 | implementation/high | manual | prescribed generation-aware repair of three gates owned by no live item, against the settled D121/D130 pattern; no open design decision, but one repair touches a P4-evidence path under D134's authorized exception — high effort/full review |
| P5.4 | frontier/high | manual | five-wave comparability, single-provider economic scope and release-readiness adjudication gate mandatory productization; full review |
| P6.1 | frontier/high | manual | mandatory umbrella/operations scope freeze binds the existing package to exact D86/D87 owner grants |
| P6.2 | implementation/high | manual | umbrella router/install/doctor integration crosses public/generated ownership while preserving the P3.8 runtime SSOT; full review |
| P6.3 | implementation/high | manual | install/update/doctor, opt-in compatibility, state migration, rollback and docs complete the public product surface; high effort/full review |
| P6.4 | frontier/xhigh | manual | cold independent release/rollback audit |

## 5. Decision Log

Решения находятся в `decisions/`; собрать или проверить их виды: `python3 packages/task/scripts/plan-views.py decisions --plan-dir <plan-dir> [--check]`.

## 7. Contracts

### Exported

| Контракт | Версия | Статус | Потребители | Уведомлены |
|:--|:--|:--|:--|:--|
| `root/contracts/supervisor-run-v1.md` | v1.0.0 | frozen P1.1 (`a784cad7`) | P2–P6 | P1.2–P1.5 и P2–P6 через plan и handoff |
| `root/contracts/slice-manifest-v1.md` | v1.0.0 | frozen P1.2 (`e6331a3d`) | P2–P6 | P1.3–P1.5 и P2–P6 через plan и handoff |
| `root/contracts/authority-policy-v1.md` | v1.0.0 | frozen P1.3 (`8a1f1757`) | P2–P6 | P1.4–P1.5 и P2–P6 через plan и handoff |
| `root/contracts/worker-envelope-v1.md` | v1.0.0 | frozen P1.4 (`698e5d7d`) | P2–P6 | P1.5 и P2–P6 через plan и handoff |
| `root/contracts/economy-evidence-v1.md` | v1.0.0 | frozen P1.5 (`26b71cac`); superseded as the P5.4/P6 adjudication contract by v2 (D123), bytes unedited | P2–P4 historical; P5.4/P6 consume v2 | D123 names the successor; v1 text is never reopened |
| `root/contracts/economy-evidence-v2.md` | v2.0.0 | frozen P5.7 under D123; MAJOR (three unknown-rule changes, no fourth semantic difference); content SHA-256 `774184dc93edd10f7c271e14d95319e34c6015685ef168e7314a8c90d6efc07d` | P5.4, P6.1/P6.4 | D123 pins every downstream economic consumer to v2; `contract-manifest-v2.json` enumerates all eight contracts and pins this hash; further change requires a v3 under a new owner decision |
| `root/contracts/dispatch-admission-v1.md` | v1.0.0 | frozen P1.6 (`140a9b53`), smoke-only; D107 forbids in-place P5 widening | P2.6, P3.4, P4/G2; P5 only as negative lineage | P2.6 materialized exact smoke admissions; D108 grants a separate P5.5 successor, not a mutation of this contract |
| `root/contracts/business-dispatch-admission-v1.md` | v1.0.0 | planned P5.5 under D108; additive G2B, absent until item commit | P5.2–P5.4, P6.1/P6.4 | D109 pins every downstream consumer to P5.5 generation/assurance; G2 remains immutable predecessor |

### Consumed

| Контракт | Донор-план | Pinned | Замечено | Реакция |
|:--|:--|:--|:--|:--|
| `root/contracts/execution-state-machine-v1.md` | 2026.07.24-AGENT-RELIABILITY | committed v1 (`575a49b2`) | data contract exists; no live `decide` module | P0.2 maps semantics; P1.1 reissues only supervisor-owned transition subset |
| `root/contracts/risk-review-loop-budget-v1.md` | 2026.07.24-AGENT-RELIABILITY | committed v1 (`575a49b2`) | loop/authority vocabulary available | P1.3 composes without weakening |
| `root/contracts/unified-agent-trace-v1.md` | 2026.07.24-AGENT-RELIABILITY | committed v1 (`3af26580`) | live acceptance coverage historically incomplete | P1.4/P1.5 reuse trace identities but do not claim old acceptance GREEN |
| `root/contracts/reliability-acceptance-v1.md` | 2026.07.24-AGENT-RELIABILITY | committed v1 (`f405017a`) | terminal plan recorded unmet F1/F10 and limited observability | P0.5 names inherited debts; candidate gets its own measured gates |
| `root/contracts/execution-policy-v1.md` | 2026.07.29-HARNESS-AGNOSTIC | sealed v1 | current policy is declarative/prompt-enforced, not runtime interception | P1.2/P1.3 consume ceilings and delegation fields; no duplicate fleet policy |
| `root/contracts/artifex-run-folder.md` | 2026.07.18-FOREMAN | sealed v1 | useful historical carrier; old driver parse anchor expired | P1.1 reissues compatible successor; old `driver-plan-protocol.md` is historical only |
