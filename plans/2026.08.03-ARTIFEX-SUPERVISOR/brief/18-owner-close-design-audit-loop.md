# Owner directive — close the design-audit loop

Date: 2026-08-05
Plan: `2026.08.03-ARTIFEX-SUPERVISOR`

The repository owner explicitly rejects an eleventh pre-execution design audit and any further
unbounded audit-of-audit cycle. The current plan must become executable now: persist the exact
new-session settings, make `2026.08.03-ARTIFEX-SUPERVISOR P3.5` the live Next, and commit the
plan carriers required by P3.5's committed-spec gate.

Every future audit checkpoint is hard-capped at two total passes and two occurrences of the same
finding. After that ceiling, do not schedule another audit automatically; perform bounded
forward remediation and deterministic validation. Interrupt the owner only for a genuine
safety, authority, frozen-contract or acceptance decision that cannot be resolved from the
recorded plan.

This directive is not permission to weaken item validation, security, protected owner grants,
frozen history, P6.4 finished-product acceptance or release authority. It grants no tag, push,
publish or release action and authorizes no implementation in this design-remediation session.
