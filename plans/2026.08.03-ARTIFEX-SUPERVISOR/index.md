# Индекс плана — 2026.08.03-ARTIFEX-SUPERVISOR

**Обновлён:** 2026-08-04

## Карта директорий

| Путь | Назначение |
|:--|:--|
| `plan.md` | master plan, Routing, Status Board, decisions and contract crosswalk |
| `phases/P0.md … phases/P6.md` | seven phases; P0–P6 detailed to authoring DoR |
| `handoff.md` | rolling next-step pointer |
| `roadmap.md` | final execution map for all 32 manual items; execution remains audit-gated |
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
| `root/contracts/supervisor-run-v1.md` | run state, journal and recovery contract | planned P1.1 |
| `root/contracts/slice-manifest-v1.md` | plan-to-slice compilation contract | planned P1.2 |
| `root/contracts/authority-policy-v1.md` | AUTO/AUTO-FIX/OWNER authority contract | planned P1.3 |
| `root/contracts/worker-envelope-v1.md` | provider-neutral worker/result taxonomy | planned P1.4 |
| `root/contracts/economy-evidence-v1.md` | token/cost/intervention evidence and verdict | planned P1.5 |

## Запланированные выходы P2

| Путь | Производитель | Потребители |
|:--|:--|:--|
| `artifacts/supervisor/artifex/compiler.py` | P2.1 | P2.2–P2.5, P3 |
| `artifacts/supervisor/artifex/store.py` | P2.2 | P2.3–P2.5, P4 |
| `artifacts/supervisor/artifex/authority.py` | P2.3 | P2.4–P2.5, P4–P5 |
| `artifacts/supervisor/artifex/scheduler.py` | P2.4 | P2.5, P3–P5 |
| `artifacts/supervisor/artifex/cli.py`, `__main__.py`, `README.md` | P2.5 | P3–P6 |
| `artifacts/P2/prototype-manifest-v1.json`, `validate-prototype.py` | P2.5 | P3/P4 terminal gate |

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
| `artifacts/supervisor/artifex/security.py`, `artifacts/P4/security-*`, `validate-security.py` | P4.4 | P4.5–P5 |
| `artifacts/supervisor/artifex/telemetry.py`, `artifacts/P4/attention-cases-v1.json`, `assurance-manifest-v1.json`, `validate-assurance.py` | P4.5 | P5–P6 |

## Запланированные выходы P5

| Путь | Производитель | Потребители |
|:--|:--|:--|
| `artifacts/P5/trial-catalog-v1.json`, archive mapping/shadow results and `validate-shadow.py` | P5.1 | P5.2–P5.4 |
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
