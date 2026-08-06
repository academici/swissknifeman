# Индекс плана — 2026.08.03-ARTIFEX-SUPERVISOR

**Обновлён:** 2026-08-05

## Карта директорий

| Путь | Назначение |
|:--|:--|
| `plan.md` | master plan, Routing, Status Board, decisions and contract crosswalk |
| `phases/P0.md … phases/P6.md` | seven phases; P0–P6 detailed to authoring DoR |
| `handoff.md` | rolling next-step pointer |
| `open-questions.md` | owner decision tracker; P5.5 replacement-probe gate resolved by D111 |
| `roadmap.md` | execution map for all 42 manual items; D85–D97 create resolver-valid owner-lawful G1 `packages/artifex`; D103–D104 produce terminal G2; D108–D111 authorize the exact P5.5 G2B/R2 producer before P5.2 without rewriting P4/P5.1 history |
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
| `brief/11-p3.4-no-tool-projection-remediation.md` | brief | P3.4 | current no-tool projection design authority and frozen D74/D77 anti-scope |
| `brief/12-p3.4-successor-manifest-remediation.md` | brief | P3.4 | current P2/P3 manifest ownership remediation authority and immutable-history anti-scope |
| `brief/13-p3-audit-reopen.md` | brief | P3.5–P3.7 | four-step P3 audit reopen scope and frozen-history anti-scope |
| `brief/14-owner-finished-product-guarantee.md` | brief | P3.8, P5.4, P6.1–P6.4, finish | owner requirement that successful plan completion yields a finished Artifex package and public operational surface |
| `brief/15-early-package-cross-phase-finish.md` | brief | finish, design audit, P3.8–P6.4 | exact post-D88 reconcile scope, cold-audit handoff and protected frozen/history/implementation anti-scope |
| `brief/16-audit8-owner-carriers-and-execution.md` | brief | finish, P3.7–P3.8, P6.1–P6.4, design audit | explicit owner grants for exact Harness package/root source/test/lock sets, executable generation/restart and P3.7 isolation requirements |
| `brief/17-audit9-resolver-valid-owner-carriers.md` | brief | finish, P3.8, P6.1–P6.4, design audit | append-forward owner directive plus exact Layer-0 R2 messages preserving the D91/D92 finite scopes |
| `brief/18-owner-close-design-audit-loop.md` | brief | finish, P3.5, later audit checkpoints | explicit owner decision: no audit 11, P3.5 is current Next, later audit loops are capped at two passes/two repeated findings |
| `brief/19-p4.1-terminal-validator-reconciliation.md` | brief | P4.1 | exact terminal-validator regeneration boundary and immutable-history constraints |
| `brief/20-p4.6-status-literal-reconciliation.md` | brief | P4.6 | exact hook-status literal repair authority and no-second-repair boundary |
| `brief/21-p4-audit1-final-remediation.md` | brief | P4.7–P4.8, P4 close/audit | final P4 design pass, F1–F7 forward remediation and resolver-valid P4.8 owner grant |
| `brief/23-p5.2-frozen-contract-reconciliation.md` | brief | P5.2 | owner directive to resolve the G2/business/native Codex conflict as a frozen-contract decision without pilot or P4-history mutation |
| `brief/24-p5-phase-successor-authorization.md` | brief | P5.5, P5.2–P5.4, P6 | owner authorization for exact additive successor generation and whole-phase producer/consumer reconciliation without a pilot |
| `brief/25-p5.5-probe-recovery-request.md` | brief | P5.5 | owner invocation of redesign after exhausted D108 attempts; explicitly not a replacement-probe grant |
| `brief/26-p5.5-probe-r2-owner-grant.md` | brief | P5.5 | direct exact D111 authorization for one schema path and two bounded R2 replacement probes |
| `brief/28-p5.5-terminalization-owner-direction-2026-08-06.md` | brief | P5.5 | direct D113 terminal evidence direction; historical R2 observations stay immutable |
| `brief/29-p5.2-business-execution-bridge-owner-direction-2026-08-06.md` | brief | P5.2 | direct D114 authority for the sole bounded package execution bridge |
| `brief/33-p5.2-seam-ownership-owner-decision-2026-08-06.md` | brief | P5.5, P5.2 | owner's literal two-option selection behind D119 (reopen P5.5, adopt the seam) and D120 (honor the `2.1.222` pin) |
| `brief/34-p5.2-zero-accept-owner-decision-2026-08-06.md` | brief | P5.1, P5.5, P5.2 | owner's literal two-answer selection behind D121 (catalog-resolving seam, three item reopens) and D122 (`G-OWNER-P5.2-RETRY`, `claude-code` wall `600000` ms), plus the owner's own research-method instruction |
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
| `findings/P3.4-no-tool-adapter-conflict-2026-08-04.md` | findings | P3.4 | execution-discovered Claude hard-coded tool widening before provider activity |
| `findings/P3.4-native-no-tool-verification-2026-08-04.md` | findings | P3.4 | installed/first-party Claude empty-tool carrier, Codex no-global-no-tool boundary and version drift |
| `findings/P3.4-successor-manifest-conflict-2026-08-04.md` | findings | P3.4 | reproduced evolved-root P2 hash failure and verified the immutable P2.6 Git snapshot |
| `findings/hooks-stale-source-precondition-2026-08-04.md` | findings | P4.6, P4.4 | reproduced effective-hook warning, exact two stale-source actions and worktree-local repair/recheck owner surface |
| `findings/P4.4-hook-status-literal-conflict-2026-08-05.md` | findings | P4.4 | reproduced terminal/live `green` versus frozen P4.4 `ok` security-prerequisite conflict |
| `findings/P4.1-terminal-precondition-blocked-2026-08-05.md` | findings | P4.1 | reproduced terminal-validator generation precondition and the forward-only repair boundary |
| `findings/P5.2-terminal-g2-native-capability-conflict-2026-08-05.md` | findings | P5.2 | exact G2 business-schema and Codex capability refusals, current official CLI surface and green preflight integrity |
| `findings/P5-successor-provider-surface-2026-08-05.md` | findings | P5.5, P5.2–P6 | G2-only runtime seams, immutable D105 parent bindings, current Codex/Claude versions and trusted preflight rerun |
| `findings/P5.5-probe-recovery-verification-2026-08-05.md` | findings | P5.5 | current partial-worktree state, pre-provider root cause and refreshed first-party provider controls |
| `findings/P5.2-seam-ownership-and-version-drift-2026-08-06.md` | findings | P5.5, P5.2 | reproduced G2B drift (exactly 4 changed files, both hashes), zero-process re-freeze path, on-disk `2.1.222` build and the existing `SKM_CLAUDE_BIN` override |
| `findings/P5.2-task-description-gap-2026-08-06.md` | findings | P5.1, P5.5, P5.2 | verified root cause of `0/3 accepted`: the admission carries no task description, the catalog does, the generator drops it, and slice-01/03's declared files do not exist at the frozen base — with the correction owed to the closing pilot finding |
| `findings/P5.2-external-harness-precedent-2026-08-06.md` | findings | P5.1, P5.5, P5.2, P6 | two owner-directed Perplexity Deep Research passes over nine OSS agent runners and two benchmark harnesses: none dispatches a file list without a task description; under-specification yields no-op success; every Artifex component is individually precedented |
| `findings/P3-P6-early-package-finish-recon-2026-08-04.md` | findings | P3.8, P4.5, P5, P6, finish/audit | reproduced promotion-manifest drift risk, stale five-package/root-router instruction canon and exact Harness generator ownership |
| `findings/P3-P6-audit8-owner-generator-recon-2026-08-04.md` | findings | P3.7–P3.8, P6.1–P6.4, design audit | repo-grounded authorize ordering, lock side effect, durable Codex continuation and temp-isolated validation facts for audit-8 F1–F4 |
| `findings/P3-P6-audit9-authority-resolver-recon-2026-08-05.md` | findings | P3.8, P6.1–P6.4, finish/design audit | exact protected resolver grammar, same-gate ambiguity and missing journal provenance observation from audit 9 |
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
| `research/24-p3.4-native-tool-projection-design.md` | research | P3.4, P4 | D80 forward adapter ownership, exact Claude projection, Codex/version pre-launch refusal and readiness-vs-item-status boundary |
| `research/25-p3.4-successor-manifest-design.md` | research | P3.4, P4 | D81 immutable P2 baseline plus additive current P3 snapshot ownership and validation contract |
| `research/26-p3-audit-reopen-design.md` | research | P3.5–P3.7, P4 | audit F1–F6 forward-remediation topology, evidence/provenance and Task regression closure |
| `research/27-finished-product-outcome-reconcile.md` | research | P3.8, P4–P6, finish/audit | early package SSOT, mandatory finished-product topology and non-terminal NO-GO remediation semantics |
| `research/28-early-package-cross-phase-finish.md` | research | P3.8, P4.5, P5, P6, design audit | G1→G5 generation chain, package/root instruction projection ownership, P6.2/P6.3 split and 39-item DoR verdict |
| `research/29-audit8-authority-generator-reconcile.md` | research | P3.7–P3.8, P6.1–P6.4, finish/design audit | exact D91/D92 authority, D93 generator/restart sequence, D94 read-only/temp isolation and repaired producer→consumer graph |
| `research/30-audit9-resolver-valid-authority-reconcile.md` | research | P3.8, P6.1–P6.4, finish/design audit | D95/D96 R2 carrier topology, D97 successor mapping, protected evaluation matrix and forward-only journal repair |
| `research/31-p4.1-terminal-validator-generation-reconcile.md` | research | P4.1 | generated terminal-validator design, source ownership and clean-tree verification |
| `research/32-p4-audit1-final-remediation.md` | research | P4.7–P4.8, P4 close/audit | F1–F7 synthesis, finite two-item repair chain, G2 successor and audit-pass-2 terminal path |
| `research/34-p5.2-frozen-successor-decision.md` | research | P5.2 | D107 additive-successor choice, rejected bypasses, immutable G2/P4 boundary and explicit non-DoR successor gate |
| `research/35-p5-phase-successor-topology.md` | research | P5.5, P5.2–P5.4, P6 | D108–D109 G2B producer topology, frozen-ID compatibility order and downstream generation reconcile |
| `research/36-p5.5-probe-recovery-design.md` | research | P5.5 | rejected silent retry/synthetic assurance and exact owner-gated R2 proposal with zero-process preflight |
| `research/37-p5.2-seam-ownership-reconcile.md` | research | P5.5, P5.2 | seam is producer surface, not evidence: reopen-vs-refreeze-vs-revert options with the rejected alternatives and the resulting item topology |
| `research/38-p5.2-zero-accept-root-cause-and-options.md` | research | P5.1, P5.5, P5.2, P5.4, P6 | `0/3` is a null measurement, not a negative one: four costed options (catalog resolution · +replacement grant · contract edit · accept-and-continue), why accept-and-continue is the expensive one, and the recommendation the owner selected |

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
| `root/contracts/dispatch-admission-v1.md` | manifest+grant+replay projection into authority, scheduler and worker request | frozen P1.6 |
| `artifacts/P1/p3-smoke-task-set-v1.json`, `p3-smoke-dispatch-grants-v1.json` | provider-specific no-write child task/authority ceilings, distinct from P3.4 | terminal P1.6 |

