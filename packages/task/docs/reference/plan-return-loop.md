# Return fingerprint v1

`plan-views.py returns --plan-dir <plan> --json` deterministically projects return events from the
append-only journal. A return is a `plan-design` event after an execution-side event for the same
item or phase. Its digest indexes a canonical tuple; the tuple remains in output for review.

The reducer reads the lifted `return-fingerprint-v1.schema.json`, preserves invalid journal rows as
`ungroupable`, and never turns an absent journal into a zero count: `durable_count()` returns
`"unknown"`. Seam metadata is additive frontmatter on item-scoped decisions/findings.
