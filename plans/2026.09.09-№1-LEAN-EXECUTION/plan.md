# 2026.09.09-№1-LEAN-EXECUTION — План №1 — Lean execution backlog

## 0. Meta

| Поле | Значение |
|:--|:--|
| Plan ID | 2026.09.09-№1-LEAN-EXECUTION |
| Title | План №1 — Lean execution backlog |
| Layout | v2 |
| Document Type | Executable Master Plan |
| Authoring Model | gpt-5.6-sol/high |
| Repository | swissknifeman |
| Related Packages | task · skiller · harness · analyst |
| Execution Mode | phase-first, adjacent-batch, evidence-reuse |
| Target Operator Classes | implementation (exec) · frontier (material audit/design) |
| Approval Owner | repository owner |
| Home | repo:swissknifeman |
| Design Passes | 3/3 + bounded remediation — pass 1 promoted and structured the roadmap backlog; pass 2 detailed P1–P6 in six cold phase sessions; pass 3 reconciled the original 18 item contracts; F1–F4 added exact owner P5.3; the owner-directed correction adds P7.1 and a direct grouped execution handoff without inventing another design pass or audit |
| visibility | private |
| Paused By | — |

<!-- migration-version: 1.0.2 -->

## 1. Context

Root roadmap mixed deferred triggers, already completed work, rejected ideas, incident duplicates
and twenty-three actionable specifications. This plan is the single executable home for the
triggered/owner-prioritized remainder. Original specs remain immutable design evidence under
`artifacts/source-roadmap/`; item carriers below own implementation. The sequence first reduces
Task read/dispatch/session waste, then fixes continue-first lifecycle, proportional phase assurance,
terminal delivery, two narrow cross-package gaps, measured Codex-only instruction/skill cost, and
the whole-plan design-completion circuit breaker exposed by this plan's own ATTENTION remediation.
RAG:— for repository scope; RAG:✅ only for provider behavior summarized in
`findings/01-codex-instruction-baseline.md` and re-verified during finish in
`findings/08-finish-external-verification.md`.

## 2. Execution Rules

- Execute only the current phase and its declared adjacent batch; never cross an audit/close boundary.
- Read each item through the v2 five-carrier path and fail closed on incomplete/truncated bundle input.
- Repair local reversible defects in the owning item; redesign only for a new decision surface or unbounded/public/authority boundary.
- Generated state, bundle, decisions, provider projections, AGENTS and skill projections change only through their owning generators.
- One full audit establishes a material phase baseline; later unchanged evidence uses delta or gate-rebind per D2.
- A completed whole-plan design audit is not repeated merely because its bounded findings were repaired; D13 admits the current grouped execution, while P7.1 makes that continuation deterministic for future plans.
- P4 must distinguish repository-owned transcript proof from an external provider transport claim per D5.
- P6.1 is read-only measurement. No instruction/skill deletion occurs before its cold-start source inventory is complete.
- P6 changes only canonical catalogs/fragments/skills and then regenerates; separate Codex semantic profiles are forbidden by D4.
- Every item closes with focused validation, affected package validation, product commit and bookkeeping commit; preserve unrelated worktree changes.
- No tag, push, release, external deployment or consumer-project rollout without separate owner authority.

## 3. Routing

| Batch | Items | Model class/effort | Exec | Review | Почему |
|:--|:--|:--|:--|:--|:--|
| B-P1-ECONOMY | P1.1 | implementation/high | manual | full | shared Task reader/CLI fixtures and read-budget context; high route exceeds plan-exec pin |
| B-P1-ECONOMY | P1.2 | implementation/high | manual | full | batch admission consumes the same parsed routing model; high route exceeds plan-exec pin |
| B-P1-ECONOMY | P1.3 | implementation/high | manual | full | continuity consumes batch/work estimates and command renderer; high route exceeds plan-exec pin |
| B-P2-CONTINUE | P2.1 | implementation/high | manual | full | common reducer, repair evidence and field fixture; high route exceeds plan-exec pin |
| B-P2-CONTINUE | P2.2 | implementation/high | manual | full | producer readiness and priority-fix reuse classifier state; high route exceeds plan-exec pin |
| B-P2-CONTINUE | P2.3 | implementation/high | manual | light | narrow archive command/canon/docs change after lifecycle settles; high route exceeds plan-exec pin |
| B-P3-ASSURANCE | P3.1 | implementation/high | manual | full | assurance and impact broker share candidate identity; batch uses its maximum high route |
| B-P3-ASSURANCE | P3.2 | implementation/medium | manual | light | focused routing parser stays in the high-route assurance batch to reuse fixtures |
| B-P3-ASSURANCE | P3.3 | implementation/high | manual | full | validation reuse consumes impact classes and candidate identity; batch uses high route |
| B-P3-ASSURANCE | P3.4 | implementation/high | manual | full | evidence graph consumes receipts and closure model; batch uses high route |
| B-P4-TERMINAL | P4.1 | implementation/high | manual | full | terminal verifier, lease and transcript schema are one chain; high route exceeds plan-exec pin |
| B-P4-TERMINAL | P4.2 | implementation/high | manual | full | provider adapters and 40-boundary proof consume P4.1 contract; high route exceeds plan-exec pin |
| B-P5-GAPS | P5.1 | implementation/medium | manual | light | narrow skill work stays with the high-route cross-package consumer to reuse generation context |
| B-P5-GAPS | P5.2 | implementation/high | manual | full | analyst fleet scan and Task template synthesis cross one package boundary; batch uses high route |
| B-P5-GAPS | P5.3 | implementation/high | manual | full | Laravel isolation skill and snippets reuse the same Skiller registry/docs qualification context; safety invariant requires full review |
| solo | P6.1 | frontier/high | manual | full | cold external Codex launches and epistemic gate precede mutation |
| B-P6-CODEX | P6.2 | implementation/high | manual | full | deterministic eval harness consumes frozen P6.1 inventory; high route exceeds plan-exec pin |
| B-P6-CODEX | P6.3 | frontier/high | manual | full | measured retain/remove/provider-filter decision can alter always-on policy |
| B-P6-CODEX | P6.4 | implementation/high | manual | full | aggregate generator/package/docs qualification and release-ready handoff; high route exceeds plan-exec pin |
| solo | P7.1 | implementation/high | manual | none | one bounded Task policy slice extends the P3 assurance seam to whole-plan design completion after all predecessor contracts exist |

## 5. Decision Log

Catalog: `decisions/`; generated views are owned by `plan-views.py decisions`.

## 7. Contracts

### Exported

| Контракт | Версия | Статус | Потребители | Уведомлены |
|:--|:--|:--|:--|:--|
| task execution-economy contracts | v1 candidate | P1–P3 implementation | Task commands/runtime | plan-local |
| terminal transcript admission | v1 candidate | P4 implementation | Task/Harness/provider adapters | plan-local |
| Codex instruction evaluation | v1 candidate | P6 implementation | Harness/Skiller generators | plan-local |
| description-trigger-priority | v1 candidate | P5.1 implementation | Skiller bucket-audit and skill authors | plan-local |
| workflow-fleet-report | v1 candidate | P5.2 implementation | Analyst and Task workflow constructor | plan-local |
| laravel-parallel-isolation | v1 candidate | P5.3 implementation | Skiller Laravel testing skill and snippets | plan-local |
| design-completion continuation | v1 candidate | P7.1 implementation | Task design/audit delivery and lint | plan-local |
