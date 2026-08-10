# Return Fingerprint v1

Status: frozen by `P4.1` on 2026-08-08.

The machine-readable shape and its single illustrative instance are defined by
[`return-fingerprint-v1.schema.json`](return-fingerprint-v1.schema.json). The schema is the sole
source of required members, types, enum subsets, and namespace-specific constraints. This document
defines their semantics and does not restate those constraints as a second schema.

## Purpose, reader, and grouping unit

The contract gives the P4 reducer a stable identity for repeated returns from execution to design.
Its reader is the deterministic reducer and durable counter introduced by P4.2. The grouping unit
is “the same repair seam for the same normalized plan subject”, never the same report wording.

A fingerprint record stores the canonical tuple and its SHA-256 digest together. The tuple is the
reviewable identity; the digest is only an index. A digest without its tuple is invalid because it
hides why two events were grouped and makes a later migration unverifiable (D136; R11.2).

## Return event and trigger

A return event is a `plan-design` journal record for normalized subject `S` when an earlier record
in the same journal has `command` in `plan-exec`, `plan-run`, `plan-close`, or `plan-audit` for `S`
or its containing phase. Only subjects matching `Pn` or `Pn.m` are fingerprinted. Other subjects
remain outside the counter and increment the mandatory `non_item_subjects` metric.

Records are ordered by `ts` ascending and then by physical journal line ascending. The trigger is
the last execution-side record for `S` or its phase before the return event in that total order.
This rule is mechanical: neither `note` nor another prose field may create a return or select its
trigger (D49).

## Canonical identity and digest

The core identity has five semantic components from D136:

- `fingerprint_version` prevents two construction rules from sharing an address space;
- `namespace` prevents provisional evidence from colliding with an explicitly declared seam;
- `subject` keeps ownership-local returns distinct (`P4.1` and `P4.2` are not one repair);
- `friction_class` preserves the trigger's machine cause as its sorted, deduplicated friction set
  plus result, so two triggers with different machine outcomes cannot collapse;
- `seam` identifies the stable repair boundary: `file` × `rule_or_contract_locus` ×
  `defect_class`, the vocabulary already used by `review_policy.finding_id`.

`ungroupable` additionally carries `event_ordinal`, the one-based physical journal line of the
return event. Without it, two returns that deliberately have neither seam nor machine evidence
would become indistinguishable and form the forbidden global “unknown” bucket. The ordinal is
allowed only in that namespace and never participates in a counted group.

Canonical bytes are UTF-8 JSON for exactly `fingerprint_version`, `namespace`, and `tuple`, with
object keys sorted lexicographically, separators `,` and `:` without surrounding whitespace, array
order preserved, and no trailing newline. `digest` is the lowercase SHA-256 of those bytes. Metrics
and the digest itself are excluded from the digest input. For `friction`, array order is the
lexicographic order of unique values; a producer that cannot prove this canonicalization fails
closed.

## Namespace rules

### `classified`

The trigger is schema-valid and exactly one distinct schema-valid seam is declared for the subject
inside the trigger→return window. Duplicate declarations of the same seam collapse to one;
different seams in the same window are ambiguous and cannot be guessed into `classified`.

Under D24 and D137, a seam is additive frontmatter on an item-scoped decision or finding. The declaration
contains `item`, `date`, `file`, `rule_or_contract_locus`, and `defect_class`; decision records keep
their existing status/replacement metadata. No journal field is added. For timestamp-precision
metadata the timestamp must fall after the trigger and no later than the return. For the frozen
date-only carriers, the UTC calendar date is compared inclusively to the trigger and return dates;
stable carrier identity breaks equal-date ordering. This makes the existing minimum satisfiable
without pretending that a date-only field has time precision.

### `provisional`

No usable seam is declared, the trigger is schema-valid, and it still carries a machine signal:
non-empty canonical friction or a negative result (`blocked`, `escalated`, `audit-red`). It counts
only inside the provisional namespace and can never equal a classified fingerprint. Attaching it
to a classified group by similarity, wording, or reducer inference is forbidden: false merging is
more expensive than false splitting (D51; R11.4).

### `ungroupable`

The trigger is schema-invalid, has neither a usable seam nor a machine signal, or has conflicting
distinct seam declarations. It receives its event-local ordinal and does not count toward a return
ceiling. A global literal digest for `unknown`, `other`, or `ungroupable` is forbidden. Raw invalid
values and validation errors remain representable for diagnostics; the historical journal is not
rewritten.

## Fields excluded from identity

The exclusion list is closed: `note`, `ts`, `session_id`, `run_id`, `attempt`, `actor`, model or
effort, `cost_usd`, `num_turns`, `duration_ms`, commit identifiers, report wording or severity, and
author/reviewer identity never enter a counted fingerprint. Each varies between otherwise identical
returns; including any one makes the counter remain at one and leaves the limiter silently dead
(D136; R11.3). `event_ordinal` is the sole namespace-local exception, only to make an ungroupable
event unique; it is never a grouping feature.

## Mandatory metrics and measured baseline

Every summary prints `provisional_share`, `ungroupable_share`, `schema_invalid_rows`, and
`non_item_subjects`; omitting any of them makes the summary invalid. Shares use all fingerprintable
return events as denominator, and an empty denominator is an explicit zero-result run rather than
an unknown coerced to zero.

The 2026-08-07 pre-reducer measurement supplies the honest baseline: 10 journals and 1109 records
contained 87 return events; 67 triggers had non-empty friction, 12 more had a negative result with
empty friction, and 8 had neither; 90 records had non-item subjects. Historical seam declarations
did not yet exist, and schema-invalid rows were observed but not separately counted by that probe.
Therefore P4.2 must print the four final metrics after schema validation; this contract does not
invent exact provisional or invalid-row shares from the coarser measurement.

## Schema-invalid history

Validation uses the sealed journal vocabulary. A malformed historical trigger is represented as
`ungroupable`, increments `schema_invalid_rows`, retains its validation errors, and is never skipped
or rewritten. Owner-gated journal exceptions remain the only mechanism that can qualify a stored
legacy row; the fingerprint reducer cannot create one.

## Rejected and deferred alternatives

- **Fingerprint from `note`.** Rejected: wording describes an observation, not a stable repair seam.
- **Digest without the canonical tuple.** Rejected: grouping becomes opaque and hard to migrate.
- **One shared `unknown` bucket.** Rejected: it merges events solely because classification failed.
- **A new journal field for the seam.** Rejected: the journal schema is sealed; D137 uses additive
  decision/finding metadata instead.
- **Cross-item clustering without `subject`.** Deferred, not rejected: no measured need exists in
  v1. Because the complete tuple is retained, a later projection can omit subject without changing
  this stored form.

This contract defines identity only. Counting, ceilings, owner-gate strength, judgement, lint
activation, and command integration belong to P4.2–P4.6 and P6.
