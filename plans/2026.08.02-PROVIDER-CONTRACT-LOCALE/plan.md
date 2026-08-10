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
| Execution Mode | phase-first, contract-first, evidence-led |
| Target Operator Models | implementation (execution) · economy (recon) · frontier (design/audit) |
| Approval Owner | repository owner |
| Home | repo:swissknifeman |
| visibility | private |
| Paused By | 2026.08.03-ARTIFEX-SUPERVISOR, 2026-08-03 |
| Design Passes | 4/4 — semantic design remains accepted; D64 records a post-execution P0 RED-audit reopen through P0.5–P0.8 without adding a fifth whole-plan design pass or ninth whole-plan audit |
| Layout | v2 |
<!-- migration-version: 1.1.2 -->

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

## 3. Routing

| Items | Model class/effort | Exec | Why |
|:--|:--|:--|:--|
| P0.1 | implementation/high | manual | prescribed read-only fleet plus current skill/audit/profile baseline with typed uncertainty and provider availability; high effort is mandatory, frontier tier is not |
| P0.2–P0.3 | frontier/high | manual | ambiguous ownership classification and a recovery contract that freezes fleet/security boundaries |
| P0.4 | implementation/high | manual | execute only the exact owner-approved external containment transaction and verify rollback |
| P0.5 | implementation/high | manual | prescribed exact-set/privacy evidence repair against audit F1–F2; high effort is mandatory, frontier tier is not |
| P0.6 | frontier/high | manual | corrective frozen-contract topology and exact new owner freeze remain decision-bearing |
| P0.7 | implementation/high | manual | prescribed executable redacted security-evidence producer against D64–D65; high effort and full review required |
| P0.8 | implementation/high | manual | append-only provenance reconciliation and committed-tree phase requalification; high effort and full review required |
| P1.1 | frontier/high | manual | freezes the desired/status schema and diagnostics with open contract decisions |
| P1.2 | frontier/high | manual | freezes the minimum Skill Core, capability negotiation, additive provider adapters, invocation intent and third-provider seam |
| P1.3 | frontier/high | manual | freezes migration/rollback authority and compatibility after Owner approval |
| P2.1–P2.3 | frontier/high | manual | locale plus current-model compact authoring, progressive disclosure and eval/ablation contracts are still open |
| P3.1 | implementation/high | manual | public shared-core resolver against frozen P1/P2 contracts; high effort is mandatory while implementation tier remains sufficient |
| P3.2 | implementation/high | manual | multi-package additive skill/provider adapter boundary, provider registration and ownership-preserving reconciliation against frozen contracts |
| P3.3 | implementation/high | manual | multi-label audit graph, typed batch failures and provider-qualified measurement/status feed later migration and fleet gates; full review is mandatory |
| P4.1 | implementation/high | manual | public locale runtime and provider render boundary against frozen contracts; full review required |
| P4.2 | implementation/high | manual | one canonical lean template plus semantic/provider-adapter admission and rollback validation becomes the write gate for repository canon |
| P4.3 | implementation/high | manual | evidence-admitted skill consolidation/thinning/reclassification changes canon consumed by every project; full review required |
| P4.4 | implementation/high | manual | command/plugin/diagnostic migration must preserve parser literals and provider parity |
| P4.5 | implementation/high | manual | broad code-prose migration requires behavior/literal preservation and full review |
| P4.6 | implementation/high | manual | terminal docs/corpus migration and protected generated-artifact regeneration/readback |
| P5.1 | frontier/high | manual | freezes the exact fleet action manifest and Owner authority while classifications/actions remain decision-bearing |
| P5.2 | implementation/high | manual | live project-owned override registration is external-state work against a frozen action set; full review required |
| P5.3 | implementation/high | manual | cross-project provider repair applies frozen adapters with per-project rollback; full review required |
| P5.4 | implementation/high | manual | destructive-boundary quarantine and final fleet convergence require high-effort verification and full review |
| P6.1 | implementation/high | manual | protected external Brain security/profile transaction with Owner gate and rollback; full review required |
| P6.2 | frontier/high | manual | freezes provider-qualified discovery/context health, uncertainty/drift probes and accepted degradation; full review required |
| P6.3 | implementation/high | manual | final exact-set external fleet evidence and non-masking release gate; high effort and full review required |
| P7.1 | implementation/high | manual | exact-set real Claude/Codex no-skill/minimal/provider-tuned replay and instruction ablation compose frozen evidence; full review required |
| P7.2 | implementation/high | manual | deterministic cross-package regressions harden P7.1 outcomes without substituting synthetic evidence for provider behavior |
| P7.3 | implementation/high | manual | generated docs, full validation and release-candidate assembly; no tag/push/publish |
| P7.4 | frontier/xhigh | manual | cold adversarial parity/release audit with an Owner-facing verdict |

## 5. Decision Log

Решения находятся в `decisions/`; собрать или проверить их виды: `python3 packages/task/scripts/plan-views.py decisions --plan-dir <plan-dir> [--check]`.

## 6. Update Log

| Дата | Кто (role/model) | Что |
|:--|:--|:--|
| 2026-08-10 | designer/gpt-5.6-sol/high | P0.7 redesigned by D68: its plan-local producer owns branch verification; the frozen P0.6 checker remains an input. |

## 7. Contracts

### Exported

| Контракт | Версия | Статус | Потребители | Уведомлены |
|:--|:--|:--|:--|:--|
| root/contracts/provider-control-plane-v1.md | v1.0.0-draft | draft | P2–P7 | — |
| root/contracts/locale-resolution-v1.md | v1.0.0-draft | draft | P3–P7 | — |
| root/contracts/english-authoring-overlay-v1.md | v1.0.0-draft | draft | P3–P7 | — |
| root/contracts/locale-authoring-review-v1.md | v1.0.0-draft | draft | P3–P7 | — |
| root/contracts/provider-recovery-gates-v1.md | v1.0.0 | frozen | P0.4–P7 | P0.3/D63 |
| root/contracts/provider-health-v1.md | v1.0.0-draft | draft | P6–P7 | — |
| root/contracts/skill-core-v1.md | v1.0.0-draft | draft | P2–P7 | — |
| root/contracts/provider-skill-adapter-v1.md | v1.0.0-draft | draft | P3–P7 | — |
| root/contracts/skill-evidence-v1.md | v1.0.0-draft | draft | P3–P7 | — |

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
