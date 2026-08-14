# P6.4 — Registered-project rollout

## Result

`skiller update --all --dry-run`, apply and post-rollout `skiller list` all exited `0`.
The ledger records 57 registry rows as 32 unique path/channel pairs across 23 paths: 29 applied,
3 explicit vendor no-ops and 0 failures. The no-op vendor records are `diabox`, `flexcrm` and
`sibintek/projects/sova`; their target update had no physical vendor/sync branch.

## Task projection probes

30 registered path/channel records have a physical
`.agents/plugins/bundles/task` carrier. Every one contains all five Task plan-command projections,
effective-route capture, and the prohibition on doctor/config/self-attestation substitution.
`agelto/agelto` and the source repository have no such physical carrier, so the probe is n/a.

## Validation

- `bash packages/skiller/scripts/validate.sh` — passed: 633 tests, registry check and Codex
  publication consumer acceptance green. Its 173 warnings are reported as inherited validation
  debt; no new failure was emitted.
- Command outputs and their SHA-256 digests are in `artifacts/P6/rollout-ledger-v1.json`.

## Process deviations

- The P6.4 start journal event used a non-derived `run_id` after a positional invocation of
  `derive_run_id` failed. The journal is append-only, so the line is preserved and terminalization
  uses the same run ID. This is a process deviation only; it did not affect rollout targets.
- The first semantic-probe predicate matched a single line instead of the generated two-line
  prohibition and produced a false red. The corrected probe checked the exact generated block;
  all applicable carriers are green.
