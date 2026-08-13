# read-budget v1

**Contract ID:** `read-budget`
**Version:** `1.1.0`
**Status:** frozen
**Owner gate:** inherited repository contract D113–D115 (2026-08-08)
**Applies to:** this executable master plan using Layout v2

## Qualified unit

Estimated upper-bound input tokens from repository `token-estimate-calibration` v2.0.0 for
`codex/gpt-5.6-terra`, adapter `codex-exec-jsonl-v1`, differential input protocol v2.

## Per-item read budget — D2(a)

```text
pass_item(i) = resolved(i) AND estimated_required_read_tokens(i) <= 100000
```

## Single-read file budget — D2(b)

```text
pass_file(f) = bytes(f) <= 262144 AND est_tokens(f) <= 25000
```

## Stage-aware admission

- `historical-pre-v2`: terminal before v2 activation;
- `pending-producer`: absent input has an earlier explicit `producer: Pn.m` whose Deliverables name it;
- `ready`: all declared reads exist and both budgets apply before mutation.

No numeric fallback, warning-only mode or silent unresolved input is allowed. Aggregate read weight
must be reported beside per-item results so splitting cannot manufacture acceptance.
