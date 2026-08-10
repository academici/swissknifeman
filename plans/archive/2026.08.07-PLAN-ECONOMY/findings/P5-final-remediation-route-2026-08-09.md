---
item: P5.5
date: 2026-08-09
file: packages/task/lib/task/task_contract.py
rule_or_contract_locus: final owner-authorized Audit P5 remediation
defect_class: execution-environment-route
---

# P5 final remediation route and audit-cap boundary

`codex doctor --json` observed `gpt-5.6-sol`; the committed routing mapping classifies it as
`frontier`. The P5.5 specification requires `implementation/high`, so the actual
`frontier/high` execution is an over-tier process deviation, not an undershoot.

After Audit P5 attempt 3, rebuilding Task Contract for P5.4/P5.5 returns
`pre_mutation=block:LOOP_BUDGET_EXCEEDED` and `pre_final=n/a`. This is the protocol's audit-cap
guard, not a product-test failure: phase-mode closure does not use the item pre-final predicate.

The owner explicitly authorised this one final remediation in the current request. The remediation
is confined to the audited single-use bypass, records RED and green evidence, and does not schedule
a fourth audit or start P6. Its journal event carries `friction:["deviation"]`; no frozen contract,
owner hash, P4 input, or `packages/artifex` path changed.
