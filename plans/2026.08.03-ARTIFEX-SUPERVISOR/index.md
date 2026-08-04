# Индекс плана — 2026.08.03-ARTIFEX-SUPERVISOR

**Обновлён:** 2026-08-04

## Карта директорий

| Путь | Назначение |
|:--|:--|
| `plan.md` | master plan, Routing, Status Board, decisions and contract crosswalk |
| `phases/P0.md … phases/P6.md` | seven phases; P0–P6 detailed to authoring DoR |
| `handoff.md` | rolling next-step pointer |
| `roadmap.md` | execution map for all 35 manual items; post-audit D77–D79 remediation is complete and execution remains design-audit-gated |
| `journal.jsonl` | append-only plan-command provenance |
| `brief/` | direct owner intent and non-goals |
| `findings/` | repository recon, first-party verification, reference products, preflight, P1–P6 reconciliation and finish recheck |
| `research/` | synthesized architecture, authority, recovery, economy, package-boundary, P1–P6 designs and cross-phase finish |

## Провенанс

| Источник | Слой | Питает | Суть |
|:--|:--|:--|:--|
| `brief/00-brief.md` | brief | P0–P6 | owner canons, interaction model and token-economy objective |
| `brief/02-p2.1-remediation.md` | brief | P2.1 | post-P0 owner directives and frozen-source remediation boundary |
| `brief/03-p2.4-circuit-breaker-remediation.md` | brief | P2.4 | escalation scope, frozen-contract anti-scope and redesign authorization |
| `brief/04-p3.3-required-reads-remediation.md` | brief | P3.3 | owner-authorized Required Reads repair with frozen-contract anti-scope |
| `brief/05-p3.4-required-reads-remediation.md` | brief | P3.4 | owner-authorized execution-input repair with frozen-contract and no-implementation anti-scope |
| `brief/06-p3.4-bridge-contract-gate.md` | brief | P3.4 | owner gate for frozen P1/P2 bridge scope; no implicit contract expansion or scope reduction |
| `brief/07-p3.4-successor-contract-choice.md` | brief | P1.6, P2.6, P3.4 | explicit owner selection of the successor-contract path and its anti-scope |
| `brief/08-post-d74-finish.md` | brief | finish, design audit | explicit owner directive to reconcile D74 and rebuild the roadmap without implementation authority |
| `brief/09-post-d74-audit-remediation.md` | brief | finish remediation, design audit | exact F1–F3 remediation scope, verification duties and anti-scope |
| `brief/10-post-d76-audit-remediation.md` | brief | finish remediation, design audit | exact smoke/business-admission/hook producer scope and protected terminal history |
| `findings/00-repo-recon-2026-08-03.md` | findings | P0–P2, P6 | FOREMAN absorption, live carriers and missing runtime |
| `findings/01-external-agent-runtime-2026-08-03.md` | findings | P0, P1, P3, P4 | current official subagent, long-horizon and durability facts |
| `findings/02-reference-products-2026-08-03.md` | findings | P1–P5 | Maestro/Superset adopt-adapt-reject pattern review |
| `findings/03-preflight-2026-08-03.md` | findings | P0 | dirty-tree/runtime baseline and stale Codex lifecycle hook evidence |
| `findings/04-p0-design-verification-2026-08-03.md` | findings | P0.1, P0.3 | live `harness run` baseline correction, repeated hook defect and first-party provider recheck |
| `findings/05-p1-donor-reconciliation-2026-08-03.md` | findings | P1.1–P1.5 | terminal-P0 precondition, six donor boundaries and live-driver reuse/gap verdict |
| `findings/06-p2-runtime-recon-2026-08-03.md` | findings | P2.1–P2.5, P4 | live Harness/Task process boundary, strict-vs-tolerant storage gaps, Python 3.12 durability APIs and repeated hook defect |
| `findings/07-p3-provider-runtime-recon-2026-08-03.md` | findings | P3.1–P3.4, P4 | current Codex/Claude CLI and permission surfaces, provider donors/gaps, fresh/child boundary and non-green hook preflight |
| `findings/08-p4-recovery-security-recon-2026-08-03.md` | findings | P4.1–P4.5, P5 | recovery/security owner seams, current official Git worktree boundary, effective hook/health preflight and empirical gaps |
| `findings/09-p5-pilot-economy-recon-2026-08-03.md` | findings | P5.1–P5.4, P6 | current provider usage/cost surfaces, archive inputs, P4 gate, hook defect and empirical measurement boundary |
| `findings/10-p6-productization-recon-2026-08-03.md` | findings | P6.1–P6.4 | current Task/Harness/root ownership, closed home predicates, generator boundary and repeated hook defect |
| `findings/11-finish-verification-2026-08-03.md` | findings | finish, design audit | same-day primary-source fact-class refresh, repository preflight and retained empirical boundaries |
| `findings/12-p2.1-process-projection-recon-2026-08-04.md` | findings | P2.1 | live S1/S2/S3 process outputs, omitted plan-model carrier and no-package-change verdict |
| `findings/13-p2.1-terminal-fixture-recon-2026-08-04.md` | findings | P2.1 | reproduced sibling-derived fixture failure and stable Harness terminal-exclusion boundary |
| `findings/14-p2.4-circuit-breaker-recon-2026-08-04.md` | findings | P2.4 | frozen authority/run transition crosswalk and no-version-bump verdict |
| `findings/P3.3-required-read-defect-2026-08-04.md` | findings | P3.3 | reproduced omission of the normative worker-envelope taxonomy from finite execution inputs |
| `findings/P3.4-required-read-defect-2026-08-04.md` | findings | P3.4 | reproduced omission of the slice/authority/activity/worker owner chain from finite execution inputs |
| `findings/P3.4-bridge-contract-conflict-2026-08-04.md` | findings | P3.4 | reproduced the terminal P1/P2 authority, budget and CLI-dispatch conflict blocking a lawful bridge |
| `findings/hooks-stale-source-precondition-2026-08-04.md` | findings | P4.6, P4.4 | reproduced effective-hook warning, exact two stale-source actions and worktree-local repair/recheck owner surface |
| `research/00-user-intent.md` | research | P0.2, P0.5, P1.3 | executable interpretation of owner intent |
| `research/01-target-architecture.md` | research | P1–P4 | deterministic external supervisor boundary and components |
| `research/02-authority-and-conflict-policy.md` | research | P0.2, P1.3, P2.3 | authority precedence and routine conflict resolution |
| `research/03-durable-state-and-recovery.md` | research | P1.1, P2.2, P4.1–P4.2 | WAL, replay, reconcile and crash matrix |
| `research/04-token-economy-and-acceptance.md` | research | P0.1, P0.5, P1.5, P5 | matched baselines, normalized metrics and GO/NO-GO |
| `research/05-package-boundary-and-rollout.md` | research | P2, P6 | plan-local prototype and measured promotion decision |
| `research/06-p0-evidence-freeze-design.md` | research | P0.1–P0.5, P1 | sequential P0 producer/consumer design, artifact discipline and stop condition |
| `research/07-p1-contract-freeze-design.md` | research | P1.1–P1.5, P2 | contract dependency graph, alternatives, no-workflow verdict and high-stakes pre-mortem |
| `research/08-p2-prototype-design.md` | research | P2.1–P2.5, P3–P4 | plan-local module ownership, process boundaries, no-provider core, CLI contract and high-stakes pre-mortem |
| `research/09-p3-provider-adapter-design.md` | research | P3.1–P3.4, P4–P5 | pure adapter ownership, shared bounded runner, parity/freshness/child policy, validation and pre-mortem |
| `research/10-p4-assurance-design.md` | research | P4.1–P4.5, P5 | exact fault chain, no-rerun reconcile, linked-worktree lane, security adjudication, owner telemetry and pre-mortem |
| `research/11-p5-pilot-economics-design.md` | research | P5.1–P5.4, P6 | frozen trial catalog, archive shadow, reversible/recovery pilots, five paired waves, independent verdict and pre-mortem |
| `research/12-p6-productization-design.md` | research | P6.1–P6.4, finish | measured home state machine, branch-locked integration, opt-in compatibility/rollback, cold audit and pre-mortem |
| `research/13-finish-reconcile.md` | research | finish, design audit, P0–P6 | complete producer/consumer graph, repair coupling, exact Required Reads, routing and DoR verdict |
| `research/14-p2.1-source-reconciliation.md` | research | P2.1 | exact S1/S2/S3 mapping, strict scope projection, source pins and adversarial test strategy |
| `research/15-p2.1-terminal-fixture-remediation.md` | research | P2.1 | item-owned S3 fixture, separate live boundary smoke test and P2.3-preserving repair scope |
| `research/16-p2.4-circuit-breaker-reconciliation.md` | research | P2.4 | exact retry-budget-to-run-state mapping, post-boundary sequence and deterministic proof obligations |
| `research/19-p3.4-bridge-feasibility.md` | research | P3.4 | frozen-carrier feasibility verdict, rejected shortcut and exact owner decision gate |
| `research/17-p3.3-required-read-reconciliation.md` | research | P3.3 | normative contract→cases→validator read order and unchanged parity acceptance boundary |
| `research/18-p3.4-execution-input-reconciliation.md` | research | P3.4 | normative slice→authority/activity→worker read order and additive P2/P3 bridge boundary |
| `research/20-p3.4-successor-contract-design.md` | research | P1.6, P2.6, P3.4 | forward-only dispatch-admission contract, provider-free integration seam and execution order |
| `research/21-post-d74-finish-reconcile.md` | research | finish, design audit, P0–P6 | post-D74 producer/consumer graph, coupling-hotspot and DoR reconcile over the current 34-item topology |
| `research/22-post-d74-audit-remediation-reconcile.md` | research | finish remediation, design audit, P1.6–P5.1 | exact grant≠admission ownership, assurance propagation, current handoffs and repaired 34-item producer→consumer graph |
| `research/23-post-d76-audit-remediation-reconcile.md` | research | finish remediation, design audit, P1.6–P5.4 | separate no-write smoke carriers, owner-bound per-trial business authority, P4.6 hook producer and repaired 35-item graph |

