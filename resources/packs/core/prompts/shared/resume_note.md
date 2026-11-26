+++
schema = "urn:skm:extensions:prompt-block:v1"
block_type = "resume_note"
variables = ["run.attempt_no", "run.round_no"]
+++
## Resumed session

This turn resumes your active session at attempt `{{ run.attempt_no }}`, round `{{ run.round_no }}`.
Unchanged system constraints, role instructions, repository context and task contracts from earlier in this session
remain in effect and are not repeated here. Process the delta blocks below and end this turn with a complete,
self-contained JSON document matching your role result schema.
