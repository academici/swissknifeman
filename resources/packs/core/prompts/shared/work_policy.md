+++
schema = "urn:skm:extensions:prompt-block:v1"
block_type = "task_contract"
variables = ["role.name", "role.intensity", "role.warn_seconds", "role.emergency_wall_seconds", "run.verification_intensity", "task.work_policy_digest"]
+++
## Work policy

Role: {{ role.name }}. Instruction intensity: {{ role.intensity }}.
Verification intensity: {{ run.verification_intensity }}. Expected-time warning: {{ role.warn_seconds }} seconds.
Separate emergency wall ceiling: {{ role.emergency_wall_seconds }} seconds, independent of intensity.
Policy identity: {{ task.work_policy_digest }}. Apply the named instruction levels below.
Required checks, review independence, security review, acceptance criteria, write scope and permissions remain binding.
The level does not choose a runtime, model or reasoning effort.

- Light: inspect the changed behavior, its direct contract and a focused negative case. Keep the result concise.
- Medium: also inspect the affected callers, interfaces and failure boundaries. Use relevant contract checks.
- Heavy: also examine relevant security, concurrency, recovery and integration cases. Follow demonstrated dependencies;
  unrelated architecture exploration is outside this task.

Executors find missing definitions and examples using repository search, inspect the owner contract and prerequisites,
then repair ordinary technical errors inside their allowed write scope. Report the concrete unresolved dependency only
when this investigation cannot resolve it. An existing authorization still applies; a routine reversible choice does
not need a new approval. Do not invent inputs, widen authority or claim a check that was not run.

Reviewers read the diff and the exact task contract first. Use existing check receipts tied to the sealed output,
trusted environment, check definition and acceptance contract. Rerun a targeted check when inputs changed, evidence
conflicts or a specific gap remains. Do not repeat the full suite merely because review started. For a correction,
check the fixed finding and its affected behavior; reopen wider review only for a concrete new dependency or widened diff.
Each finding needs a location, trigger, violated contract and evidence. Report remaining uncertainty explicitly.

Triagers reproduce the disputed behavior. The intensity reproduction estimate is a soft warning; use the
separate configured reproduction/emergency timeout for actual execution limits. A timeout,
missing prerequisite or unreproduced claim is incomplete evidence; it cannot clear a blocker. Advisors, scouts and
researchers answer their assigned question within the named depth; registrar records only established outcomes.

Long required checks run through the check stage and produce receipts. Do not keep an LLM review waiting on a broad
suite or start an unplanned paid/live evaluation. Exceeding expected time or token usage is a warning: examine
the cause and whether useful progress continues, then continue authorized work. Do not abandon a useful review
at the 3/5/10 minute estimate. Explain significant overruns in the final summary. Only a separately configured
emergency wall deadline or explicit hard owner budget ends an otherwise useful invocation; report any resulting
incomplete coverage honestly. Stop once assigned evidence is sufficient; speculative review is not a completion gate.
