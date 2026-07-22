# Индекс плана — `2026.07.19-DUAL-PROVIDER`

**Обновлён:** 2026-07-22

## Карта директорий

| Путь | Назначение |
|:--|:--|
| `plan.md` | мета, scope, routing, status board и решения |
| `phases/P0.md … P7.md` | все 8 фаз детализированы до DoR; 51 item, skeleton markers отсутствуют; D106 добавляет только P6.9→P6.10 |
| `handoff.md` | rolling next-step для холодного старта |
| `roadmap.md` | полная execution map 51/51 с GPT-5.6 Sol/Terra routing и owner gates |
| `journal.jsonl` | append-only журнал plan-команд |
| `journal-exceptions.jsonl` | optional append-only owner-gated provenance exceptions для historical schema-invalid journal rows |
| `brief/` | полный вход владельца, включая launch/hook и environment-defect refinements |
| `findings/` | repo/provider evidence, immutable P0.1/P0.5 carriers, P0 clean-reproducibility repair, package recon P2/P3/P5, P3.5 unmanaged-provider-B reproduction и current OpenAI model routing |
| `artifacts/p0-evidence-anchors.json` | v1 sealed source-tree/input anchors for P0.1/P0.5 replay; D64 records only one external plugin path, never its contents |
| `artifacts/d65-main-reconciliation-check.py` + `artifacts/d65-main-reconciliation.json` | stdlib-only D65-A/D68 exact-path checker и sealed base/main/delivery hash manifest; D71 records its completed main reconciliation and retained stash recovery point |
| `research/` | traceability, architecture/sequence и phase design syntheses P0–P7 |
| `root/contracts/` | frozen P0 capability/artifact/migration-gate + draft config/harness/analytics contracts; skill/command contracts создаются своими owner-gated items |
| `root/adr/` | архитектурные решения плана; ADR-0001 фиксирует canonical source → deterministic adapters |

## Провенанс

