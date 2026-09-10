# P5.2 local override disposition

**Observed:** 2026-08-15

## Frozen action set

D83 binds P5.2 to `action-set-7fc7d9fa6332f7d4613a8408` in manifest
`sha256:8c134c75214cff8dc4193f3b251e1afaf5c3041135a942976571068ad527bae4`.
The approved action set contains no `preserve` or `register-override` rows and authorizes zero
consumer/provider writes. All 13,421 manifest rows remain `no-op-unresolved`; no override bytes
were copied, changed, adopted, registered, translated, or relocated.

## Execution evidence

The exact P5.2 `apply` and `resume` carrier invocations both returned 0. The derived result is
`p5-fleet-results/v1`, has zero project outcomes and zero durable transaction events, and lists
all 13,421 unresolved action IDs. `resume` had no terminal transaction to replay and reproduced
the same result bytes. `verify-results` returned 0; the result file SHA-256 is
`2e56b540f34042314f2e388c225b53f96331a0cc509366df9b3d9af8b02ddaa6`.

No private backup was created because no config or provider target mutation was admitted. The
shared hash-chained fleet transaction log remains empty. Required unresolved rows therefore stay
explicit and cannot contribute a green fleet-health claim.

## Validation and environment evidence

- The complete stdlib runner carrier passed all 11 tests.
- Plan lint `--gate new` returned 0 with no newly introduced errors; full lint retained five
  inherited P4 write-site errors and was not reported green.
- `codex doctor --json` and worktree-local `maind health --cwd` were green.
- Preflight found stale global Claude `run-report` hook files. The worktree-local
  `packages/harness/bin/harness hooks --global` regenerated the effective registration, and the
  repeated `harness doctor` returned `harness: OK`.
- The first five-carrier read and one later validation summary were truncated by tool-output
  transport. Execution recovered only the missing item text and inspected the already-produced
  result instead of rerunning validation; neither defect changed product bytes or route evidence.
- Foreign changes in `packages/task`, unrelated generated bundles, and `roadmap/` were preserved
  and excluded from P5.2 commits.