## Запланированные выходы P2

| Путь | Производитель | Потребители |
|:--|:--|:--|
| `artifacts/supervisor/artifex/compiler.py` | P2.1 | P2.2–P2.5, P3 |
| `artifacts/supervisor/artifex/store.py` | P2.2 | P2.3–P2.5, P4 |
| `artifacts/supervisor/artifex/authority.py` | P2.3 | P2.4–P2.5, P4–P5 |
| `artifacts/supervisor/artifex/scheduler.py` | P2.4 | P2.5, P3–P5 |
| `artifacts/supervisor/artifex/cli.py`, `__main__.py`, `README.md` | P2.5 | P3–P6 |
| `artifacts/P2/prototype-manifest-v1.json`, `validate-prototype.py` | P2.5/P2.6 | immutable P2.6 snapshot consumed by P3.4's successor validator and later provenance checks |
| `artifacts/P2/p3-smoke-dispatch-manifest-index-v1.json`, replay, two admissions/index and `build-p3-smoke-admissions.py` | P2.6 | P3.4–P5 negative lineage |
| `artifacts/supervisor/artifex/dispatch.py` and provider-free `dispatch --admission` CLI seam | P2.6 | P3.4–P5 |

## Запланированные выходы P3

| Путь | Производитель | Потребители |
|:--|:--|:--|
| `artifacts/supervisor/artifex/providers/{common,codex,claude_code}.py` | P3.1–P3.2; narrow native-tool repair P3.4/D80 | P3.3–P5 |
| `artifacts/P3/provider-parity-*`, `validate-provider-parity.py` | P3.3 | P3.4, P4–P5 |
| `artifacts/supervisor/artifex/worker.py` and provider-aware existing CLI binding | P3.4 | P4–P6 |
| `artifacts/P3/provider-smoke/*`, `adapter-manifest-v1.json`, `validate-adapters.py` | P3.4 | additive current-P3 plus immutable-P2 terminal gate for P4/P5 |
| D95 resolver-valid Harness Artifex instruction source/tests/shared lock plus D93-generated `packages/artifex/{CLAUDE.md,AGENTS.md}` | P3.8 stage 1 | atomic generation commit exists before full implementation/high package-cwd Codex continuation and runtime writes |
| `packages/artifex/**`, standalone CLI/tests/validation plus G1 `artifacts/P3/package-promotion-manifest-v1.json`, `validate-package-promotion.py` | P3.8 stage 2 | sole live runtime baseline; current at P3 close, historical after first P4 package mutation |