| Источник | Слой | Питает | Суть |
|:--|:--|:--|:--|
| `findings/repository-baseline-2026-07-19.md` | findings | P0–P7 | реальный масштаб и package seams |
| `findings/P0-provider-coupling-baseline.md` | findings | P0.1–P0.3 | anchored, reproducible current inventory and classified provider seams |
| `findings/P0-command-surface-correction.md` | findings | P0.5–P0.3 | terminal umbrella command-surface anchor; не переписывает historical P0.1 evidence |
| `findings/P0-red-reproducibility-preflight-2026-07-20.md` | findings | P0.6 | clean committed-tree RED reproduction, immutable evidence anchors и exact prerequisite boundary |
| `findings/P0-clean-reproducibility-repair.md` | findings | P0.6 | object-based replay attribution; D64 sealed external path-only correction without live node_modules fallback |
| `findings/P0-isolated-cli-root-resolution-defect-2026-07-20.md` | findings | P0.7, pre-P7.4 reconciliation | path-only evidence bare/global CLI root defect, restored derived state и isolated write invariant |
| `findings/P0-codex-launch-hook-defects-2026-07-20.md` | findings | bootstrap, P5–P7 | exit-127 dangling hook, duplicate global logger, local repair и launch preflight |
| `findings/provider-capabilities-2026-07-19.md` | findings | P0, P3–P5 | first-party provider facts |
| `findings/upstream-patterns-2026-07-19.md` | findings | P0–P3 | проверенные multi-provider patterns |
| `findings/P3-skiller-publication-recon-2026-07-19.md` | findings | P3–P4 | current skiller publication/install/marketplace seams |
| `findings/P3.5-provider-b-unmanaged-partial-success-2026-07-20.md` | findings | re-opened P3.4, P3.5 | synthetic unmanaged Codex vendor conflict was skipped yet reported as success |
| `findings/P5-harness-recon-2026-07-19.md` | findings | P5–P6 | current settings/hooks/MCP/agent-pack ownership seams |
| `findings/P7-openai-model-routing-2026-07-19.md` | findings | Routing, roadmap, P7 | official current GPT-5.6 Sol/Terra/Luna role guidance |
| `findings/journal-remediation-verification-2026-07-19.md` | findings | journal gate, design audit r3 | anchored 0/0 lint, tests, exact exception provenance |
| `findings/journal-same-plan-remediation-verification-2026-07-20.md` | findings | journal gate, design audit r4 | canonical directory-ID binding, wrong-plan red probe и negative-test matrix |
| `research/00-user-intent-traceability.md` | research | все фазы | мысль владельца → deliverable |
| `research/01-target-architecture-options.md` | research | P0–P2 | выбранная adapter architecture |
| `research/02-sequence-and-boundaries.md` | research | Status Board | порядок и границы с FOREMAN/fleet |
| `research/03-p0-design-and-premortem.md` | research | P0 | item dependency chain, owner gates, pre-mortem mitigations |
| `research/04-provider-domain-scenarios.md` | research | P0.2–P0.4 | scenario-tested provider vocabulary and security/artifact distinctions |
| `research/05-p1-provider-config-domain-design.md` | research | P1–P2 | config precedence, core/package boundary, compatibility pre-mortem |
| `findings/P2-artifact-engine-recon-2026-07-19.md` | findings | P2 | current core/skiller/harness/maind hash/lock/drift seams и Rule of Three evidence |
| `research/06-p2-deterministic-artifact-engine-design.md` | research | P2–P6 | shared kernel boundary, registry/apply alternatives, invariants и pre-mortem |
| `research/07-p3-dual-skill-publication-design.md` | research | P3–P4 | publication ownership/modes, dual marketplace/install sequence и pre-mortem |
| `research/08-p4-task-command-routing-design.md` | research | P4–P7 | semantic command IDs, neutral routing tiers, invocation projections и plan gates |
| `research/09-p5-harness-provider-surfaces-design.md` | research | P5–P7 | security intent, profiles/hooks/MCP/agents projections и pre-mortem |
| `research/10-p6-maind-analytics-bootstrap-design.md` | research | P6–P7 | provider deploy loop, neutral analytics/migration и cold restart |
| `research/11-p7-self-host-release-design.md` | research | P7, roadmap | docs source, isolated→live self-host, guarded cleanup, release gate и GPT-5.6 routing |
| `findings/P7.1-capability-manifest-gap-2026-07-22.md` | finding | P7.1 | frozen manifest obligation против фактического отсутствующего carrier/production gate/docs operation |
| `research/22-p7-capability-manifest-remediation.md` | research | P7.1 | root manifest, shared validation/projection, production gates и deterministic docs render/check |
| `findings/P6-d104-live-admission-root-cause-2026-07-22.md` | findings | P6.9–P6.10 | read-only replay: D104 admitted, later unmanaged `.mcp.json` refusal, expected P5 non-selector and write-order defect |
| `research/24-d104-live-admission-repair-design.md` | research | P6.9–P6.10 | terminal P2/P5 invariants, P6-only atomic/result repair, split-verdict proof and new-authority boundary |
| `research/12-final-cross-phase-reconcile.md` | research | finish, design audit | contract chain, Required Reads, Routing, owner gates и итоговый DoR pass 3/3 |
| `research/13-instruction-contract-remediation.md` | research | P5.6–P7, design audit | common instruction contract/projections и restart propagation |
| `research/14-journal-schema-exception-remediation.md` | research | journal gate, design audits r3–r4 | F1 sidecar alternatives, exact schema и unchanged same-plan contract |
| `research/18-p3-provider-b-unmanaged-remediation.md` | research | re-opened P3.4, P3.5 | smallest contract-preserving pre-write ownership refusal and acceptance matrix |
| `research/16-p0-red-reproducibility-repair.md` | research | P0.6 | selected canonical exception + anchored evidence repair, commit topology и Owner Approval set |
| `root/adr/0001-provider-adapter-architecture.md` | decision | P0.3–P7 | alternatives, business rationale, dependency direction и component diagram |
| `root/contracts/provider-migration-gates.md` | decision D59 | P0.4–P7, FOREMAN/fleet boundaries | frozen exact G01–G11 producers/evidence/owners/failure actions, rollback/no-write и handoff bundle |

## Ключевые артефакты `root/`

| Артефакт | Суть | Статус |
|:--|:--|:--|
| `root/CONTEXT.md` | owner-approved provider glossary, stewardship и collisions | approved D53 |
| `root/contracts/provider-capability-contract.md` | capability manifest, support/evidence/compatibility | frozen v1.0.0, D55 |
| `root/contracts/provider-artifact-contract.md` | identity/provenance/hash/boundary/drift/repair | frozen v1.0.0, D55 |
| `root/adr/0001-provider-adapter-architecture.md` | canonical semantic source → deterministic provider adapters | accepted, D55 |
| `root/contracts/provider-migration-gates.md` | P1–P7/FOREMAN/fleet entry и release gates | frozen v1.0.0, D59 |
| `root/contracts/provider-config-contract.md` | project/fleet carriers, precedence, provenance и diagnostics | frozen v1.0.0, D70 |
| `root/contracts/provider-harness-contract.md` | profiles/security/provider-native settings/hooks/MCP/agents | draft; sealing P5.1 |
| `root/contracts/provider-analytics-contract.md` | neutral events/runs/readers/storage/privacy/migration | draft; sealing P6.3 |
