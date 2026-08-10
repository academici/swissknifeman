# P3.8 package-promotion evidence

## G1 boundary

The P3 runtime now has one live owner: `packages/artifex/lib/artifex`. The
plan-local prototype remains immutable evidence and has no package runtime
import edge. Every Python runtime and test source has an explicit source and
successor hash row in `artifacts/P3/package-promotion-manifest-v1.json`.

## Stage-1 provenance

Stage 1 is the committed D95 transaction `40781d376a1ee489d61e8ff3ce93fbdb751b2f9f`.
Its exact closed file set contains the D95 Harness sources/tests/shared lock and
the two D86-generated Artifex guides. The package-promotion validator recomputes
that set from Git and verifies the guide and lock generation hashes.

## Validation boundary

`validate-package-promotion.py` has a current-tree mode for P3.8 close and a
historical mode which recomputes package file blobs from an explicit Git commit.
It rejects `HEAD` as historical input, so a current root cannot stand in for a
historical baseline. The P3.8 bookkeeping commit provides the first usable
historical anchor after the item commit is written.
