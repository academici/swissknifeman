# Library of Code Guidance patterns for standard item classes

Three proven Code Guidance wording templates - plan-design for authoring
items of these classes are referenced here and provide specifics, rather than invent
reformulation (P0.3 rec#10). Source - semantically identical formulations,
independently invented plans AGENTOOLS (P2.8/P3.8), FLEX-IMPL (P2.2),
THEMEON (P0.1). `<…>` — substitution slots.

## 0. Evidence-first execution — adaptive items

For items with external checks, generation or shared-tree noise.

```text
Before stopping, use observe → minimal reproduce → classify → act → verify.
procedural/transient/dependency-not-ready/unrelated-pre-existing signal fix safe
fallback, bounded wait or local repair in the same root; acceptance/safety/authority - stop
only after actual-impact evidence. Routing correct before journal start, future carrier does not
producer RED, and terminalize the external process only after PID/output/state reconciliation.
Repeat fingerprint first changes tactics; one scoped review is allowed only after repetition or
new material scope/SHA/risk trigger. Deterministic non-material bookkeeping drift - one
regeneration + gate rerun in the current attempt; sealed spec, safety, authority and acceptance are not inline.
```

## 1. Anti-fitting - conformance/contract-items

For items, where the code is checked against a standard: contract tests, golden vectors,
compatibility with spec/SDK.

```text
No special code “for vector/test”: the implementation must pass <standard:
contract tests / golden vectors / spec> in a common way. Implementation divergence
with a standard = signal, not interference - parse to the root (error in code OR in
standard) and record the output in Completion Notes; silently fit <code/test/
vector> to green PROHIBITED.
```

## 2. Anti-self-deception - gate-items

For items gates: the precondition must be closed before the work is considered
delivered (migrations, feature flags, external dependencies, foreign phases).

```text
IT IS FORBIDDEN to mark item 🟢 when the precondition is not closed <gate: what exactly should
be closed and how to check>. Bypass the gate (with a stub, TODO, “I’ll check later”,
by weakening Validation) is prohibited: the gate is not passed → status remains 🟡/🔴 +
Pending Work with exact reason. Passage of the gate is confirmed <artifact:
command/log/string>, not in words.
```

## 3. If-then escalation to D#

For items standing on a specific D-log solution: the detected condition X changes
basis for the decision - the performer does not continue without permission.

```text
If <condition X: fact that breaks the premise> - DO NOT continue without permission:
stop and escalate according to the protocol (SKILL section 10), this changes the decision
<D#>. Unauthorized bypass/replacement of a solution = defect in execution; fixation - ESCALATION-
block in item + Escalation Needed: yes.
```
