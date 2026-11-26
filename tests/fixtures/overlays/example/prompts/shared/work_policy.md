+++
schema = "urn:skm:extensions:prompt-block:v1"
block_type = "task_contract"
variables = ["role.name", "role.intensity", "role.warn_seconds", "role.emergency_wall_seconds", "run.verification_intensity", "task.work_policy_digest"]
+++
## Operator overlay work policy

Role: {{ role.name }}. Instruction intensity: {{ role.intensity }}.
Verification intensity: {{ run.verification_intensity }}. Expected-time warning: {{ role.warn_seconds }} seconds.
Emergency wall ceiling: {{ role.emergency_wall_seconds }} seconds.
Policy identity: {{ task.work_policy_digest }}.

Apply the operator verification checklist in addition to mandatory contract, review, and permission gates:
- Verify boundary invariants and deterministic tie-breaking on every modified path.
- Record concrete command and test evidence before closing the task.
