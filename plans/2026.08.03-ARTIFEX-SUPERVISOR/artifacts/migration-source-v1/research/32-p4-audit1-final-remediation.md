# P4 audit-1 final remediation design

## Sources

This synthesis uses the appended `## Audit P4 — 2026-08-05` block in `phases/P4.md`,
`brief/21-p4-audit1-final-remediation.md`, the exact git history named by F1–F7,
`packages/task/lib/task/task_contract.py`, the P4 completion carriers, and the current
Harness tests/generators. No external facts are required. RAG:— (repo-grounded).

## Finite recovery chain

The audit findings split into two sequential producers:

| Producer | Findings | Terminal output |
|:--|:--|:--|
| P4.7 | F2–F7 | committed-tree Harness gate plus independently validated append-forward provenance map |
| P4.8 | F1 and final G2 fan-in | resolver-valid protected successor plus new G2 current-package assurance snapshot |

P4.7 comes first because P4.8 may not publish the terminal G2 successor while the affected-package
Harness gate or the provenance/status carrier is red. P4.8 comes second because its protected
contract transition must consume the corrected F2–F7 record and run the final aggregate gates.
After both items are terminal, `plan-close P4` rebuilds closure/handoff state and the second P4
audit is the final independent checkpoint allowed by D98. RAG:— (repo-grounded: audit findings,
plan-protocol status and close rules).

## Historical status reconciliation

- P4.1 remains `🟢`: its missing original close row/handoff boundary is a process-provenance
  deviation, not a product acceptance failure.
- P4.2 becomes `🟠`: `test_scheduler.py` was a material file outside its declared Files; the
  delayed bookkeeping/corrective-close topology is recorded as an additional process deviation.
- P4.4 becomes `🟠`: `activity.py` carried material runtime enforcement outside Files.
- P4.5 becomes `🟠`: protected contract scope and D102 appeared only after mutation, so the
  historical G2 producer is not the terminal authority proof.
- P4.6 becomes `🟠`: its advertised full Harness validation is red on `10422237`.

Old Completion Notes and journal rows stay unchanged. The current fields, one Update Log commit map,
the P4.7 machine-readable reconciliation artifact, and the future P4.7/P4.8 close records are the
append-forward correction. RAG:— (repo-grounded: plan-protocol §6/§8 and Audit F2–F7).

## Protected successor

D102 remains historical and cannot validate itself. P4.8 uses the new gate identity
`G-OWNER-P4.8-G2-REQUALIFICATION`, exact branch/scope, and Layer-0 message from brief/21.
Before mutation, the executor must build/evaluate a Task Contract with those exact three request
values and require `authority.class=owner-gate`, `granted=true`, and `pre_mutation=allow`.
The item then checks the complete `17a57adc..23f71d34` protected diff against the declared scope,
repairs only deviations from the five packet fields plus `blocking_dependencies` and
`authority_attention` semantics, writes an independent requalification record, and republishes G2
from committed bytes. Any extra semantic widening or scope mismatch stops before G2 mutation.
RAG:— (repo-grounded: `task_contract.py:193-322`, Audit F1, D102 historical diff).

## Harness and generated-reference repair

P4.7 replaces the stale generated `provider-instructions.md` only through a new deterministic
write/check generator around `operator_reference()`, removes hard-coded inventory totals from the
rendered source, and keeps the byte-equality test. The live-plan reader test must use a committed
fixture/archive path or a temp fixture, never assume an active plan directory exists. Full Harness
validation is executed after the item commit in a clean detached checkout of that commit, so an
ambient dirty tree cannot make the published gate green. RAG:— (repo-grounded:
`packages/harness/tests/test_instruction_compatibility.py:85-88`,
`packages/harness/tests/test_run_plan_reader.py:162-169`, Audit F2).

## Stop condition

This design pass is complete when P4 is reopened by all four protocol steps, P4.7/P4.8 are fully
specified and routed, every F1–F7 finding has one explicit owner, the live handoff points to P4.7,
Task Contract ordinary/protected probes are deterministic, and plan-lint/conflict/citation gates are
green. There is no next design pass. RAG:— (direct owner directive and repo-grounded protocol).
