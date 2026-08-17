# План

## 0. Meta

| Поле | Значение |
|:--|:--|
| Plan ID | 2026.08.02-PROVIDER-CONTRACT-LOCALE |
| Title | Lean multi-provider skills, provider control plane, localization, and fleet recovery |
| Document Type | Executable Master Plan |
| Authoring Model | gpt-5.6-sol/high |
| Repository | swissknifeman |
| Related Packages | skiller · harness · maind · task · core |
| Execution Mode | flat/fast, batch-first, evidence-led |
| Target Operator Models | implementation (execution) · economy (recon) · frontier (design/audit) |
| Approval Owner | repository owner |
| Home | repo:swissknifeman |
| visibility | private |
| Paused By | 2026.08.03-ARTIFEX-SUPERVISOR, 2026-08-03 |
| Design Passes | 4/4 — whole-plan semantic design remains accepted; D70 adds only the bounded post-audit P0.9–P0.10 final requalification chain, not a fifth whole-plan design pass or another whole-plan audit |
| Layout | v2 |
<!-- migration-version: 1.1.5 -->

## 1. Context

SKM must be a reliable hub rather than a collection of provider-specific copies. The user
selects capabilities once per project; Claude Code and Codex independently realize that
semantic selection and keep state isolated. Canonical skills, plugins, comments and
development documentation move to compact English. Localized rendering remains available,
with English default and independent inheritable language choices for responses, plans and
diagnostics.

The plan starts with security and evidence because current fleet state includes red provider
trust, legacy projections and unclassified local changes. No fleet cleanup or credential
rotation is implicit authority. A project is not reported healthy until both adapters are
observed, reconciled and behaviorally probed.

Current frontier models must not be constrained by accumulated historical prompt ritual. The
shared Skill Core therefore contains only a concrete job, discriminative trigger boundary,
inputs/outputs, non-obvious invariants and on-demand resources. Claude Code and Codex add their
own discovery, invocation, layout, measurement and replay adapters without replacing that meaning;
a third provider joins through the same seams. Corpus changes are admitted by current official
documentation, real provider workflows and with/without-skill ablation. Deterministic tests lock
the implementation after those outcomes are established; they do not substitute for them.

`audits/2026.08.10-skills-audit.md` is an evidence input, not an accepted change list. Every claim
has a verdict in `findings/13-skills-audit-adjudication-2026-08-10.md`. Its supervisor references
remain owned by `2026.08.03-ARTIFEX-SUPERVISOR`; this plan consumes only stable shared boundaries
and does not duplicate a supervisor runtime.

## 2. Execution Rules

- Canonical intent is the only cross-provider source of truth; adapters own only projections and status.
- Shared skills contain no provider control fields; provider-native discovery/invocation policy is rendered by additive adapters.
- A third provider must be addable through descriptor, renderer, capability, meter and replay seams without modifying existing adapters.
- Claude Code and Codex may not write each other's target files or share mutable adapter state.
- Official current documentation defines expected behavior; live provider replay and ablation establish outcomes; deterministic tests are supplementary regression gates.
- An instruction, example, navigator or resident entry is retained only with a named repository invariant, official requirement, observed failure or measured outcome benefit.
- Audit observations are multi-label and provider-qualified; lexical overlap, token heuristics and residency never become merge/dead decisions by themselves.
- Measurements preserve provider/model/unit/method/uncertainty and expiry; incompatible Claude/Codex units are never added into one scalar verdict.
- Existing local skills are preserved until classified; destructive migration needs ownership proof and backup.
- English is source language; localized text is a rendered overlay, never a second implementation.
- Locale resolution and fallback are deterministic, logged and tested at each precedence boundary.
- Every fleet claim names inspected projects and evidence; skipped projects remain non-green.
- Secret rotation/revocation requires an owner-authorized security step; secrets never appear in reports.
- Generated artifacts are regenerated through their owner and checked, never hand-edited.
- **Переходное правило Layout v2 (до P6):** закрытие пункта фиксируется записью в `journal.jsonl`, находкой или решением при необходимости и регенерацией видов; поля исхода в файле ТЗ запрещены и ловятся линтером.
- **Flat/fast по умолчанию:** соседние ready items с совместимыми входами исполняются одним root-сеансом и одним batch-handoff; отдельный cold start нужен только при смене route, cwd, authority или внешнего состояния.
- **Жёсткий бюджет каждого item P1.3–P7.7:** один initial implementation candidate, один проход объявленной item Validation и, только если он красный, один сгруппированный repair candidate + один targeted recheck. После второго RED исполнитель останавливается с точной failing-командой/риском/owner gate; третий ремонт, новый review или расширение scope запрещены.
- **Validation economy:** Validation item'а — закрытый acceptance inventory, а не приглашение расширять тестирование. Каждая обязательная команда запускается не более одного раза на material candidate; после repair повторяются только проверки, инвалидированные изменёнными файлами, а неизменённые green receipts переиспользуются. Full suite допустим только когда он буквально объявлен item'ом и ещё не запускался для candidate.
- **Запрет синтетического разрастания:** никакие дополнительные fixtures, self-tests, fuzz/mutation/adversarial probes, checker branches или «полезные на будущее» cases не создаются, кроме прямо перечисленного Deliverable либо минимального regression case для уже воспроизведённого acceptance failure. Доступный real provider/project probe выполняется раньше дополнительной синтетики и ровно один раз на candidate.
- **Минимальный acceptance без redesign-циклов:** если объявленный Validation carrier отсутствует и не проверяет ни один изменяемый `Files`/инвариант item'а, executor удаляет только эту stale-команду в текущем attempt, сохраняет остальные проверки и продолжает; отдельные `plan-design`, Owner gate, новый item или дополнительный test layer для такой локальной коррекции запрещены.
- **Конечное состояние локализации:** legacy-параллели `SKILL.ru.md` после подтверждённого EN-переноса удаляются назначенным migration item'ом; английский `SKILL.md` остаётся единственным semantic source, а русский доступен только как sparse key-addressed render overlay, не как второе дерево.
- **Review cap:** P1.3–P7.3 и P7.5–P7.6 имеют `Review: none`: не запускаются дополнительный Task-level reviewer, exploratory reread или discretionary review loop. Это не отменяет product evidence, буквально требуемый frozen-контрактом: P4.3–P4.6 сохраняют bounded independent English/Russian content-review carrier из `locale-authoring-review-v1.md`, D40 и D45, без третьего раунда или дополнительного general review. P7.4 — immutable RED attempt-1 baseline; D90 разрешает ровно один independent successor P7.7, который reuses неизменённые receipts и rechecks только F2–F6, а не выполняет второй whole-plan audit.
- **Batch continuation:** зелёный item сразу передаёт следующий item тому же coordinator; общий bookkeeping, generated views и lint собираются на границе batch, если item contract не требует раньше.

