# Review P10.12, round 1 (grok/grok-4.7/high, headless read-only via planner-orch launch)
Stream: review-grok-round1.stream.jsonl (31 turns). Verdict: FINDINGS, all three reproduced and fixed by the executor.
1. ADR 0059 gave a non-existent contract URN -> fixed to the family id and the `<kind>` $id pattern.
2. ADR 0059 claimed the gate state in run.json -> fixed: register answer/receipt and orch.run.finished.
3. golden case harness-instructions-check not recaptured -> recaptured with reason.
Instruction texts verified verbatim by the reviewer.
