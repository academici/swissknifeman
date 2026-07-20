# Индекс плана — `2026.07.19-DUAL-PROVIDER`

**Обновлён:** 2026-07-20

## Карта директорий

| Путь | Назначение |
|:--|:--|
| `plan.md` | мета, scope, routing, status board и решения |
| `phases/P0.md … P7.md` | все 8 фаз детализированы до DoR; 39 items, skeleton markers отсутствуют |
| `handoff.md` | rolling next-step для холодного старта |
| `roadmap.md` | полная execution map 39/39 с GPT-5.6 Sol/Terra routing и owner gates |
| `journal.jsonl` | append-only журнал plan-команд |
| `journal-exceptions.jsonl` | optional append-only owner-gated provenance exceptions для historical schema-invalid journal rows |
| `brief/` | полный вход владельца |
| `findings/` | repo/provider evidence, P0 reproducible coupling baseline, package recon P2/P3/P5 и current OpenAI model routing |
| `research/` | traceability, architecture/sequence и phase design syntheses P0–P7 |
| `root/contracts/` | draft capability, artifact, migration-gate, config, harness и analytics contracts; skill/command contracts создаются своими owner-gated items |

## Провенанс

| Источник | Слой | Питает | Суть |
|:--|:--|:--|:--|
| `findings/repository-baseline-2026-07-19.md` | findings | P0–P7 | реальный масштаб и package seams |
| `findings/P0-provider-coupling-baseline.md` | findings | P0.1–P0.3 | anchored, reproducible current inventory and classified provider seams |
| `findings/provider-capabilities-2026-07-19.md` | findings | P0, P3–P5 | first-party provider facts |
| `findings/upstream-patterns-2026-07-19.md` | findings | P0–P3 | проверенные multi-provider patterns |
| `findings/P3-skiller-publication-recon-2026-07-19.md` | findings | P3–P4 | current skiller publication/install/marketplace seams |
| `findings/P5-harness-recon-2026-07-19.md` | findings | P5–P6 | current settings/hooks/MCP/agent-pack ownership seams |
| `findings/P7-openai-model-routing-2026-07-19.md` | findings | Routing, roadmap, P7 | official current GPT-5.6 Sol/Terra/Luna role guidance |
| `findings/journal-remediation-verification-2026-07-19.md` | findings | journal gate, design audit r3 | anchored 0/0 lint, tests, exact exception provenance |
| `findings/journal-same-plan-remediation-verification-2026-07-20.md` | findings | journal gate, design audit r4 | canonical directory-ID binding, wrong-plan red probe и negative-test matrix |
| `research/00-user-intent-traceability.md` | research | все фазы | мысль владельца → deliverable |
| `research/01-target-architecture-options.md` | research | P0–P2 | выбранная adapter architecture |
| `research/02-sequence-and-boundaries.md` | research | Status Board | порядок и границы с FOREMAN/fleet |
| `research/03-p0-design-and-premortem.md` | research | P0 | item dependency chain, owner gates, pre-mortem mitigations |
| `research/05-p1-provider-config-domain-design.md` | research | P1–P2 | config precedence, core/package boundary, compatibility pre-mortem |
| `findings/P2-artifact-engine-recon-2026-07-19.md` | findings | P2 | current core/skiller/harness/maind hash/lock/drift seams и Rule of Three evidence |
| `research/06-p2-deterministic-artifact-engine-design.md` | research | P2–P6 | shared kernel boundary, registry/apply alternatives, invariants и pre-mortem |
| `research/07-p3-dual-skill-publication-design.md` | research | P3–P4 | publication ownership/modes, dual marketplace/install sequence и pre-mortem |
| `research/08-p4-task-command-routing-design.md` | research | P4–P7 | semantic command IDs, neutral routing tiers, invocation projections и plan gates |
| `research/09-p5-harness-provider-surfaces-design.md` | research | P5–P7 | security intent, profiles/hooks/MCP/agents projections и pre-mortem |
| `research/10-p6-maind-analytics-bootstrap-design.md` | research | P6–P7 | provider deploy loop, neutral analytics/migration и cold restart |
| `research/11-p7-self-host-release-design.md` | research | P7, roadmap | docs source, isolated→live self-host, guarded cleanup, release gate и GPT-5.6 routing |
| `research/12-final-cross-phase-reconcile.md` | research | finish, design audit | contract chain, Required Reads, Routing, owner gates и итоговый DoR pass 3/3 |
| `research/13-instruction-contract-remediation.md` | research | P5.6–P7, design audit | common instruction contract/projections и restart propagation |
| `research/14-journal-schema-exception-remediation.md` | research | journal gate, design audits r3–r4 | F1 sidecar alternatives, exact schema и unchanged same-plan contract |

## Ключевые артефакты `root/`

| Артефакт | Суть | Статус |
|:--|:--|:--|
| `root/contracts/provider-capability-contract.md` | capability vocabulary/matrix | draft |
| `root/contracts/provider-artifact-contract.md` | render/provenance/lock/drift | draft |
| `root/contracts/provider-migration-gates.md` | P1–P7/FOREMAN/fleet entry и release gates | draft |
| `root/contracts/provider-config-contract.md` | project/fleet carriers, precedence, provenance и diagnostics | draft; sealing P1.1 |
| `root/contracts/provider-harness-contract.md` | profiles/security/provider-native settings/hooks/MCP/agents | draft; sealing P5.1 |
| `root/contracts/provider-analytics-contract.md` | neutral events/runs/readers/storage/privacy/migration | draft; sealing P6.3 |
