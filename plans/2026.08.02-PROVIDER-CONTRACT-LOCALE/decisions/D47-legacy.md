---
id: D47
date: 2026-08-03
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

P5.1–P5.4 share one durable append-only `artifacts/P5/fleet-transaction-log.jsonl`: canonical hash-chained events are flushed and `fsync`'d before/after each project transaction boundary, carry stable project/action/transaction IDs, frozen manifest/action-set/source identities, pre/post hashes and the closed `before → applied → readback-passed

## Почему

readback-failed → accepted
