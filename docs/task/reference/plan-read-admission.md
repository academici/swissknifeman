# Stage-aware admission budget reading

`task.plan_weight` for Layout v2 plans distinguishes when D2 is applied without changing the unit,
threshold `100000`, single-read limits or anti-displacement D74. The public contract is described in
[read-budget v1 contract](./read-budget-contract.md); There are no numeric fallbacks in the code.

## States

- `historical-pre-v2` - the item was terminal no later than the Layout v2 activation journal event.
  Its measurement remains baseline evidence, the closed technical specification is not rewritten for the sake of a green outcome.
- `pending-producer` - each missing required input is associated with an existing one
  is an unfinished predecessor item, and its `Deliverables` is called the same path. This is deferred,
  not pass and not zero weight.
- `ready` - D2(a) and D2(b) are required before mutation. Generic missing, unresolved entry, invalid
  producer edge or missing output of an already terminal producer gives fail-closed.

Producer is declared at the corresponding position `Required Reads`:

```text
2) `root/contracts/bundle-v1.md` (producer: P3.1)
```

Compact form `producer=P3.1` is equivalent. The producer must exist before the consumer,
and its `Deliverables` - address the missing path. Manual `admission_state`, warning-mode,
allowlist or baseline-exception no.

## Output and API

### Mandatory layout path

`plan-weight item` selects a path only according to the declared `Layout`:

- v1 preserves the legacy order `plan → handoff → phase → Required Reads`;
- v2 measures exactly five carrier roles `plan-core → phase-context → item-spec →
  item-input-bundle → item-state`. `handoff.md` is not included in executor path v2.

For v2, the tool first checks the byte-freshness of the generated bundle and state. Then he reads
only the listed bundle selections, compares the digest of the source and the selected fragment and calculates
them as `bundle-input`. Repeating the same source with the same selector does not double the weight; different selectors
of the same source remain different reading units. Stale carrier, digest mismatch or
undecidable selection gives fail-closed gap, not zero weight.

```bash
python3 packages/task/scripts/plan-weight.py item plans/<PLAN-ID> Pn.m --json
```

Item record contains `admission_state`, `producer_item`, `producer_edges`, separate
`admission_gaps`, `d2a_pass`, `d2b_pass` and `admission_pass`. The last field is boolean only for
`ready`; for historical/pending it is `null`. Summary `totals.admission` carries version/path
contract, number of states, gap codes and `ready_failed`.

The dimension remains in `task.plan_weight`; `task.plan_admission` only classifies stage and
checks producer edges. Pre-mutation consumers are required to call this API, not create a second one
weight counter or own interpretation of missing inputs.
