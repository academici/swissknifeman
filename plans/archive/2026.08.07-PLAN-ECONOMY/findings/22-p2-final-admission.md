# P2 final admission — 2026-08-08

## Measured graph

`python3 packages/task/scripts/plan-weight.py plan plans/2026.08.07-PLAN-ECONOMY --json`
produced `artifacts/p2-admission-after.json` with 47 items: 17 `historical-pre-v2`,
21 `pending-producer`, and 9 `ready`. Every `pending-producer` edge names an earlier
non-terminal producer whose Deliverables contain the missing path. The two unresolved
entries and one missing pre-v2 carrier remain solely in historical items and are not
claimed as ready-path evidence.

`READY-FAILURES 0` and `INTRINSIC-FAILURES 0` were computed from that report. The
largest measured item is P2.1 at 101068 estimated tokens, but it is
`historical-pre-v2`; every ready item passes D2(a) and D2(b).

## D74 anti-displacement answer

The closed-graph sum of per-item mandatory-read weights fell from 2263520 in
`artifacts/p2-weight-before-after.json` to 1678553 in
`artifacts/p2-admission-after.json`: `ANTI-DISPLACEMENT: pass`.

**Could this result pass only because work was split, moved, cached, deferred, or
excluded? No for the measured self-host graph.** Replaced decision aggregates use exact
immutable D-records; every content slice has a source hash, per-slice hash, ordered
range and byte reassembly verifier; future files are deferred only via checked producer
edges, never treated as zero. The report counts every slice and per-file overhead.

## Verified ARTIFEX projection

The read-only command
`python3 packages/task/scripts/plan-migrate.py plans/2026.08.03-ARTIFEX-SUPERVISOR --dry-run --output plans/2026.08.07-PLAN-ECONOMY/artifacts/P6/artifex-resume-projection/2026.08.03-ARTIFEX-SUPERVISOR`
completed with `MIGRATED: 45 items; inventory 1124 elements`. The ARTIFEX source
`plan.md` hash was `f25dd39c280c17198d5bf124cd17bd5210f3f2c2a7e0a8b30cea5dfb48800c8a`
both from `HEAD` and after the dry run; the source was not modified.

The converter now preserves an absent legacy `## Обсуждение` carrier as explicit
inventory data, rather than rejecting a complete source or inventing a discussion
file. It also projects a last-journal blocked state to the v2 escalation triple;
these are local deterministic compatibility repairs with focused tests. The
projection's state, status, and decision views pass `--check`; `plan-lint` reports
0 errors. Its two warnings are inherited diagnostics: a stale historical P1 phase
handoff and the unavailable `HEAD` baseline for an untracked dry-run directory.
`git diff --check` additionally reports inherited trailing whitespace in one copied
ARTIFEX source script; it is retained because this evidence is a content-preserving
projection, not a source rewrite.
