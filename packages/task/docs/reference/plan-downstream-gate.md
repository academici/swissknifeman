# Downstream gate

`plan-downstream.py` smoke-checks the recorded `Validation` of items that mechanically consume a
producer's declared paths. It is available only for layout-v2 plans and has three outcomes:
`green`, `red`, and `unknown`. A red result always exits non-zero; there is no advisory mode.

```bash
python3 packages/task/scripts/plan-downstream.py \
  --plan-dir plans/<PLAN-ID> \
  --item Pn.m \
  --producer-commit <item-commit> \
  --record \
  --json
```

The tool discovers edges from `Files`/`Deliverables` to `Inputs`/`Required Reads`; it never accepts
a manual consumer list. It runs only Validation commands whose addressed repository paths exist at
the producer commit. Path extraction reads executable argv directly, including Unicode numbered
plan IDs with `№`; a future validator absent from the producer tree is dependency-not-ready and
produces recorded `unknown`, not a fabricated command failure. No applicable command also produces
`unknown`, not a pass.

Each consumer finding is keyed by the SHA-256 of its item specification and the producer commit.
Changing either value invalidates the old evidence. `--record` writes one append-only finding per
consumer under the plan's existing `findings/` carrier. If a producer is fixed after a red run, the
newest recorded producer commit in the current `HEAD` ancestry wins; the red finding remains as
history instead of blocking forever.

The `plan-lint` presence check is forward-only. Its activation date and immutable
journal-line boundary live beside the check in `configs/lint-check-dispositions.json`;
only producers whose events are after that boundary must carry a record. This keeps
historic layout-v2 producers outside the new obligation without a
plan-local opt-out switch.
