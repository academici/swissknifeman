# ADR 0033: error/v1: `context_limit`, request identity, `unknown` is not `unknown_outcome`

## Status

Accepted

## Context

The taxonomy of [ADR 0017](0017-provider-boundary-and-error-taxonomy.md) had eleven classes. A class added to a
closed enum after readers exist breaks them, and an exhausted context needs a different reaction than a retry.

## Decision

`error/v1` has twelve classes: the eleven of ADR 0017 plus `context_limit` (the context is exhausted, so retrying or
switching provider is useless; the run policy chooses re-plan or compaction). The record gets two optional fields:
`request_id` (the provider or CLI request identifier) and `diagnostic_ref` (a reference to an artifact with the raw
text; the text itself never enters `safe_message`). `unknown` means the failure could not be classified. It is not
`unknown_outcome`, the status of an orchestration stage meaning the request may have been executed, which requires a
reconcile against the effect receipt before any retry. `cancelled` is not an error class but a kind of run event.
`attempt_consumed_quota` and `output_may_have_been_produced` are properties of an attempt in the stage result of
orch, not of `aicore`. Rules for `context_limit` are added to `configs/provider-errors.json` only after real CLI
messages are observed. `aicore.provider` contains no waiting and no retry code.

## Alternatives considered

- Add the class later: rejected, a closed enum would need `v2`.

## Consequences

- The schema description states the difference between `unknown` and `unknown_outcome`.

## Supersedes

Extends the class list of [ADR 0017](0017-provider-boundary-and-error-taxonomy.md).
