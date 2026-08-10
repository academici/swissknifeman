# Индекс плана — `2026.08.02-PROVIDER-CONTRACT-LOCALE`

**Обновлён:** 2026-08-10

## Карта директорий

| Путь | Назначение |
|:--|:--|
| `plan.md` | Мастер-план: Meta, Context, Rules, Routing, Status Board, D-log и Contracts. |
| `status.md` | Генерируемый status/update-log view. |
| `decisions/` | Append-only D-records и генерируемые current/archive/index views. |
| `phases/<Pn>/<Pn>.md` | Stable Phase Context и item index. |
| `phases/<Pn>/<Pn.m>.md` | Stable item specification. |
| `phases/<Pn>/<Pn.m>.state.md` | Генерируемое volatile state item'а. |
| `bundles/<Pn.m>.json` | Генерируемые digest-qualified executor inputs; создаются JIT после terminal predecessors. |
| `handoff.md` | Rolling-указатель следующего шага. |
| `journal.jsonl` | Append-only история plan-protocol запусков. |
| `roadmap.md` | 30-item карта исполнения, evidence-led skill modernization, per-cwd multi-package carrier, closed P4.4/P4.6 cwd→command matrix и P4 bounded-checkpoint/reviewer protocol; активируется только после нового GREEN design audit. |
| `brief/` | Слой 0: исходные требования владельца. |
| `findings/` | Слой 1: RAG и наблюдаемые repository/fleet facts. |
| `research/` | Слой 2: user-intent trace, target architecture, phase designs и finish reconcile. |

## Провенанс

| Источник | Слой | Питает | Суть |
|:--|:--|:--|:--|
| `brief/00-brief.md` | brief | P0–P7 | Надёжный hub, независимые provider adapters, compact English + localized render и пофайловое fleet evidence. |
| `research/00-user-intent.md` | research | P0–P7, design audit | Полная трассировка каждой мысли brief к D-записям, фазам, items и evidence carriers. |
| `findings/01-rag-locale-2026-08-02.md` | findings | P2, P4 | Внешние locale/fallback источники и исходный вердикт. |
| `findings/02-rag-control-plane-2026-08-02.md` | findings | P1, P3 | Внешние drift/state-upgrade источники для control-plane mapping. |
| `findings/03-current-defects-2026-08-02.md` | findings | P0, P5, P6 | Исходные unsealed наблюдения по Brain, trust, budgets и legacy consumer paths. |
| `findings/04-authoring-environment-drift-2026-08-02.md` | findings | P0.1 | Mid-session Codex default-model/sandbox drift; configured state is not runtime provenance. |
| `findings/05-p1-contract-verification-2026-08-02.md` | findings | P1.1, P1.3 | Official desired/observed and versioned-upgrade verification plus untrusted mAInd navigation to archived predecessor contracts. |
| `findings/06-p2-locale-authoring-verification-2026-08-02.md` | findings | P2.1–P2.3 | RFC 5646 syntax/private-use/canonicalization boundaries rechecked 2026-08-03; catalog fallback is separated as SKM policy; current RU→EN source-direction conflict. |
| `findings/07-p3-control-plane-recon-2026-08-02.md` | findings | P3.1–P3.3, P0.1 | Repository recon of current provider primitives and observed runtime/hook integrity facts; it is evidence, not repair authority. |
| `findings/08-p4-locale-migration-recon-2026-08-02.md` | findings | P4.1–P4.6, P0.1 | Current RU→EN source direction, corpus/generator surfaces and fresh preflight observations for locale migration. |
| `findings/09-p5-consumer-migration-recon-2026-08-02.md` | findings | P5.1–P5.4, P0.1 | Existing fleet-loop semantics, locator/privacy mismatch and the boundary between P3 adapters and P5 rollout sequencing. |
| `findings/10-p6-health-control-recon-2026-08-02.md` | findings | P6.1–P6.3, P7 | Current single-axis health surfaces, missing public Codex settings route, dependency-diagnostic gap and exact-set fleet boundary. |
| `findings/11-p7-release-acceptance-recon-2026-08-02.md` | findings | P7.1–P7.4 | Existing provider acceptance, regression, generated-doc and release surfaces plus gaps the final phase must close. |
| `findings/12-design-audit-remediation-2026-08-03.md` | findings | P0.1, P2.1, P3.2, P4.1, P5, P6, P7, design audit | Official pinned IANA/RFC/HashiCorp provenance, exact public hook CLI reproduction and repository-grounded F16–F18 carrier remediation. |
| `brief/01-owner-refinement-2026-08-10.md` | brief | P0–P7 | Current-model lightweight skills, official-doc/real-provider evidence order, additive Claude/Codex adapters and third-provider extensibility. |
| `findings/13-skills-audit-adjudication-2026-08-10.md` | findings | P0.1, P1.2, P2.3, P3.2–P3.3, P4.2–P4.3, P6.2, P7 | Perplexity-first external verification plus current repository measurements and a verdict for every audit claim. |
| `research/01-target-architecture.md` | research | P0–P7 | Синтез desired/status split, adapter ownership, locale surfaces и legacy classification. |
| `research/02-p2-locale-authoring-design.md` | research | P2–P7 | Locale surface/precedence, canonical English overlay and review-gate synthesis derived from P2 evidence. |
| `research/03-p3-control-plane-implementation-design.md` | research | P3–P7 | Core-to-package ownership map and sequential implementation design for desired snapshot, reconciliation and status diagnostics. |
| `research/04-p4-locale-migration-implementation-design.md` | research | P4–P7 | Shared locale ownership, cumulative admission ledger, bounded per-cwd checkpoints, independent review/resume, terminal regeneration and P4 pre-mortem. |
| `research/05-p5-consumer-migration-design.md` | research | P5–P7 | Exact-set action freeze, locator-only rebinding, preservation-first rollout, durable write-ahead transaction/resume carrier, recoverable cleanup and convergence evidence. |
| `research/06-p6-health-parity-design.md` | research | P6–P7 | Owner-gated Brain transaction, package-owned health composition, exact-set aggregate, two-run evidence and P6 pre-mortem. |
| `research/07-p7-release-operational-design.md` | research | P7.1–P7.4 | Exact-set acceptance, forward regressions, no-publish release candidate, dynamic D# crosswalk, cold audit and P7 pre-mortem. |
| `research/08-finish-reconcile.md` | research | design audit, P0–P7 | Сквозной producer/consumer, contract registry, coupling, routing/roadmap и DoR verdict design pass 3/3. |
| `research/09-lean-multi-provider-skills-design.md` | research | P0–P7, design audit | Minimum Skill Core, additive provider/third-provider seams, real replay/ablation loop, multi-label audit architecture and mapping onto the unchanged 30 items. |
| `findings/P0-provider-fleet-baseline.md` | findings | P0.2–P0.4, P5–P7 | Sealed P0.1 redacted registry/carrier/provider baseline; includes the relative Codex hook CLI defect and absolute-target observer control without repair authority. |
| `research/09-fleet-migration-classification.md` | research | P0.3, P0.4, P5 | Exhaustive no-write P0.2 classification of the sealed provider-path snapshot; only proven broken links are non-ambiguous and every other unresolved row is preserved as no-op. |
| `root/contracts/provider-recovery-gates-v1.md` | contract | P0.4–P7 | Frozen additive recovery gates, P0.4 no-op predicate, and immutable D63 contract-freeze binding. |
| `research/10-p0-premortem.md` | research | P0.4–P7 | P0 failure modes, early signals, and assigned recovery-gate mitigations. |
