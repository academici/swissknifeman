# Source Evidence Verification v1 (P0.1)

RAG:— (plan-grounded: D3/D25/D30; repo-grounded: `findings/08-design-audit-red-attempt-2.md` F1).

## Scope

This contract governs how `2026.07.24-AGENT-RELIABILITY` proves the committed,
immutable `artifacts/source-evidence/` bundle (D25, unchanged by this item —
bundle bytes and `verify_source_bundle.py` are frozen) is semantically closed,
not only byte/hash/schema green. It supersedes no prior D-record; it is the
first Files-owning artifact D30 promised.

`verify_source_bundle.py`'s own `verify`/`map-state`/`verify-results`/
`verify-claim-inventory` commands remain the sole owners of byte-hash, JSON
schema, exact case-ID-set, and the three pinned constants
(`952`/`591`/`550`/`135110000` stored-value comparisons) they already
implement (`verify_source_bundle.py:26-121`). This contract never
re-implements or bypasses them; every item that consumes the bundle keeps
running all four immutable commands first.

## What the immutable verifier does not check (F1 gap this contract closes)

- Per-record journal key closure (no forbidden raw-body/reasoning/tool-payload
  key ever appears; no required key is missing).
- A fresh, independent recompute of the journal `result` and `friction`
  histograms straight from the seven committed JSONL snapshots.
- Cross-manifest linkage between `manifests/journal-snapshots.json` and
  `manifests/bundle-manifest.json` for the same seven files.
- Corpus/session/manifest case-ID cross-linkage as three independently loaded
  documents, not only the immutable verifier's own internal comparison.
- Corpus case field shape (`confidence` enum, `kind` distribution, referenced
  `source_committed_paths` existing on disk) and session record field shape
  (`sha256` regex, ISO-8601 `timestamp`, `confidence` enum).
- An explicit, closed-vocabulary proof-class ledger for every load-bearing
  claim, so a fact that cannot be recomputed from the committed
  (privacy-minimized) bundle is never silently reported as verified.

## Proof classes (closed enum)

- `recomputed` — independently derived from committed bundle bytes by this
  item's own algorithm, with no reliance on a stored value.
- `cross-checked` — two or more committed documents (or the immutable
  verifier's own commands) are compared against each other; neither side is
  treated as ground truth by itself.
- `pinned-not-recomputable` — a committed constant is recorded and used as
  labelled context, but this item does not claim to have derived it from
  committed bundle bytes (its derivation input, e.g. raw session rollouts, is
  explicitly out of Scope Excluded).
- `unknown` — reserved for a future assertion whose derivation basis has not
  yet been established; not used by the current assertion set because every
  currently attempted assertion resolved to one of the three classes above.

A claim never moves from `pinned-not-recomputable`/`unknown` to
`recomputed`/`cross-checked` without a change to this contract's assertion
list and a corresponding algorithm in the verifier — never by prose alone.

## Non-recomputable facts named explicitly

- `classified_lifecycle_events` (550) and the `outcomes` breakdown
  (`closed_green`/`closed_deviations`/`audit_red`/`audit_green`/`blocked`/
  `escalated`/`retry`/`deviation`) in `precomputed/baseline.json:journals`: no
  classifier that maps 591 physical journal records to these categories is
  committed to the bundle. Recomputing the raw `result`/`friction` histograms
  (assertions `journal-result-histogram`/`journal-friction-histogram`) is the
  closest independently derivable fact, and it does not equal this
  classification.
- `dedup_correction` totals (`135,110,000` corrected input tokens and
  siblings) in `precomputed/baseline.json`: derived from excluded raw rollout
  files, out of Scope Excluded for this and every downstream item.

## Machine contract and executable owner

- `plans/2026.07.24-AGENT-RELIABILITY/artifacts/P0.1/semantic-verification-contract.json`
  is the machine-readable assertion list (id, proof class, input, algorithm).
- `plans/2026.07.24-AGENT-RELIABILITY/artifacts/P0.1/semantic_bundle_verifier.py`
  is the sole executable owner of every assertion in that contract; it never
  writes below `artifacts/source-evidence/`.
- `plans/2026.07.24-AGENT-RELIABILITY/artifacts/P0.1/verification-report.json`
  is the deterministic, regenerable report the verifier produces against the
  exact committed bundle.

## Consumers

P0.2 and P0.3 read `verification-report.json` and this contract as Inputs.
Neither may cite a `pinned-not-recomputable`/`unknown` fact as satisfying a
deterministic acceptance predicate (D30).