## Запланированные выходы P0

| Путь | Производитель | Потребители |
|:--|:--|:--|
| `artifacts/P0/baseline-*` | P0.1 | P0.5, P1.1, P1.5, P5 |
| `artifacts/P0/owner-mandate-input-v1.json`, `authority-cases-v1.json` | P0.2 | P0.4–P0.5, P1.2–P1.4, P2.3 |
| `artifacts/P0/provider-*` | P0.3 | P0.4–P0.5, P1.4–P1.5, P3 |
| `research/08-threat-model-and-premortem.md`, `artifacts/P0/threat-cases-v1.json` | P0.4 | P0.5, P1, P4 |
| `artifacts/P0/acceptance-*`, `research/09-p0-freeze-crosswalk.md` | P0.5 | P1, P4, P5 |

## Ключевые артефакты `root/`

| Артефакт | Суть | Статус |
|:--|:--|:--|
| `root/contracts/supervisor-run-v1.md` | run state, journal and recovery contract | frozen P1.1 |
| `root/contracts/slice-manifest-v1.md` | plan-to-slice compilation contract | frozen P1.2 |
| `root/contracts/authority-policy-v1.md` | AUTO/AUTO-FIX/OWNER authority contract | frozen P1.3 |
| `root/contracts/worker-envelope-v1.md` | provider-neutral worker/result taxonomy | frozen P1.4 |
| `root/contracts/economy-evidence-v1.md` | token/cost/intervention evidence and verdict | frozen P1.5 |
| `root/contracts/dispatch-admission-v1.md` | manifest+grant+replay projection into authority, scheduler and worker request | planned P1.6 |
| `artifacts/P1/p3-smoke-task-set-v1.json`, `p3-smoke-dispatch-grants-v1.json` | provider-specific no-write child task/authority ceilings, distinct from P3.4 | planned P1.6 |

