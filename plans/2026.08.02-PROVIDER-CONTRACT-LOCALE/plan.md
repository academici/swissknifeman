# План

## 0. Meta

| Поле | Значение |
|:--|:--|
| Plan ID | 2026.08.02-PROVIDER-CONTRACT-LOCALE |
| Title | Provider control plane, localization, and fleet recovery |
| Document Type | Executable Master Plan |
| Authoring Model | gpt-5.6-sol/high |
| Repository | swissknifeman |
| Related Packages | skiller · harness · maind · task · core |
| Execution Mode | phase-first, contract-first |
| Target Operator Models | implementation (execution) · economy (recon) · frontier (design/audit) |
| Approval Owner | repository owner |
| Home | repo:swissknifeman |
| visibility | private |
| Paused By | 2026.08.03-ARTIFEX-SUPERVISOR, 2026-08-03 |
| Design Passes | 3/3 — cross-phase `finish` plus targeted audit remediation F1–F25 reconciled all P0–P7 contracts, brief coverage, routing and the final execution roadmap; repeated independent design audit is next |
| Layout | v2 |
<!-- migration-version: 1.0.5 -->

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

## 2. Execution Rules

- Canonical intent is the only cross-provider source of truth; adapters own only projections and status.
- Claude Code and Codex may not write each other's target files or share mutable adapter state.
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
| P0.1 | implementation/high | manual | prescribed read-only fleet capture and final evidence verification; high effort is mandatory, frontier tier is not |
| P0.2–P0.3 | frontier/high | manual | ambiguous ownership classification and a recovery contract that freezes fleet/security boundaries |
| P0.4 | implementation/high | manual | execute only the exact owner-approved external containment transaction and verify rollback |
| P1.1 | frontier/high | manual | freezes the desired/status schema and diagnostics with open contract decisions |
| P1.2 | frontier/high | manual | freezes ecosystem-wide capability negotiation and provider ownership boundaries |
| P1.3 | frontier/high | manual | freezes migration/rollback authority and compatibility after Owner approval |
| P2.1–P2.3 | frontier/high | manual | locale contract and compact-English authoring decisions are still open |
| P3.1 | implementation/high | manual | public shared-core resolver against frozen P1/P2 contracts; high effort is mandatory while implementation tier remains sufficient |
| P3.2 | implementation/high | manual | multi-package adapter boundary and ownership-preserving reconciliation against frozen contracts |
| P3.3 | implementation/high | manual | redacted status/diagnostic semantics feed later migration and fleet gates; full review is mandatory |
| P4.1 | implementation/high | manual | public locale runtime and provider render boundary against frozen contracts; full review required |
| P4.2 | implementation/high | manual | migration admission/rollback validator becomes the write gate for repository canon |
| P4.3 | implementation/high | manual | skill source-ownership migration changes canon consumed by every project; full review required |
| P4.4 | implementation/high | manual | command/plugin/diagnostic migration must preserve parser literals and provider parity |
| P4.5 | implementation/high | manual | broad code-prose migration requires behavior/literal preservation and full review |
| P4.6 | implementation/high | manual | terminal docs/corpus migration and protected generated-artifact regeneration/readback |
| P5.1 | frontier/high | manual | freezes the exact fleet action manifest and Owner authority while classifications/actions remain decision-bearing |
| P5.2 | implementation/high | manual | live project-owned override registration is external-state work against a frozen action set; full review required |
| P5.3 | implementation/high | manual | cross-project provider repair applies frozen adapters with per-project rollback; full review required |
| P5.4 | implementation/high | manual | destructive-boundary quarantine and final fleet convergence require high-effort verification and full review |
| P6.1 | implementation/high | manual | protected external Brain security/profile transaction with Owner gate and rollback; full review required |
| P6.2 | frontier/high | manual | freezes ecosystem-wide provider-health contract and composes multi-package public diagnostics; full review required |
| P6.3 | implementation/high | manual | final exact-set external fleet evidence and non-masking release gate; high effort and full review required |
| P7.1 | implementation/high | manual | exact-set provider acceptance composes frozen multi-package/fleet evidence; full review required |
| P7.2 | implementation/high | manual | cross-package release regressions at frozen provider/locale seams; full review required |
| P7.3 | implementation/high | manual | generated docs, full validation and release-candidate assembly; no tag/push/publish |
| P7.4 | frontier/xhigh | manual | cold adversarial parity/release audit with an Owner-facing verdict |

## 5. Decision Log

Решения находятся в `decisions/`; собрать или проверить их виды: `python3 packages/task/scripts/plan-views.py decisions --plan-dir <plan-dir> [--check]`.

## 7. Contracts

### Exported

| Контракт | Версия | Статус | Потребители | Уведомлены |
|:--|:--|:--|:--|:--|
| root/contracts/provider-control-plane-v1.md | v1.0.0-draft | draft | P2–P7 | — |
| root/contracts/locale-resolution-v1.md | v1.0.0-draft | draft | P3–P7 | — |
| root/contracts/english-authoring-overlay-v1.md | v1.0.0-draft | draft | P3–P7 | — |
| root/contracts/locale-authoring-review-v1.md | v1.0.0-draft | draft | P3–P7 | — |
| root/contracts/provider-recovery-gates-v1.md | v1.0.0-draft | draft | P0.4–P7 | — |
| root/contracts/provider-health-v1.md | v1.0.0-draft | draft | P6–P7 | — |

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
