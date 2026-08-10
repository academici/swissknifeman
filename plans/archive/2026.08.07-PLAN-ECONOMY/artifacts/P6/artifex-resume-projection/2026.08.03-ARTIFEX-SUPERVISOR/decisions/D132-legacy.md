---
id: D132
date: 2026-08-06
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

P5.5 reopens a FOURTH time as the sole package producer (D119) to register the authority the owner already granted in D125: `business_dispatch.GRANT_BATCHES` gains a `D125` row (marker `[OWNER-GRANT:G-OWNER-P5.4-PAIRED-WAVES]`, `trial-admission-index-v3-p5.4-paired.json`, `trial-catalog-v3-p5.4-paired.json`, `expected_count` 10), and — the design decision `brief/37` §5 delegated to this pass — the `branch` literal MOVES INSIDE the batch row (`load_indexed:118` reads the selected batch's own `branch` instead of the hardcoded `p5-business-trials`), so batch identity has exactly one carrier. The alternative selected AGAINST is a data-driven batch table read from a plan-local manifest: it would move the authorized-batch set out of reviewed code into a file written by the same layer that mints the carriers (an authority-semantics change, i.e. an owner gate, not a designer's constructive decision under `brief/36`), and it would pay a contract-sized cost now for a benefit that arrives only at a NEXT grant — while D125 is by construction this plan's last grant (P6 dispatches nothing), which `root.speculative-work` forbids. The registration commit carries the seventh G2B re-freeze and its ledger entry, exactly as the D122 registration did (`6755be6b`, ledger `7a44f9bc…`). **Consequences:** D127's «third and by design final reopen» wording for P5.5 no longer holds — this is the fourth, and the claim was falsified by the same class it was written under; P5.5 loses `🟠` terminality again; the seventh G2B freeze invalidates any literal generation pin laid before it, which is why D133's gate repairs are ordered after it; and the two grant batches that today share one branch literal stop sharing it, so a branch swapped between D105 and D122 rows — undetectable until now — refuses. RAG:— (repo-grounded: `findings/P5.4-package-authority-gap-2026-08-06.md` §3–§4 and its two-change 10/10 proof, `findings/P5.4-forward-conformance-sweep-2026-08-06.md` §1, `research/41-p5.4-package-authority-remediation.md` §2, `packages/artifex/lib/artifex/business_dispatch.py:31-38,84,117-118`, `activity.py:148`; owner-grounded: D125, `brief/37` §5).

## Почему

The owner granted the authority and P5.1 minted its carriers, but the seam that must spend them was never taught the grant — the missing work is producer-side registration, not a design question; and moving the branch into the row closes the second half of the same class instead of leaving it for the next grant to rediscover.
