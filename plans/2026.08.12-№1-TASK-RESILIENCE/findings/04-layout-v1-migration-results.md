# P1.2 — Layout v1 migration rehearsal results

## 2026-08-12 — first deterministic target

- Target: `/home/vostrikov/Vaults/Brain/plans/2026.07.17-AXIOMA-ORCHESTRA`
- Source `plan.md` SHA-256 before dry-run: `52a8e4d1623857d9219e7d74038b252ab60f492188396417bef24d93dda2c734`.
- Dry-run output: `/tmp/task-p1-2-migration.ZDiSxX/2026.07.17-AXIOMA-ORCHESTRA`.
- Migrator result: `MIGRATED: 34 items; inventory 630 elements`.
- Required output lint failed: `4` Routing grammar errors and `6` warnings.

The v2 projection preserves Routing `Items` cells that use multiple non-contiguous
item/range expressions. The current linter rejects those cells, so this target cannot
meet P1.2's required per-target lint. The runbook requires stopping after a failed
rehearsal; no in-place migration was attempted. The source target remains unchanged;
the migrator's source-hash guard also passed before lint was invoked.

## Required follow-up

Redesign the migrator/linter compatibility contract before resuming P1.2. The repair
must preserve the existing Routing semantics or emit a v2-supported normalized form,
then repeat this target's dry-run and output lint before processing the remaining
inventory targets.
