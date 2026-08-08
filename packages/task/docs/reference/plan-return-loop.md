# Return fingerprint v1

`plan-views.py returns --plan-dir <plan> --json` deterministically projects return events from the
append-only journal. A return is a `plan-design` event after an execution-side event for the same
item or phase. Its digest indexes a canonical tuple; the tuple remains in output for review.

The reducer reads the lifted `return-fingerprint-v1.schema.json`, preserves invalid journal rows as
`ungroupable`, and never turns an absent journal into a zero count: `durable_count()` returns
`"unknown"`. Seam metadata is additive frontmatter on item-scoped decisions/findings.

## Return-loop v1

`plan-views.py returns --plan-dir <plan> --gate --json` applies the lifted
`return-loop-v1.spec.json` ladder without embedding its cap in Python. The first
durable occurrence remains a local fix, the second requires isolated review, and
an occurrence above the configured cap hard-stops with an owner packet. The packet
contains the frozen fingerprint tuple/digest, occurrence count, cap, and durable
journal history; the words `blocked` and `escalated` alone are not risk triggers.

`plan-lint` stays silent unless the plan Meta table explicitly says
`Return Loop Gate | v1`. Once later phases enable that opt-in, D139 uses additive
frontmatter on an existing item-scoped `findings/*.md` carrier: `gate:
return-loop-v1`, `qualification: new|repeat|unqualifiable`, and (for grouped
returns) `fingerprint_digest` plus `occurrences`. An over-cap return additionally
needs `owner_authorization: D#` naming an existing decision. The evidence carrier
is validated but P4.4 does not turn the new check on for ordinary plans.

## Return-judgement v1

An item-scoped finding may add `return_judgement:` with one compact JSON object conforming to
`configs/return-judgement-v1.schema.json`. The reducer scans findings in canonical path order,
uses the first schema-valid record matching both subject and fingerprint digest, and ignores a
record missing required provenance. A matching self-judgement is rejected and does not permit a
later record to become a tie-break or retry.

The reducer never calls a model. `JUSTIFIED` and `INSUFFICIENT_EVIDENCE` only preserve evidence;
`AVOIDABLE`, `OUT_OF_SCOPE`, and `MALFORMED` can require an earlier stop. The durable counter,
fingerprint namespace, and existing owner gate are monotone and cannot be weakened by any verdict.
