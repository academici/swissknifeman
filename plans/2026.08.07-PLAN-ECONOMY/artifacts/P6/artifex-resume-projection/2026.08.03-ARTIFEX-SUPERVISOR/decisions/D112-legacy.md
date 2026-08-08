---
id: D112
date: 2026-08-05
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

D112 supersedes D111 only for Codex R2 cap-enforcement semantics; every other D111 authority predicate remains active. Codex R2 keeps provider=`codex-cli 0.146.0`, root=`mktemp:p5-g2b-codex-r2`, exactly one of the two total R2 attempts, and the unchanged rooted security controls. Its enforceable cap-contract is exactly: `single fresh exec invocation`; Artifex process wrapper `hard_timeout_ms=120000`, aggregate output `<=8192` bytes and parsed events `<=16`; fixed experimental `rollout_budget` token limit `2000` only if strict-config proof is required; no Codex CLI claim for `max_turns` or money cap; instead `automatic_retry=false` plus minimal measured post-run usage evidence. JSON-Schema self-test and projection/complete-argv fake-binary preflight must prove `process_count=0` before either R2 attempt. Claude Code `2.1.222` D111 controls/caps remain unchanged. Exactly two R2 attempts remain authorized, one per provider; all 14 D105 usage rows remain 0; P5.2–P5.4 remain forbidden; no retry/fallback/R3; P4/G2/P5.1, schema scope, provider versions, roots and D105 expiry/budget remain unchanged. D112 restores P5.5 execution DoR under this corrected contract, so P5.5 remains `🟡 In progress`; any failed preflight or started-attempt refusal leaves it blocked without another provider call. **Consequences:** the Codex R2 executor loses the unproven `max_turns`/money CLI assertions from D111 and must rely on Artifex hard wrapper bounds, a conditional strict-config-proven `rollout_budget`, no automatic retry and minimized measured usage; no attempt, authority or security boundary is widened. RAG:— (direct repository-owner refinement in `brief/27-p5.5-codex-r2-cap-contract-owner-refinement.md`; repo-grounded D108–D111 carriers and `findings/P5.5-probe-recovery-verification-2026-08-05.md`).

## Почему

The owner authorized the narrow cap-contract replacement so the final Codex canary is bounded by controls the executor can actually prove instead of false CLI flags, while all finite R2 and business-safety gates stay intact.
