+++
schema = "urn:skm:extensions:prompt-block:v1"
block_type = "run_rules"
variables = ["run.attempt_no", "run.round_no", "run.workflow", "run.verification_intensity"]
+++
## Run rules

Workflow: `{{ run.workflow }}`. Attempt `{{ run.attempt_no }}`, round `{{ run.round_no }}`.
Verification intensity: `{{ run.verification_intensity }}`.

- Stay within the current stage assignment and return only the structured role result at the end of your turn.
- On round 2 or later, treat the latest answers, fix brief or review delta as the active delta while keeping the
  task contract, write scope and acceptance criteria in force.
- Keep execution deterministic and concise: inspect targeted evidence first, record unresolved blockers or open
  questions explicitly in the structured result, and stop once the required evidence for this stage is complete.
