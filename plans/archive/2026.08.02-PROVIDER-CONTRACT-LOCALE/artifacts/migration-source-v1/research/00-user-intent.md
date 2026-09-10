# User-intent trace — 2026.08.02-PROVIDER-CONTRACT-LOCALE

This is the plan-wide layer-2 trace from every owner requirement in `brief/00-brief.md` to
the decisions, executable items and evidence carriers that must prove it. It adds no new
requirement and does not treat a planned deliverable as existing evidence.

| Owner thought | Decisions | Executable coverage | Proof carrier |
|:--|:--|:--|:--|
| SKM is the reliable hub; project config selects capabilities once | D1, D7, D15, D20 | P1.1–P1.3 freeze desired/status/ownership; P3.1–P3.3 implement the shared resolver and adapter boundary | Frozen `provider-control-plane-v1`; P3 conformance/status evidence; P7.1 acceptance bundle |
| Claude Code and Codex are configured independently from one semantic intent | D1, D5, D15, D20 | P1.2 ownership/capability matrix; P3.2 provider-scoped reconcile/readback; P7.1–P7.2 pair and isolation tests | Ownership matrix, per-provider readback/status rows, negative cross-write regressions |
| Do not copy Python runtime/plugins into consumers; canon stays in SKM | D7, D12, D15, D27 | P0 inventory classifies projections; P3 adapters reuse package owners; P5 migrates only an approved exact action set | Provider artifact locks, source identities, sealed P0/P5 manifests and protected-delta evidence |
| Remove legacy projections, overrides, broken links, trust and drift defects without losing owner work | D4, D6, D8–D11, D26–D29, D47 | P0.1–P0.4 seal/classify/gate containment; P5.1–P5.4 preserve, repair, crash-resume, quarantine and prove convergence; P6.1 handles Brain separately | Redacted fleet bundle, classification matrix, Owner D# action sets, durable per-project transaction journal, rollback/readback and convergence bundle |
| Neither provider overwrites the other's configuration/state; use provider strengths honestly | D5, D15, D20, D35 | P1.2 freezes ownership/support; P3.2 enforces target isolation; P6.2/P7.1 preserve shared vs provider-qualified native/unsupported rows | Frozen ownership/capability/health contracts, cross-write negative tests and exact provider-qualified acceptance rows |
| Canonical skills/plugins/comments/diagnostics/development docs become compact English | D3, D18, D22–D25 | P2.2–P2.3 freeze authoring/review policy; P4.2–P4.6 migrate admitted carriers and regenerate through owners | English-source/overlay/review contracts, cumulative corpus ledger, independent review and byte-stable generator evidence |
| Russian remains a render language; English default; plan/response/diagnostics choose independently and inherit | D2, D17–D19 | P2.1 defines three surfaces/precedence/fallback; P4.1 implements resolver/render context; P4.4 and P7.2 prove provider and surface isolation | Locale contract/vectors, EN/RU catalogs, requested/resolved/fallback trace and pair regressions |
| A Russian plan and provider-rendered text are actually Russian without changing other surfaces | D2, D17–D18 | P2.1–P2.3 specify plan rendering and independent review; P4.1/P4.4 integrate both providers; P7.2 varies one surface at a time | Russian plan/message fixtures, independent RU review and no-cross-surface assertions |
| Every known problem and every fleet project/path has evidence; skipped coverage is non-green | D8–D11, D32, D35, D49 | P0.1 exhaustive inventory; P0.2 exact-one classification; P6.3 exact-set two-run health; P7.1/P7.4 acceptance, dynamic D# crosswalk and adversarial audit | Self-verifying minimized bundles, empty project/provider/decision set differences and release-blocker set |

## Coverage verdict

Every brief sentence has at least one D-record, one owning item and one deterministic evidence
carrier. Owner choices are not silently filled: P0.3/P0.4, P1.3, P2.1–P2.3, P5.1/P5.4,
P6.1/P6.2 and P7.4 retain exact D# gates. No unresolved design question remains in prose.

## Verification

- **RAG:** existing same-day primary-source verification only: RFC 5646/Unicode TR35 in
  `findings/06-p2-locale-authoring-verification-2026-08-02.md` and HashiCorp desired/drift/
  state-upgrade documentation in `findings/05-p1-contract-verification-2026-08-02.md`.
- **Unverified → repeat pass:** future runtime APIs, contracts and fleet preimages must be
  rebound from their terminal commits at execution; planned paths are not current facts.
- **Workarounds/[POSSIBLE-DEFECT]:** none.
