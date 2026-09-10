# P0 audit-reopen design

## Sources

- `brief/03-p0-audit-reopen-2026-08-10.md` — owner invocation and bounded scope.
- `phases/P0/P0.md` → `## Audit P0 — 2026-08-10` — seven RED findings and anti-scope.
- `findings/17-layout-v2-phase-reopen-status-gap-2026-08-10.md` — truthful v2 status boundary.
- Existing P0.1–P0.4 specs, states, bundles and committed artifacts — implementation facts.

No external fact class is load-bearing for this pass; all decisions are repo-grounded. Current
provider observations are execution inputs to P0.5/P0.7 and must be freshly produced there, not
recalled from this design session.

## Finding ownership

| Audit finding | Forward owner | Acceptance boundary |
|:--|:--|:--|
| F1–F2: P0.1 exact-set/privacy negatives and missing D55–D61 measurements | P0.5 | independently mutated copies fail; committed baseline retains typed counts, observations and provider-qualified measurements |
| F3: checker accepts weakened G01–G11/gate rows | P0.6 | semantic row/schema/topology validation plus real mutations of copied inputs |
| F5: R01–R07 depend on future P7.4 | P0.6 | every transition has an available phase-local independent verifier; P7.4 remains release audit only |
| F4: P0.4 trusts hand-authored booleans | P0.7 | executable redacted producer, command/detector provenance and protected pre/post digests are recomputed |
| F6–F7: missing write-site/commit/route anchors and hidden close deviations | P0.8 | append-only forward provenance ledger and corrective close events regenerate truthful state views; historical bytes remain intact |

## Sequential design

P0.5 must run first because every later checker and security verdict depends on a sealed exact
baseline. P0.6 consumes that baseline and produces the patched recovery contract/checker topology.
P0.7 consumes both and creates fresh executable no-op or owner-gated mutation evidence. P0.8 is the
terminal reconciliation item: it consumes committed P0.5–P0.7 outputs, reconstructs the original
P0.1–P0.4 execution map from Git/journal, appends bounded correction events, and runs the final P0
fan-in before close and audit pass 2. The four items are data-coupled; N≥3 independent scopes does
not fire, so no workflow is legal. RAG:— (repo-grounded: audit dependency chain and existing P0
producer/consumer edges).

## Contract and authority boundary

The recovery contract should advance from v1.0.0 to the smallest compatible corrective version
only after P0.6 materializes the exact diff and obtains a new typed `contract_freeze_decision`.
D63 never authorizes the successor bytes and never authorizes containment. The recommended
version is v1.0.1 because the intended G01–G11/no-write semantics stay unchanged while their
machine verification and verifier topology are corrected; an observed semantic expansion stops
for a new design D#. RAG:— (repo-grounded: D63, audit F3/F5 and the existing contract text).

## Historical provenance boundary

P0.8 does not amend old commits, item specs or journal rows. It records the observed item anchors
(`0169e256`, `5703feb4`, `18571a14`, `d17e4497`), original executor route, recomputed Task Contract
codes, bundling/spec-timing deviations and reproducible validation references in one deterministic
ledger. Only after that ledger validates may it append current reconciliation events whose note
starts with the canonical `write-site: pre_mutation: allow · pre_final: allow` carrier. The event
actor is the current reconciler; the historical executor route remains an explicit ledger field,
never a fabricated current route attestation. RAG:— (repo-grounded: audit F6/F7, append-only
`journal.jsonl`, and `packages/task/lib/task/plan_item_state.py`).

## DoR verdict

All seven RED findings have one owner and deterministic acceptance. Scope and anti-scope are
explicit, no clarification markers remain, frozen-contract authority is isolated, and the phase
remains sequential. The only named protocol deviation is the Layout v2 phase-status projection
gap; generated views stay truthful and unedited.
