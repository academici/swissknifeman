# Authority Frame Contract v1

Status: frozen by the repository owner in `P5.2` on 2026-08-09 (`D143`).

The machine-readable contract is
[`authority-frame-v1.schema.json`](authority-frame-v1.schema.json). It is the only source of field
names, requiredness, closed enums, aggregation literals, and delegated predicates. This document
defines their meaning and authority boundary without maintaining a second schema.

## Default and monotonic authority

The frame is a deny-by-default authorization program over decision classes. An unclassified or
incompletely specified decision is `reserved`; absence is never delegation. Implementations must
reject catch-all classes such as “other”, “miscellaneous”, or “residual”.

Authority is monotonic. A derived frame may remove classes, limits, tools, files, or timeout
behaviors, but may not add rights beyond this contract and the pinned repository instance. A signed
or owner-authored narrower mandate does not turn a reserved decision into a delegated one unless the
frame itself is replaced through its owner gate.

## Decision-class form

Every declared class has a closed semantic definition, material fields, an aggregation rule,
delegated limits, an owner and escalation route, a structured verdict, borrowed action and attention
classes, and an explicit timeout behavior. Missing load-bearing fields resolve to `reserved` before
any side effect.

The material fields must be sufficient to reconstruct the decision's affected surfaces and test the
reserved predicates. The model may provide evidence, but it may not select the class, omit material
fields, change the aggregation key, or interpret an unknown state as safe.

## Owner words to predicates

The repository owner's rule is machine-addressable as follows:

| Owner boundary | Predicate | Result |
|:--|:--|:--|
| scope | `scope_change` | `reserved` |
| authority | `authority_change` | `reserved` |
| irreversible semantics | `irreversible_semantics` | `reserved` |
| constructive work inside all three boundaries | `constructive` with every required predicate true | `delegated` |

Changing this table, the predicates behind it, or the active instance is itself
`authority_change` and therefore requires the repository owner.

## Constructive delegation

`constructive` is the only delegated class. It is legal only when the declared item scope contains
all affected surfaces, no frozen contract changes, no closed set grows, the change is reversible,
and an immutable decision record is produced. These predicates are conjunctive: one false, missing,
or unknown value produces `reserved`.

Delegation authorizes only the already-declared technical choice. It does not authorize changing the
plan's goals, files, authority model, public surface, frozen semantics, or an append-only record.

## Aggregation against decision splitting

Evaluation groups automatically authorized decisions for the lifetime of one item by the pinned key
`(plan_id, item_id, decision_class)`. The evaluator unions their affected surfaces, including already
accepted commitments. If the union crosses any reserved predicate, the aggregate becomes
`reserved`, even if every individual request appeared constructive.

Changing the subject, reordering requests, or splitting one change into smaller proposals does not
reset the item-lifetime window. A new item creates a new window but not broader authority.

## Borrowed action and attention classes

Action classes `AUTO`, `AUTO-FIX`, and `OWNER` and attention classes `none`, `batched`, and
`immediate` are borrowed unchanged from the frozen `authority-policy` v1 donor. This contract does
not extend either set. Its own decision classes and predicates live in the `authority-frame`
namespace.

No class in this frame receives `immediate`; that attention remains reserved by the donor for
security, destructive, and irreversible operations. A reserved result uses `OWNER`/`batched` and
does not itself authorize a side effect.

## Timeout policy

Timeout behavior belongs to the decision class, not the request. A reserved class can only `park`.
`apply_default` is within the machine envelope solely for a reversible delegated class inside an
explicitly preauthorized envelope; its presence in the contract never grants that envelope. Policy
errors, unknown classes, unknown options, and invalid instances fail closed.

## Active instance and freeze

The active repository instance is
[`packages/task/configs/authority-frame.json`](../../../../../packages/task/configs/authority-frame.json).
Tools must load and validate that artifact, pin its digest in every decision record, and emit a clear
error when it is absent or invalid. They must not silently substitute either delegation or an
unrecorded owner decision.

The instance is handwritten and versioned because it expresses the repository owner's current
mandate. Freezing or changing it requires an explicit owner verdict recorded immutably in
`decisions/` and linked back to this contract. The active v1 instance was approved in `D143` with
SHA-256 `37df9c289931ee198c92039fd6a0337340b2dc4a2878c9ae6e86446b927b299f`.

## Rejected alternatives

- A prose-only delegation matrix was rejected because it is not deterministically evaluable.
- Catch-all and residual classes were rejected because unclassified authority belongs to the owner.
- Per-request thresholds were rejected because splitting one decision would bypass them.
- Model-selected classes, material fields, policy versions, or digests were rejected because a
  proposal must not widen its own authority.
- An external PDP runtime was rejected to keep the package stdlib-only; the policy discipline is
  implemented locally.
- Cryptographic approval signatures were rejected for v1 because the single owner's git authorship
  is the repository's approval carrier.

## Verification boundary

Validation parses the machine contract, proves the reserved default, monotonicity, exact predicates,
single delegated class, aggregation key and rule, and absence of catch-all classes. It separately
checks the active instance for complete timeout policy, unchanged donor enums, and no `immediate`
assignment. P5.3 owns the evaluator; P5.4 owns durable requests; P5.5 owns the return-loop adapter;
P6 owns command integration and fleet rollout.