## Запланированные выходы P4

| Путь | Производитель | Потребители |
|:--|:--|:--|
| `packages/artifex/lib/artifex/faults.py`, `artifacts/P4/fault-*`, `validate-fault-matrix.py` | P4.1 | P4.2–P4.5 |
| Existing candidate recovery owners + `artifacts/P4/recovery-results-v1.json`, `validate-recovery.py` | P4.2 | P4.3–P5 |
| `packages/artifex/lib/artifex/worktree.py`, `artifacts/P4/worktree-*`, `validate-worktree.py` | P4.3 | P4.4–P5 |
| Harness-generated `.codex/hooks.json`/`.codex/hooks/lifecycle.py` plus `artifacts/P4/hook-integrity-results-v1.json`, `validate-hook-integrity.py` | P4.6 | P4.4–P5 |
| `packages/artifex/lib/artifex/security.py`, `artifacts/P4/security-*`, `validate-security.py` | P4.4 | P4.5–P5 |
| `packages/artifex/lib/artifex/telemetry.py`, `artifacts/P4/attention-cases-v1.json`, historical G2 `assurance-manifest-v1.json`, `validate-assurance.py` | P4.5 | historical predecessor requalified only by P4.8; not a terminal P5 gate |
| Harness provider-instructions generator/reference, package-owned run-reader fixture, `provenance-reconciliation-v1.json`, `validate-provenance-reconciliation.py` | P4.7 | reproducible committed-tree Harness gate and append-forward F2–F7 provenance input for P4.8 |
| `authority-requalification-v1.json`, `validate-authority-requalification.py`, separately committed G2 successor and refreshed `validate-assurance.py` evidence | P4.8 | sole current package snapshot for P5 and P6.1 pre-write; terminal input for P4 close |

