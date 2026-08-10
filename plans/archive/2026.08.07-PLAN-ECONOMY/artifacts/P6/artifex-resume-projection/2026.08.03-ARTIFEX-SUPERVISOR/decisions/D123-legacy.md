---
id: D123
date: 2026-08-06
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

[OWNER-SELECTION:P5.4-ECONOMIC-ADJUDICATION] Shown two facts verified first-party this pass — (a) the candidate lane writes provider usage as BOOLEANS (`usage_observed`/`cost_observed` in `providers/{codex,claude_code}.py`), not one integer, so no `economy-evidence-v1` metric field is ever populated; (b) no single provider exports all seven `metric_fields`: claude-code does not report `reasoning_tokens` separately (they are definitionally inside `output_tokens`) and codex reports no cost at all, while price lookup/imputation is forbidden by D25 and P5.4's own Scope Excluded — the owner literally selected «single-provider claude-code + economy-evidence-v2 (реком.)» (`brief/35-p5.4-economic-adjudication-owner-decisions-2026-08-06.md` Q1). The terminal economic adjudication therefore runs in `provider_scope.mode = single-provider` on `claude-code`, which `economy-evidence-v1` itself permits only «with a non-empty prior Owner D# reference» — D123 is that reference — and P1's frozen contract set is unfrozen for exactly one additive successor, `root/contracts/economy-evidence-v2.md`, carrying exactly three rule changes and no new field, formula, threshold, verdict or relaxed floor: (1) provider-structural inclusion (a field the provider does not report separately because it is definitionally contained in another reported field is a MEASURED `0` with a mandatory `inclusion_basis`; instantiated exactly once, for claude-code `reasoning_tokens` ⊂ `output_tokens`), (2) structural coordinator zero (an envelope of a component that makes no model call is a measured all-zero envelope with a mandatory `zero_basis` file reference — Artifex's coordinator is deterministic by D3), (3) single-provider economic scope never reported as parity. D123 supersedes D14 ONLY in that its `GO` may now rest on a single-provider economic lane; every D14 threshold (`<25%`, `≥2×`, `N=5`, «unknown measurement запрещает GO») is unchanged, and D25's ban on imputing a missing metric stands — rules (1)/(2) are measured values with a named basis, not imputations. **Consequences:** `economy-evidence-v1` stops being the adjudication contract for P5.4 and P6 (it stays frozen and archived as the predecessor, unedited); P1's six-contract aggregate freeze is re-cut as an eight-contract v2 manifest; the plan can no longer claim provider parity from its economic verdict; and codex, having no cost surface that rule (1) can rescue, is structurally outside the economic lane. RAG:✅ 2026-08-06 provider usage-surface verification (`findings/P5.4-metric-surface-gap-2026-08-06.md` F10, `perplexity-web` + first-party `.claude/runs/*.json`); owner-grounded: `brief/35-…` Q1; repo-grounded: `findings/P5.4-metric-surface-gap-2026-08-06.md` F9, `root/contracts/economy-evidence-v1.md`.

## Почему

A frozen field list that no available provider can fill makes `GO` unreachable by construction; the owner chose to fix the contract's unknown rules honestly on the one lane that can supply real integers, rather than to fabricate numbers or to quietly drop the economic claim the brief asks for.
