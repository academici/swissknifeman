# P4 authoritative history and durability results

## Result

P4.1 repairs confirmed N-07, N-12, N-15, N-16 and N-17 without rewriting sealed
journal bytes:

- journal and exception mutations share one per-plan exclusive lock; every mutation
  rereads authoritative bytes, rejects malformed nonempty history as `JOURNAL_CORRUPT`,
  opens append targets with `O_NOFOLLOW`, completes the append, then syncs the file and
  containing directory;
- terminal identity is idempotent for an exact result/fingerprint and conflicts for a
  different terminal; paired lifecycle events reject terminal timestamps before start;
- historical exceptions resolve through parsed decisions and require one accepted,
  current, item-bound D# carrying an exact `JOURNAL-EXCEPTION` digest/field/plan/item grant;
- new journal values require strict UTC `Z` timestamps, finite nonnegative cost/duration
  and integer nonnegative turns; decision dates use calendar-valid ISO parsing;
- projection publish/check is serialized on the containing directory, rejects symlink or
  special targets, uses a same-directory no-follow temporary file, and acknowledges write
  success only after file sync, atomic replace and directory sync.

## Evidence map

| Finding | Repaired behavior | Evidence |
|:--|:--|:--|
| N-07 | Filename presence no longer grants a journal exception; proposed and unbound decisions fail closed. | `TestHistoricalSchemaException`, `TestV2DecisionCarrier` |
| N-12 | Corrupt history blocks mutation; synchronized duplicate terminal writers produce one row and one existing pointer; divergent terminal fingerprints conflict. | `TestAppend.test_malformed_history_blocks_append_without_changing_bytes`, `test_synchronized_duplicate_terminal_race_appends_once`, `test_duplicate_terminal_returns_pointer_without_appending` |
| N-15 | Invalid/non-UTC time, negative/non-finite metrics and non-integral turns reject; paired chronology is ordered. | `TestNewEntryAndValidate.test_timestamp_and_metrics_are_strict`, `TestAppend.test_terminal_timestamp_before_paired_start_is_rejected` |
| N-16 | Impossible calendar dates reject while a leap day remains valid. | `PlanDecisionsTest.test_date_is_calendar_valid_without_imposing_monotonic_order` |
| N-17 | Matching-byte symlinks reject in check/write, publish sync order is file → replace → directory, and concurrent writers leave complete bytes. | `PlanProjectionTest.test_write_and_check_reject_symlink_without_touching_target`, `test_publish_syncs_file_before_replace_and_directory_after`, `test_concurrent_publishers_serialize_complete_bytes` |

## Validation

- Focused journal/decision/projection suite: 57 tests GREEN before the final conflict and
  chronology additions; both added regressions passed independently.
- End-to-end terminal journal → reconcile → successor-materialization smoke:
  `test_plan_reconcile.py`, 1 test GREEN.
- `bash packages/task/scripts/validate.sh`: 1150 tests GREEN, 1 skipped; plan-lint and
  generated provider-command checks GREEN.
- P4.1 bundle regeneration and plan-lint conflicts check: GREEN.

## Compatibility and filesystem limits

- Valid historical records remain readable. A schema-invalid journal remains read-only
  for ordinary mutation until the existing migration protocol repairs it; old filename-only
  exception decisions no longer authorize new sidecars.
- Direct legacy terminal fixtures without a paired start remain readable/writable for
  compatibility. Once a lifecycle start with the same item/attempt/run ID exists, terminal
  ordering is strict.
- Durability is the local POSIX contract verified on Linux: advisory `flock`, `O_NOFOLLOW`,
  regular-file checks, `fsync(file)`, atomic same-directory replace and `fsync(directory)`.
  Distributed/network filesystem semantics are outside P4.1. The final projection parent
  component is opened no-follow; repository layout remains responsible for trusted ancestors.
