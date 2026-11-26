# Repair: the `review-findings` block of P1.1 review.1

A role finished its work and ended its answer with a result block that does not fit the contract. You do not redo, judge or extend the work, read no file and run nothing. You rewrite that one block from the facts the answer states.

## Rules

- Keep every fact of the answer: statuses, paths, check ids and exits, verdicts, findings, reasons.
- Never invent a check, an exit, a verdict, a path, a finding or a reproduction the answer does not give; when a required fact is missing, use the closest honest statement of the answer (for example an issue that says what is missing).
- Never raise a status: a blocked answer stays blocked.
- Change only what the problem below names, plus what the contract needs for the block to be valid.
- The conductor compares your block with the role's own: a raised status, a lighter verdict, a lowered severity or a lost finding, question, escalation or check row is refused.

## The problem

```text
p
```

## The contract

End your answer with exactly one fenced block tagged `review-findings` holding one JSON object and nothing else:

```review-findings
{"verdict": "GREEN | ATTENTION | RED",
 "findings": [{"id": "F1", "severity": "Blocker | Major | Minor | Nit", "confidence": "high | medium | low",
               "location": "path:line", "failure_scenario": "concrete inputs or state and the wrong outcome",
               "basis": "correctness | security | performance | project rule | input contract",
               "reproduction": "command or steps that show it, when you ran any"}],
 "questions": ["an uncertainty, asked as a question"],
 "residual_risk": "material risk when there are no findings"}
```

## The answer

```text
[… the start of the answer is cut …]
yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy
```

## Result

Answer with exactly one fenced block tagged `review-findings` holding the corrected JSON object, and nothing else.
