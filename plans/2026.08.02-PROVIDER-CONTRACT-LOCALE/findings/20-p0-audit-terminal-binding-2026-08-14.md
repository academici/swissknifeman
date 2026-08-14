# Finding 20 — P0 audit terminal binding is self-invalidating

**Status:** open · reducer-confirmed terminal boundary · PROMOTE-CANDIDATE

## Finding

The P0 candidate fingerprint includes audit bookkeeping that the terminal audit must mutate.
`phase_candidate_fingerprint()` hashes every tracked path declared by an item; P0.8 declares
`journal.jsonl` and generated status/index views, while P0.10 declares generated views and
`handoff.md`. The current snapshot therefore contains `journal.jsonl`, `handoff.md` and
`status.md` in `product_files`.

An isolated worktree reproduced both failure branches:

1. Candidate `8da4ec1e593966417642b5ba14d5c6f37072a5ac34c08a673285eefa5a4ad92f`
   followed by the canonical audit subject `P0 — режим фазы` produced candidate
   `328cb865652e3423e65b0cd1addb9dbcd3330785a08d9f83c1043c292e8d2390`; the close gate returned
   `PHASE_AUDIT_MISSING` because it compares `event.item_id` directly with `P0`.
2. Appending the same audit under exact subject `P0` produced candidate
   `682df884d66333cccfd8cd481786a41ff2d2288b39fca93181e5aebc6c679a76`; the close gate found the
   row but returned `PHASE_AUDIT_STALE` because the append changed `journal.jsonl` bytes.

`reviewer:gpt-5.6-sol` returned `JUSTIFIED` from an `isolated-child-return`. The deterministic
`task.plan_blocking.evaluate()` result is `terminal-block / BLOCK_CONFIRMED`: repairing this
requires shared `packages/task` runtime semantics or changing closed item contracts, neither of
which is inside the P0 audit repair scope.

## Failure scenario

A correct GREEN audit can never authorize `plan-close`: the canonical subject is invisible to
the close gate, and the compatible subject immediately stales its own fingerprint. Repeating the
audit only adds another changing journal row.

## Required repair boundary

- Normalize phase audit subjects in `phase_close_gate()` through the same
  `phase_audit_subject()` policy used by lint and delivery.
- Make audit bookkeeping truly absent from the material candidate fingerprint, including when a
  closed item declared generated owner views or the append-only journal as files.
- Add regression coverage proving one terminal GREEN append remains fresh for the immediately
  following close gate.

After the shared runtime repair, build an impact classification against the already completed full
baseline. The expected mode for this bookkeeping/runtime-only change is `gate-rebind`; use `delta`
only if a bounded material change is actually found. A repeated full P0 audit is not authorized
without a new wide-material justification or an explicit owner decision. Do not reopen or
reimplement P0.9/P0.10.