## Запланированные выходы P5

| Путь | Производитель | Потребители |
|:--|:--|:--|
| `artifacts/P5/trial-catalog-v1.json`, archive mapping/shadow results and `validate-shadow.py` | P5.1 | P5.2–P5.4 |
| `artifacts/P5/business-grant-request-v1.json`, business grants, per-trial manifest/replay/admission indexes and validators | P5.1 after `G-OWNER-P5-BUSINESS` | P5.2–P5.4 |
| `artifacts/P5/run-pilot.py`, repository pilot results and validator | P5.2 | P5.3–P5.4 |
| `artifacts/P5/recovery-pilot-results-v1.json`, `validate-recovery-pilot.py` | P5.3 | P5.4/P6 |
| `artifacts/P5/battle-wave-results-v1.json`, `economic-verdict-v1.json`, G3 `pilot-manifest-v1.json`, `validate-economic-verdict.py` | P5.4 | P6; pins unchanged measured G2 package digest |

## Запланированные выходы P6

| Путь | Производитель | Потребители |
|:--|:--|:--|
| `artifacts/P6/product-home-*`, P6.2/P6.3-owned root/public/instruction `integration-scope-v1.json`, `validate-product-home.py` | P6.1 | P6.2–P6.4 |
| exact `swissknifeman artifex` route, package-installer delegation, D96 resolver-valid Harness root source/tests/shared lock, D93-generated root projections and G4 `integration-manifest-v1.json`/validator | P6.2 | P6.3–P6.4; preserves protected G2B runtime and immutable G2 predecessor plus exact generator lineage |
| installer/update/doctor/config/docs/CHANGELOG scope plus compatibility/rollback and G5 operations manifest/validator | P6.3 | P6.4 |
| `artifacts/P6/release-candidate-audit-v1.json`, `validate-release-candidate-audit.py` | P6.4 | cold G1→G2→G2B→G3→G4→G5 product/instruction audit, phase close and release decision |
