# Target architecture

## System boundary

Artifex is a deterministic process around provider CLIs. It does not become a third provider,
rewrite plan-protocol, or keep a second status board.

```text
frozen plan + owner mandate + repo canons
                  |
           plan/slice compiler
                  |
       durable scheduler + arbiter <---- resume/reconcile
          |           |       |
     Codex adapter Claude adapter owner queue
          |           |
       fresh workers (one bounded slice each)
                  |
        schema + scope + validation gate
                  |
       accept / bounded auto-fix / owner
                  |
 plan bookkeeping + terminal packet + redacted mAInd summary
```

## Components

### Compiler

Reads the canonical plan/status/handoff and frozen contracts at pinned hashes, rejects skeleton or
unsupported routes, and emits immutable slice manifests. It never changes plan status.

### Durable scheduler

Owns run and slice state, attempt budgets, dependencies, one-writer lock, parallelism ceiling and
circuit breakers. The scheduler only evaluates typed predicates from frozen contracts.

### Provider adapters

Translate one provider-neutral worker envelope into exact current CLI invocation and translate
events/exits back into a closed taxonomy. Provider-specific capabilities are additive; an
unsupported feature refuses or chooses an explicitly permitted degraded route.

### Workers

Fresh contexts receive a minimal bundle: slice intent, exact reads/files, frozen canons, authority
class, validation commands, output schema and budget. They cannot extend their own scope or spawn
children unless the slice policy explicitly allows a bounded read-only child.

### Validator/arbiter

Treats worker output as untrusted. It checks schema, file delta, source hashes, authority, tests and
evidence before accepting, retrying a bounded point-fix, rolling back or queuing an owner decision.

### Reporter

Derives all status and economy summaries from the durable journal. It may append plan-protocol
bookkeeping only after an accepted slice and may publish a minimized terminal memory summary only
after the repository evidence is committed.

## Control-loop states

The exact enum is P1.1's contract, but it must distinguish at least:

`compiled → ready → intent_durable → dispatched → observed → validating → accepted`

with explicit terminal or waiting paths for `rolled_back`, `owner_attention`, `budget_exhausted`,
`provider_unavailable`, `refused`, and `incident`. `dispatched` and `worker_success` are never aliases
for `accepted`.

## Why this should save coordinator tokens

The durable scheduler carries state in files rather than re-explaining the whole phase to a parent
model. Workers see one slice and return a small envelope. The claim remains conditional: extra
workers and retries can still cost more total tokens, so P5 measures full-run economics.

RAG:✅ architecture principles verified in `findings/01-external-agent-runtime-2026-08-03.md`;
component boundaries are internal synthesis.
