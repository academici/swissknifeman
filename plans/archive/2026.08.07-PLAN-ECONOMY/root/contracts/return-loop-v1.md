# Return Loop Contract v1

Status: frozen by `P4.3` on 2026-08-08.

The machine-readable policy is
[`return-loop-v1.spec.json`](return-loop-v1.spec.json). The JSON is the sole source of field names,
closed enums, the default cap, ladder predicates, outcome flags, refusal codes, and owner-packet
members. This document defines their meaning and boundaries without maintaining a second schema.

## Purpose and grouping boundary

The contract limits repeated design↔exec returns for one durable fingerprint produced under
`return-fingerprint` v1. A fingerprint in either the `classified` or `provisional` namespace owns
an independent counter. A change of fingerprint starts a separate ladder and never inherits another
fingerprint's count. An `ungroupable` event remains recorded and measurable but cannot form a counted
group or cross the ceiling.

The ceiling is a contract parameter named `same_return_max`, not an implementation literal. Its
default deliberately reuses the fleet's frozen `same_finding_max` value rather than inventing a
second meaning for “the third occurrence.” Changing the default requires a new version of this
contract and consumer reconciliation; callers may supply the parameter but may not embed a separate
comparison constant.

## Adaptive ladder

The first eligible occurrence is repaired locally only when the failure is deterministic,
reproducible, confined to the declared Scope and Files, and carries no risk trigger. The second
occurrence of the same durable fingerprint receives exactly one isolated review. A risk trigger
selects that isolated review immediately, including on the first occurrence. The words `blocked`
and `escalated` are observations, never triggers by themselves.

The third occurrence with the default cap crosses the ceiling and raises the owner gate. Review
cannot decrease the count, replace the fingerprint, or authorize continuation above the cap. Its
verdict may permit continuation below the cap only after the required isolated review has actually
completed. This is the monotone boundary consumed by P4.5.

## Orthogonality to existing budgets

| Budget | Counted subject | Unit | Relationship to this contract |
|:--|:--|:--|:--|
| `AUDIT_ROUNDS_MAX` | audit passes over a phase | phase × audit pass | unchanged; does not count design↔exec returns |
| `SAME_FINDING_MAX` | repair rounds for one review finding | finding × fix round | unchanged; only its frozen default value is reused |
| item attempt counter | executions recorded for one item | item × execution attempt | unchanged; attempts do not establish equal return reasons |
| `same_return_max` | returns for one durable fingerprint | fingerprint × return event | new and independent of all three counters above |

No producer or consumer of this contract may modify the other three budgets as part of return-loop
handling.

## Blocking force and authority

Every machine outcome has explicit blocking and recording semantics in the adjacent specification.
Below the cap, the ladder determines whether local repair may proceed or isolated review must finish.
Crossing the cap blocks the affected subject and returns the existing action class `OWNER` with
attention `batched`. Independent legal work may continue; no `OWNER` result authorizes a side effect.
An ungroupable event is non-blocking but must be recorded.

The action and attention vocabularies are borrowed unchanged from the frozen
`authority-policy-v1`. Its closed sets are not extended. In particular, `immediate` remains reserved
for security, destructive, and irreversible cases; repetition alone receives `batched`. P4 refusal
codes live only in the adjacent return-loop specification and are never appended to the donor's
closed `reason_codes` set (D6, D53).

There is no advisory, warn-only, or bypass mode. A producer flag that prints the violation while
allowing the subject to continue would violate D43 and is not part of this contract.

## Owner-gate packet and the P5 boundary

The packet is the evidence needed to decide the blocked fingerprint, not a notification. It carries
the reviewable fingerprint tuple beside its digest, the observed count beside the effective cap, the
complete history for that fingerprint, all available return judgements, and the resolutions already
tried. Each history event preserves its time, attempt, actor, command, and links to decision and
finding records. Omitting that history makes the packet invalid.

P4 owns this packet's content and the blocking force. P5 owns the `DecisionRequest` transport around
it: alternatives, default, timeout, and the mandatory escalate/reject choices. P5 must consume the
packet without rebuilding it or changing the cap (D54). Until that transport exists, crossing the
ceiling is a hard stop that prints the complete packet.

## Escalation qualification

D13-б2 requires every escalation to be qualified as a genuinely new circumstance, a repeat tied to
its fingerprint digest and observed count, or unqualifiable because the durable carrier needed to
recover the count is absent. The last state is first-class: it cannot be treated as new. The exact
closed values and evidence required for each are defined only by the machine specification.

## Rejected alternatives

- **A separate return cap.** Rejected because it creates two fleet meanings for the third recurrence;
  the frozen `same_finding_max` default is reused.
- **`immediate` attention.** Rejected because the donor reserves it for security, destructive, and
  irreversible cases; ordinary loop ownership is batchable.
- **Treating unqualifiable as new.** Rejected because missing durable evidence would silently reset
  the mechanism and create a fail-open path (D55).
- **Making provisional evidence non-blocking.** Rejected because omitting a seam declaration would
  then bypass the cap; provisional and classified counters have equal force.
- **Extending donor refusal codes.** Rejected because `authority-policy-v1` is frozen and paused;
  return-loop failures have their own namespace in the P4 specification.

Implementing the reducer and opt-in checks belongs to P4.4. Judgement semantics belong to P4.5 and
P4.6. Enabling checks in command paths belongs to P6.
