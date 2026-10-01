# Declarative execution policy

Media `packages/harness/configs/common/agent-packs/execution-policy.json` answers two
issues that were previously resolved ad hoc in each session: *when subagent spawning is justified* and
*that the subagent is required to carry out the task*. Schematic sealed with contract
 — four
section, the values are copied from there verbatim along with `provenance`.

## Four sections

- **`spawn_threshold`** — decision rule (all positive-conditions YES, none negative) plus
  scale `scale_by_task_class` (per-task class, not token budget).
- **`max_parallel_agents`** — concurrency ceilings by actor and provider.
- **`allowed_agent_roles`** — derived rule over canon `roles.json`, second directory
  does not create roles.
- **`delegation_contract`** — five required subagent job fields + life cycle of points
  coercion `pending`/`enforced` with `pending_until`.

## Gate - `execpolicy.py`

`packages/harness/lib/harness/execpolicy.py` checks the FORM of data: private key sets,
mandatory `provenance` for numeric fields, resolve `allowed_agent_roles` vs `roles.json`,
and enforcement point status. Twenty conditions §10 contract - line-by-line checklist, each
check in the code carries the number of the condition being closed.

```
PYTHONPATH=packages/harness/lib python3 -m harness.execpolicy --check
```

Step `[10/10]` in `packages/harness/scripts/validate.sh`. File - generated media by
sealed diagram: corrected according to the contract, not by hand (discrepancy with
§2–§5 contract - media defect, not local solution).

## Consumer - grammar PLAN

Period `delegation_contract` translated P4.4 from `pending` in `enforced`: five job fields
are required in grammar `_common.orchestrator` (both provider projections). Coercion -
via consumer (orchestrator reads and requires fields), not automatic runtime interception -
the validator only checks the form of the media, not the actual behavior of the orchestrator in a live session.

## Related

[Canon of root instructions](./instruction-canon) (adjacent carrier of the same kind - rule +
data + gate); contract `execution-policy-v1.md` (full diagram, versions, trace
«field → consumer»).