## 3. Routing

| Batch | Items | Model class/effort | Exec | Review | Почему |
|:--|:--|:--|:--|:--|:--|
| solo | P0.1 | implementation/high | manual | full | sealed fleet baseline is a hard producer boundary before classification; high effort is mandatory, frontier tier is not |
| solo | P0.2 | frontier/high | manual | full | ownership classification is a decision boundary and consumes the sealed P0.1 baseline |
| solo | P0.3 | frontier/high | manual | full | recovery-contract freeze is isolated by exact owner authority and immutable bytes |
| solo | P0.4 | implementation/high | manual | full | exact owner-gated containment/no-op transaction is isolated by external security authority and rollback |
| solo | P0.5 | implementation/high | manual | full | exact-set/privacy baseline rebuild is a sealed producer before corrective contract work |
| solo | P0.6 | frontier/high | manual | full | frozen-contract topology and exact owner freeze form an irreversible authority boundary |
| solo | P0.7 | implementation/high | manual | full | executable security evidence is isolated by live trust observations and containment authority |
| solo | P0.8 | implementation/high | manual | full | provenance fan-in is isolated by append-only history and committed-tree reconciliation |
| p0-final-requalification | P0.9–P0.10 | implementation/high | manual | full | adjacent digest rebinding and live-admission requalification share the same audit candidate, pins and full P0 validation |
| solo | P1.1 | frontier/high | manual | full | desired/status public contract ends in an exact schema freeze |
| solo | P1.2 | frontier/high | manual | full | Skill Core/adapter ownership freeze is a distinct public contract boundary |
| p1-close | P1.3 | frontier/high | manual | none | new session; finish the open provider contract, stopping only for its Owner gate |
| p2-contracts | P2.1–P2.3 | frontier/high | manual | none | adjacent locale/authoring freezes share one source set |
| p3-runtime | P3.1–P3.3 | implementation/high | manual | none | resolver, adapters and status graph form one vertical result |
| solo | P4.1 | implementation/high | manual | none | open per-cwd runtime attempt is a producer boundary; terminal runtime/fixture evidence must exist before P4.2 can materialize |
| solo | P4.2 | implementation/high | manual | none | root + Skiller admission tooling freezes the ledger/checkpoint seam before any corpus row can migrate |
| solo | P4.3 | implementation/high | manual | none | skill migration has its own bounded ledger, frozen content-review evidence and rollback boundary; no extra Task review |
| solo | P4.4 | implementation/high | manual | none | command/plugin/diagnostic migration crosses package cwd slices and parser-literal gates, so context is not reused safely |
| solo | P4.5 | implementation/high | manual | none | code-prose checkpoints span package-specific AST/runner evidence and retain an independent rollback cursor |
| solo | P4.6 | implementation/high | manual | none | docs migration ends at the unique terminal-regeneration and all-green integration boundary |
| p5-fleet | P5.1–P5.4 | frontier/high | manual | none | freeze and authorized project actions keep one coordinator |
| p6-health | P6.1–P6.2 | frontier/high | manual | none | terminal Brain transaction and package-health contract share the protected composition boundary |
| solo | P6.3 | implementation/high | manual | none | D86 freezes the remaining local membership/evidence delta; live two-run rebound and privacy cleanup form one external-state boundary |
| p7-real-first | P7.1–P7.3 | implementation/high | manual | none | real replay first, then demonstrated regressions and release assembly |
| p7-final | P7.4 | frontier/xhigh | manual | full | immutable attempt-1 independent audit and RED evidence |
| p7-red-recovery | P7.5–P7.6 | implementation/high | manual | none | adjacent verifier repair and candidate-only integration share the P7.4 findings, exact path partition and candidate-tree validation |
| p7-final-delta | P7.7 | frontier/xhigh | manual | full | one cold successor audit reuses unchanged P7.4 receipts and rechecks only F2–F6 after terminal producers |

