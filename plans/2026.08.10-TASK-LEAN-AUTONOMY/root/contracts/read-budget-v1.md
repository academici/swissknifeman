# read-budget v1

**Contract ID:** `read-budget`
**Version:** `1.1.0`
**Status:** frozen
**Owner gate:** D113–D115 (2026-08-08)
**Applies to:** new executable master plans using layout v2

## 1. Qualified unit

The unit of every threshold in this contract is **estimated upper-bound input tokens from
`token-estimate-calibration` v2.0.0**, target `codex/gpt-5.6-terra`, adapter
`codex-exec-jsonl-v1`, probe protocol `differential-input-total-v2`, usage semantics
`provider-reported-input-total-v1`.

The calibration target is part of the unit. A value produced for another provider, model, or
probe protocol is not numerically interchangeable with this value and cannot silently replace it.

## 2. Per-item read budget — D2(a)

For every item, resolve the complete mandatory read path and compute its weight with the qualified
unit from §1, including the estimator's per-file overhead.

```text
pass_item(i) = resolved(i) AND estimated_required_read_tokens(i) <= 100000
```

`Required Reads` entries that cannot be resolved to readable files fail closed. They are reported
as unresolved input and are never counted as zero.

## 3. Single-read file budget — D2(b)

Every file on an item's mandatory read path must pass both independently measured limits from
`read-limit` v1:

```text
pass_file(f) = bytes(f) <= 262144 AND est_tokens(f) <= 25000
```

The two limits are a conjunction and cannot be converted into one another. Reading an over-limit
file page by page does not satisfy this condition: the protocol requires the whole file to be
readable in one tool call.

## 4. Applicability boundary of the upper estimate

The upper-bound property was established on a bounded corpus of real plan prose and dense-ASCII
inputs, not as a statistical proof for every future file. Calibration v2 adds the contextual
`dense_ascii` class (`[0-9A-Za-z+/=]` runs of at least 32 characters) that closed the observed
underestimate on mandatory JSON artifacts; its frozen corpus recorded 8 accepted real samples,
0 bound violations, and `max_true_over_estimate = 1.0846677212727815`.

Any observed underestimate is a contract failure, not tolerance. It requires a new qualified
calibration artifact, a decision record, and revalidation before the new unit can replace §1.
Changing provider, model, probe protocol, classifier, or usage semantics triggers the same review.

## 5. Anti-displacement rule — агрегат и дробление (D74)

The aggregate (`агрегат`) is the total mandatory-read weight over the plan's closed read graph: all mandatory
carriers, including generated carriers, plus per-file overhead. Every acceptance report must print
this aggregate beside the per-item result and compare it with the aggregate from before the
restructuring.

Splitting (`дробление`) an item below the per-item ceiling or moving mandatory content outside the measured graph
is not by itself an improvement. The report must distinguish, by the aggregate values, between:

- splitting that reduced total mandatory work; and
- splitting that left the aggregate unchanged or increased it.

Every acceptance report must answer: **Could this result pass only because work was split, moved,
cached, deferred, or excluded?** A positive or unresolved answer fails acceptance until the
aggregate and graph boundary demonstrate a real reduction.

## 6. Acceptance output

For each checked plan, the machine-readable and human-readable reports must include:

- the qualified calibration target and artifact version;
- maximum per-item mandatory-read weight and the `100000` comparison;
- the closed-graph aggregate and its before/after comparison;
- unresolved or unreadable mandatory inputs;
- every file failing either independent single-read limit; and
- the D74 adversarial answer from §5.

## 7. Stage-aware admission

Layout-v2 items have exactly one admission state:

- `historical-pre-v2`: the journal records the item as terminal no later than the journal event
  that activates Layout v2. Its measurements remain baseline evidence; historical item specs are
  not rewritten to manufacture a pass.
- `pending-producer`: every absent required input is linked to one existing, non-terminal,
  strictly earlier producer item. The producer's `Deliverables` field must name the absent path.
  This state is deferred, never passed and never counted as zero.
- `ready`: the hard D2(a) and D2(b) predicates apply before mutation. Any generic missing input,
  unresolved entry, invalid producer edge, or absent output of a terminal producer fails closed.

The producer edge is declared on the corresponding `Required Reads` entry as
`producer: Pn.m` (the equivalent compact spelling `producer=Pn.m` is accepted). The relation is
valid only when the named item exists earlier in plan order and its `Deliverables` field names the
same missing path. State is derived from committed item status, journal history and these edges;
there is no manual state flag, warning mode, allowlist or baseline exception.

Machine-readable output reports `admission_state`, `producer_item`, `producer_edges`, separate
`admission_gaps`, `d2a_pass`, `d2b_pass`, and `admission_pass`. The latter is boolean only for
`ready`; it is `null` for historical or pending input.

## 8. Revision procedure

Changing the threshold, applicability, unit, or anti-displacement semantics is a public-contract
change. It requires an explicit owner decision, a new D-record, a freshly generated qualified
calibration when the unit changes, a machine measurement of the affected corpus, and a version
change to this contract. Generated calibration and measurement artifacts are regenerated by their
owners and are never edited by hand.

## 9. Provenance

This contract freezes D2(a), D2(b), D74, D107–D109, and the owner decisions D113–D115. The active
qualified calibration and provider boundary are frozen by D116–D122. Version 1.1.0 adds D131
stage-aware timing and producer edges without changing the unit, thresholds or D74.
