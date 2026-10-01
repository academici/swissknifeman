# Template loop-kickoff — copy to .claude/commands/loop.md project

Start prompt for an iterative task: sets the goal, check between circles,
iteration limit, exit criterion and hard-stop. Runs built-in `/loop`
(self-paced) — the agent maintains the pace himself. Runner gives Claude Code; this template
gives the contents (what to check and when to stop).

```markdown
---
description: Run the task in iterative mode with checking between circles
argument-hint: <task goal>
---

Execute the task in loop-mode. Self-pace: run a check after each lap,
read the output and continue only if exit condition not reached.

Goal:            $ARGUMENTS
Active skills: task-brief-template (contract), anti-drift (stop controller),
                 cross-layer-change-checklist (verifier), code-simplifier (gate)
Between-check:   <test command: test / lint / `git log --oneline`>
Max iterations:  <3–12; loop insurance>
Exit condition:  <objective state = task completed, according to the check output>

Hard stop — stop and request approval if:
- second fix of the same symptom (search root cause, not the third patch);
- the number of files is growing/abstractions, and exit condition is not approaching;
- ~20 iterations without working result → do handoff (see anti-drift).

Guardrails (anti-gaming): don't change the check to make it pass; don't miss it
verification; Don't fake success by manipulating metrics. Exit is estimated by
honest conclusion Between-check, and not according to your statement.

After each lap - a short status: what has been done, what the check showed,
has been reached exit.
```
