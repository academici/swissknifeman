---
id: D113
date: 2026-08-06
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

[OWNER-DIRECTION:P5.5-TERMINALIZATION] Direct owner direction in `brief/28-p5.5-terminalization-owner-direction-2026-08-06.md` supersedes D111/D112 only for P5.5 terminal acceptance: the already completed minimized controlled observations (`codex=1/13539ms/4/OK`, `claude-code=1/4380ms/1/OK`) are the two assurance carrier rows. Historical D108/D111/D112 `PROVIDER_NONZERO` records remain append-only facts and are neither retried nor reclassified. No provider process is launched by this decision; D105 remains 14/14 unused and P5.2–P5.4 remain gated until P5.5 validation and package validation are green. **Consequences:** P5.5 may close only as `🟠 Done with deviations` after materializing the specified manifests and passing its independent validator; downstream pilot authority, scope, caps, expiry and frozen predecessor bytes are unchanged. RAG:— (owner-grounded: `brief/28-p5.5-terminalization-owner-direction-2026-08-06.md`; repo-grounded: D108–D112 and `findings/P5-business-successor.md`).

## Почему

The owner chose an explicit, traceable terminal evidence rule instead of a forbidden retry; the historical failure remains visible and the acceptance deviation cannot be mistaken for a new provider measurement.
