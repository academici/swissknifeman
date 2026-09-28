# repeat-admission/v1

## Independent terminal-item repeat

A separate owner-requested repeat uses `repeat-admission/v1`, drafted by
`task.plan_repeat.build()` and bound to an accepted decision marker
`[REPEAT-ADMISSION:<sha256-of-canonical-contract>]`. The closed contract binds
plan/item/command, current GREEN design fingerprint and spec digest, exact prior
terminal head, historically terminal phase/sibling heads and specs, owner-message
path/digest, new attempt/session/run identity. It applies only to one solo slot.
Pass its JSON carrier to `plan-work.py prepare --repeat-admission <path>`.
Current route, authority, recovery order, bundle and evidence checks still apply.
The durable start consumes the grant and stores it beside the route receipt.
Resume revalidates it; another run requires another owner grant. New outcomes
append to history. Terminal delivery authenticates the original consumed grant
and unchanged sibling contracts; the repeat does not reclose the historical phase.
No historical outcome is upgraded to contemporary acceptance by this contract.

Phase aggregates retain the authenticated historical phase outcome. Item state
and item tables expose the current repeat run independently; revoking the owner
grant invalidates this projection. No status-board design rewrite is required.

A completed repeat is historical evidence when later authored scope changes the
whole-plan fingerprint. Projection and delivery authenticate its consumed start,
original pre-start finish/GREEN, owner provenance and unchanged item/phase/siblings;
they do not require the later design to be ready. New admission and unfinished
resume still require the current GREEN and exact bound fingerprint. A historical
read never admits execution or reuses a consumed grant.
