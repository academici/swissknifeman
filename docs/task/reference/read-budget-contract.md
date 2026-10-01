# Read-budget v1 contract

**Contract ID:** `read-budget`
**Version:** `1.1.0`
**Status:** frozen

This contract specifies mandatory reading boundaries for new executable master plans with
`Layout | v2`.

## Qualified unit

All thresholds are measured in the estimated upper limit of input tokens from
`token-estimate-calibration` v2.0.0 for `codex/gpt-5.6-terra`, adapter
`codex-exec-jsonl-v1`, protocol `differential-input-total-v2` and semantics
`provider-reported-input-total-v1`. Values from a different provider, model, or protocol
are not interchangeable without new calibration.

## Thresholds

For each item the full mandatory read path must be allowed:

```text
pass_item(i) = resolved(i) AND estimated_required_read_tokens(i) <= 100000
```

Each file in this path must simultaneously pass:

```text
bytes(f) <= 262144 AND est_tokens(f) <= 25000
```

Unsolvable mandatory input fail-closed and is not considered null. Splitting an item or taking out
material outside the graph is not considered an improvement without reducing the overall mandatory-read
aggregate.

## Upper bound

The upper bound property is set on a limited corpus of real plan prose and dense-ASCII
inputs, not statistically proven for all files. Calibration v2 adds class
`dense_ascii` (`[0-9A-Za-z+/=]` runs at least 32 characters): 8 real ones recorded
received samples, 0 upper bound violations and
`max_true_over_estimate = 1.0846677212727815`.

The observed underpricing is a contract failure, not a tolerance. She demands something new
calibration artifact, D-record and revalidation; the same actions are needed when changing
provider, model, probe protocol, classifier or semantics usage.

## Anti-displacement

Aggregate — total mandatory-read weight of the complete closed plan graph, including generated
carriers and per-file overhead. Each acceptance report prints aggregate next to per-item
result and comparison with the state before restructuring. The report must answer whether
pass will appear only due to fragmentation, transfer, cache, defer or exclusion of work; positive
or an unresolved response blocks acceptance.

## Admission

layout-v2 item has exactly one admission state:

- `historical-pre-v2` - historical terminal item; its baseline is not overwritten.
- `pending-producer` - missing input named in Deliverables of earlier non-terminal
  producer item; this is defer, not pass.
- `ready` - both thresholds are applied; The absence or invalid producer connection blocks the work.

Report includes calibration, maximum per item, aggregate before/after, unresolved inputs,
violations of both limits and the answer to the question whether pass was reached only by transfer or
except for work.

## Change of contract

Changing threshold, unit, applicability or anti-displacement semantics requires a solution
owner, new D-record, new calibration when changing unit, machine measurement and
contract versions.

Full application rules and reporting fields: [read-admission](./plan-read-admission.md) and
[read-budget gate](./plan-read-budget-gate.md).

## Provenance

Contract archived from plan; original immutable carrier:
.