## Запланированные выходы P2

| Путь | Производитель | Потребители |
|:--|:--|:--|
| `artifacts/supervisor/artifex/compiler.py` | P2.1 | P2.2–P2.5, P3 |
| `artifacts/supervisor/artifex/store.py` | P2.2 | P2.3–P2.5, P4 |
| `artifacts/supervisor/artifex/authority.py` | P2.3 | P2.4–P2.5, P4–P5 |
| `artifacts/supervisor/artifex/scheduler.py` | P2.4 | P2.5, P3–P5 |
| `artifacts/supervisor/artifex/cli.py`, `__main__.py`, `README.md` | P2.5 | P3–P6 |
| `artifacts/P2/prototype-manifest-v1.json`, `validate-prototype.py` | P2.5 | P3/P4 terminal gate |
| `artifacts/P2/p3-smoke-dispatch-manifest-index-v1.json`, replay, two admissions/index and `build-p3-smoke-admissions.py` | P2.6 | P3.4–P5 negative lineage |
| `artifacts/supervisor/artifex/dispatch.py` and provider-free `dispatch --admission` CLI seam | P2.6 | P3.4–P5 |

## Запланированные выходы P3

| Путь | Производитель | Потребители |
|:--|:--|:--|
| `artifacts/supervisor/artifex/providers/{common,codex,claude_code}.py` | P3.1–P3.2 | P3.3–P5 |
| `artifacts/P3/provider-parity-*`, `validate-provider-parity.py` | P3.3 | P3.4, P4–P5 |
| `artifacts/supervisor/artifex/worker.py` and provider-aware existing CLI binding | P3.4 | P4–P6 |
| `artifacts/P3/provider-smoke/*`, `adapter-manifest-v1.json`, `validate-adapters.py` | P3.4 | P4/P5 terminal gate |

