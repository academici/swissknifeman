# Query

Best practice for AI coding agents to log deviations, blockers and difficulties during task execution (friction log, decision log, structured execution journal) without overloading the agent: schemas or formats used by Devin, OpenHands, SWE-agent, Claude Code, Codex. Recommend a minimal event schema.

# Answer

## Recommendation

Use two layers, not one agent-written diary:
- An automatic execution trace records tool calls, results, failures, timings, and lifecycle events. The harness writes it; the agent doesn’t need to narrate routine work.
- A sparse friction/decision log records only events that changed the plan, blocked progress, exposed a failed assumption, or needed human input. Ask the agent for a short structured entry at natural boundaries—usually when recovering from a failure, changing approach, or pausing—not after every tool call.
This separation follows the useful pattern in OpenHands’ append-only, typed event log and SWE-agent’s per-step trajectory of action and observation, while avoiding the token cost of turning every tool interaction into prose.

## What the tools suggest

The tools’ native traces answer “what happened?” A useful friction entry adds only “what did it change, and what happens next?”

## Minimal event schema

Store one JSON object per event in JSONL. Keep required fields small; put extra context in details only when it helps someone resume, review, or diagnose the task.
```
{ "v": 1, "ts": "2026-10-05T06:00:00Z", "task_id": "issue-123", "type": "blocker", "summary": "Integration test cannot reach the local PostgreSQL service.", "impact": "Tests requiring PostgreSQL are unverified.", "next": "Start the test database and rerun the integration suite.", "ref": { "tool_call_id": "call-456", "url": "https://github.com/org/repo/issues/123" } }
```
Required: v, ts, task_id, type, summary.Recommended: impact, next, ref. Omit optional fields when they add no value.
Keep type to a small enum:
- deviation — departed from the requested plan or a stated constraint.
- blocker — progress depends on missing access, input, a service, or a decision.
- difficulty — an unexpected failure or repeated unsuccessful attempt, with a recovery path or a clear statement that none is known.
- decision — chose among plausible approaches; include the reason and consequence.
- assumption — proceeded on an uncertain premise that could affect correctness.
The execution trace should carry details such as command text, tool output, and timestamps. The friction entry should link to that trace by ID rather than duplicate it. For a decision, summary can state the choice; put alternatives and rationale in impact or details if needed.

## Keep logging cheap

- Log only when something meaningful changes: a plan, a correctness assumption, a constraint, a dependency, or the ability to finish.
- Record a difficulty after a useful signal—such as a failed test or error—not after each exploratory command. If retries are routine, summarize them in one event.
- Use a deterministic hook or harness for tool outcomes and failures; don’t ask the model to reproduce facts already captured in the trace. Claude Code hooks, for example, can observe tool success and failure events.
- Don’t require hidden reasoning or long free-form “thoughts.” Ask for a short, outcome-focused explanation: what changed, why it matters, and what happens next.
- Emit a final completion event in the task result or trace, not necessarily as another friction entry. Include unresolved blockers and unverified requirements there.
Rule of thumb: if the entry would not change a reviewer’s understanding, next action, or future diagnosis, don’t write it. The event stream is the audit trail; the friction log is the sparse index into the parts that need attention.

Sources:
1. [openhands](https://docs.openhands.dev/sdk/arch/events)
2. [github](https://github.com/SWE-agent/SWE-agent/blob/main/docs/usage/trajectories.md)
3. [anthropic](https://docs.anthropic.com/en/docs/claude-code/hooks)
