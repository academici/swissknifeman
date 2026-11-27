---
name: diagnosing-bugs
description: "Diagnose software regressions with a repeatable observation, evidence, and a verified fix."
---

# Diagnosing Bugs

Capture the expected and observed behavior, relevant version and conditions,
and the smallest repeatable case. For intermittent failures, collect enough
observations to distinguish the failure from environmental noise.

Follow the failing path through relevant code, state, and logs. Form a
hypothesis with a prediction and choose an inexpensive observation that can
confirm or rule it out. Record what each result changes in your diagnosis.
Use isolated, reversible changes while testing hypotheses.

When the cause is established, make a focused fix and add or update a
regression check when appropriate. Re-run the failing case and affected
checks. Report the cause, supporting evidence, and remaining uncertainty.