## Запланированные выходы P4

| Путь | Производитель | Потребители |
|:--|:--|:--|
| `artifacts/supervisor/artifex/faults.py`, `artifacts/P4/fault-*`, `validate-fault-matrix.py` | P4.1 | P4.2–P4.5 |
| Existing candidate recovery owners + `artifacts/P4/recovery-results-v1.json`, `validate-recovery.py` | P4.2 | P4.3–P5 |
| `artifacts/supervisor/artifex/worktree.py`, `artifacts/P4/worktree-*`, `validate-worktree.py` | P4.3 | P4.4–P5 |
| Harness-generated `.codex/hooks.json`/`.codex/hooks/lifecycle.py` plus `artifacts/P4/hook-integrity-results-v1.json`, `validate-hook-integrity.py` | P4.6 | P4.4–P5 |
| `artifacts/supervisor/artifex/security.py`, `artifacts/P4/security-*`, `validate-security.py` | P4.4 | P4.5–P5 |
| `artifacts/supervisor/artifex/telemetry.py`, `artifacts/P4/attention-cases-v1.json`, `assurance-manifest-v1.json`, `validate-assurance.py` | P4.5 | P5–P6 |

## Запланированные выходы P5

| Путь | Производитель | Потребители |
|:--|:--|:--|
| `artifacts/P5/trial-catalog-v1.json`, archive mapping/shadow results and `validate-shadow.py` | P5.1 | P5.2–P5.4 |
| `artifacts/P5/business-grant-request-v1.json`, business grants, per-trial manifest/replay/admission indexes and validators | P5.1 after `G-OWNER-P5-BUSINESS` | P5.2–P5.4 |
| `artifacts/P5/run-pilot.py`, repository pilot results and validator | P5.2 | P5.3–P5.4 |
| `artifacts/P5/recovery-pilot-results-v1.json`, `validate-recovery-pilot.py` | P5.3 | P5.4/P6 |
| `artifacts/P5/battle-wave-results-v1.json`, `economic-verdict-v1.json`, `pilot-manifest-v1.json`, `validate-economic-verdict.py` | P5.4 | P6 |

## Запланированные выходы P6

| Путь | Производитель | Потребители |
|:--|:--|:--|
| `artifacts/P6/product-home-*`, `integration-scope-v1.json`, `validate-product-home.py` | P6.1 | P6.2–P6.4 |
| `artifacts/P6/integration-manifest-v1.json`, `validate-integration.py` or roadmap-only return | P6.2 | P6.3–P6.4 |
| `artifacts/P6/compatibility-matrix-v1.json`, rollback/operations manifests and validator or D-backed skip | P6.3 | P6.4 |
| `artifacts/P6/release-candidate-audit-v1.json`, `validate-release-candidate-audit.py` | P6.4 | phase close, final design audit and release decision |
