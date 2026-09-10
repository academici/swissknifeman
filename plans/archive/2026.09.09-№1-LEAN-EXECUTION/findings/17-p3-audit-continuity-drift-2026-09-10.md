# P3 audit finding — audit continuity drift

**Status:** open · **Owner:** P3.4 forward repair · **Candidate:**
`48dd1d316ae3d0435d0ad9103aa9c76a571cde0900d10652dc7fbe2939c2873e`

P7 requires fresh roots after design/audit only for measured context, capability, owner-pause or
independent-review boundaries (`findings/15-lean-lifecycle-overhead-2026-09-10.md:85-87`), and the
plan repeats that rule in `plan.md:48`. The current runtime selects `continue-root` unless a session
boundary is declared (`packages/task/lib/task/plan_lifecycle.py:47-72`), while the canonical
plan-protocol still makes every completed audit an unconditional hard boundary
(`packages/skiller/skills/general/plan-protocol/SKILL.md:312-317`) and the delivery regression test
requires that legacy result (`packages/task/tests/test_plan_delivery.py:158-180`).

**Failure scenario:** a low-risk audit with reusable route/context evidence still forces a new root,
so the practical continuation contradicts the lean lifecycle and preserves the overhead P7 was
created to remove.

**Acceptance for the owning continuation:** P3.4 must make `plan_continuity`/lifecycle evidence the
single owner of audit continuation, update canon/delivery/tests and generated projections together,
and retain a fresh root for genuine route, context, owner-pause or independent-review boundaries.
