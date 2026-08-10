# Audit-9 protected-authority resolver recon

## Sources and observed contract

- Audit input: `plan.md` → last `## Audit design — 2026-08-05`, pass 9, findings 1–3.
- Resolver source: `packages/task/lib/task/task_contract.py` →
  `_OWNER_GRANT_RECORD_RE`, `_OWNER_MESSAGE_RECORD_RE`, `_resolve_authority`.
- Existing owner intent: `brief/16-audit8-owner-carriers-and-execution.md`.

The protected resolver accepts one and only one Decision Log record for a gate. Its `Решение`
cell must consist solely of `[OWNER-GRANT:<gate>] branch=`...`; scope=`...`;
owner-message=`brief/<file>.md#<message-id>``. The referenced Layer-0 file must contain exactly
one matching `[REPOSITORY-OWNER-MESSAGE:<message-id>]` record with the same gate, branch and
scope plus `provenance=`repository-owner``. The item Implementation Rules must name that exact
gate marker. RAG:— (repo-grounded: `packages/task/lib/task/task_contract.py:95-121,193-273`).

## Append-forward consequence

D91 and D92 contain the old gate markers but fail the exact record grammar. Adding another row
with either old gate ID would leave two marker-bearing rows and therefore fail the resolver's
`len(grant_rows) == 1` ambiguity check. A lawful successor must use a fresh gate ID, preserve the
already-approved branch/scope byte-for-byte, add its own exact Layer-0 message, and update only
the live consumer specs to request the successor. Historical D91/D92 remain untouched.
RAG:— (repo-grounded: `packages/task/lib/task/task_contract.py:246-273`; audit-9 findings 1–2).

## Provenance finding

`journal.jsonl` line 111 is audit pass 9; no earlier event records the plan-design run that
introduced D91–D94. The only allowed repair is a new append event naming the historical omission
and the current finish remediation; no existing JSONL byte is rewritten. RAG:— (repo-grounded:
`journal.jsonl`; plan-protocol §2 append-only journal rule; audit-9 finding 3).