## 5. Decision Log

Решения находятся в `decisions/`; собрать или проверить их виды: `python3 packages/task/scripts/plan-views.py decisions --plan-dir <plan-dir> [--check]`.

## 7. Contracts

### Exported

| Контракт | Версия | Статус | Потребители | Уведомлены |
|:--|:--|:--|:--|:--|
| root/contracts/provider-control-plane-v1.md | v1.0.0 | frozen | P2–P7 | D73 |
| root/contracts/locale-resolution-v1.md | v1.0.0 | frozen | P3–P7 | D74 |
| root/contracts/english-authoring-overlay-v1.md | v1.0.0 | frozen | P3–P7 | D77 |
| root/contracts/locale-authoring-review-v1.md | v1.0.0 | frozen | P3–P7 | D77 |
| root/contracts/provider-recovery-gates-v1.md | v1.0.0 | frozen | P0.4–P7 | P0.3/D63 |
| root/contracts/provider-health-v1.md | v1.0.0 | frozen | P6–P7 | P6.2 |
| root/contracts/provider-health-release-membership-v1.schema.json | v1.0.0 | frozen | P6.3–P7 | P6.3/D86 |
| root/contracts/skill-core-v1.md | v1.0.0 | frozen | P2–P7 | P1.2 |
| root/contracts/provider-skill-adapter-v1.md | v1.0.0 | frozen | P3–P7 | P1.2 |
| root/contracts/skill-evidence-v1.md | v1.0.0 | frozen | P3–P7 | D77 |
| artifacts/P7.1/replay-admission-v1.json | v1.0.0 | frozen diagnostic denominator | P7.1, P7.4, P7.7 | D88 (supersedes D87 gate) |

### Consumed

| Контракт | Донор-план | Pinned | Замечено | Реакция |
|:--|:--|:--|:--|
| root/contracts/task-contract-v1.md | 2026.07.24-AGENT-RELIABILITY | v1 | portability defect previously observed | P3 preserves provider-neutral task runtime discovery |
| root/contracts/provider-capability-contract.md | 2026.07.19-DUAL-PROVIDER | v1.0.0 | frozen predecessor available in archive | P0 inventories conformance; P1 extends rather than replaces |
| root/contracts/provider-artifact-contract.md | 2026.07.19-DUAL-PROVIDER | v1.3.0 | frozen predecessor available in archive | P0/P1 preserve ownership, lock and drift semantics |
| root/contracts/provider-config-contract.md | 2026.07.19-DUAL-PROVIDER | v1.0.0 | frozen predecessor available in archive | P1 composes locale/control-plane fields additively |
| root/contracts/provider-migration-gates.md | 2026.07.19-DUAL-PROVIDER | v1.0.0 | frozen predecessor available in archive | P0.3 produces successor recovery gates without weakening G01–G11 |
| root/contracts/provider-skill-publication-contract.md | 2026.07.19-DUAL-PROVIDER | v1.0.0 | frozen predecessor available in archive | P1.2 maps publication ownership without output-to-output conversion |
| root/contracts/provider-command-routing-contract.md | 2026.07.19-DUAL-PROVIDER | v1.0.0 | frozen predecessor available in archive | P1.2 preserves semantic command ownership and provider-qualified projection |
| root/contracts/provider-harness-contract.md | 2026.07.19-DUAL-PROVIDER | v1.0.0 | frozen predecessor available in archive | P1.2 maps harness surfaces and independent security axes |
| root/contracts/provider-instruction-contract.md | 2026.07.19-DUAL-PROVIDER | v1.0.0 | frozen predecessor available in archive | P1.2 preserves common canon plus additive provider extensions |
| root/contracts/provider-analytics-contract.md | 2026.07.19-DUAL-PROVIDER | v1.0.0 | frozen predecessor available in archive | P1.2 maps provider-qualified observed evidence without raw payload leakage |
| root/contracts/read-budget-v1.md | 2026.08.07-PLAN-ECONOMY | v1.1.0 | Layout v2 admission requires a plan-local frozen carrier | D64 forward remediation; P0.5 is materialized now and P0.6–P0.8 remain JIT until terminal predecessors exist |
