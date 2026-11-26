# ADR 0059: The `orch:work-source` port, owner fencing and the evidence gate

## Status

Accepted

## Context

`orch` has to take work from a plan without knowing the planner, and a result must not be registered by a run that no
longer owns the item or without proof that the checks ran.

## Decision

- **Port.** `orch` declares the extension point `work-source` (`orch:work-source` in `unit.json`) and the contract
  `urn:swissknifeman:orch:work-source` (`schemas/work-source/v1`: `input` and `output`, `$id` `urn:swissknifeman:orch:work-source:<kind>:v1`; operations `claim`, `brief`,
  `register`). The plugin is named by the `work_source` key of `[orch]` and reached through `aicore.ext.plugins`.
  `bridges/planner-orch` is the plugin (`extension.json`).
- **Claim.** An item is claimed with the run id as the owner session. A scenario unknown to `orch` is a `blocked` answer
  (`SCENARIO_UNKNOWN`); an item owned by another session is `blocked`, with no take-over. The attempt id is derived
  from the run id and the item, so repeating a claim returns the same answer.
- **Brief.** The brief is stored as a content-addressed artifact; the answer carries an `artifact-ref/v1`. Unchanged
  inputs reuse the artifact.
- **Register.** Registration is fenced by the owner session and epoch: a stale owner is `REGISTER_STALE_OWNER`. The
  evidence gate refuses a `done` result without evidence of every required check; the gate state is `pass`, `missing`,
  `red`, `stale` or `none` in the register answer, the register receipt and `orch.run.finished`.
- **CLI.** `orch.py source claim|brief|prepare|register` writes `run.json`, `launch-plan.json` and
  `receipts/register.json` into the run directory and emits `orch.run.*` events.

## Alternatives considered

- A fixed planner import in the core: rejected by the boundary rule.
- Registering without a gate: rejected, a green claim without evidence is the failure the gate exists for.

## Consequences

- Another work source is another plugin with the same contract.
- An engine that starts later reuses the same cycle.

## Supersedes

None.
