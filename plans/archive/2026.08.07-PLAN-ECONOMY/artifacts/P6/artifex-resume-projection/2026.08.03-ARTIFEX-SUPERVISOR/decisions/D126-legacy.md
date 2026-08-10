---
id: D126
date: 2026-08-06
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

[OWNER-SELECTION:P5.4-CLAUDE-ONLY-WAVES] Shown that the codex lane is blocked by its own bubblewrap sandbox, that the only verified path is `--dangerously-bypass-approvals-and-sandbox` (which forfeits the `network-disabled`/`SEC-WORKTREE` guarantee on a host with confirmed outbound network), and that the compensating control — an externally created network namespace — was tested first-party this pass and does not work on this kernel (`unshare -rn` → `Operation not permitted`, the same restriction that produces codex's own `bwrap: loopback: Failed RTM_NEWADDR`), the owner literally selected «Все пять волн на claude-code, codex исключён из P5.4 (реком.)» (`brief/35-…` Q4). All ten D125 rows are `claude-code`; waves 01 and 04, previously codex, keep their scenarios, file scopes and historical patches and change provider only. D126 supersedes P5.4's Implementation Rules requirement «Terminal success requires both providers» and, correspondingly, the Scope Excluded entry «single-provider waiver into terminal readiness», BOTH only for the P5.4 adjudication: provider parity remains a live, separately carried acceptance obligation proven by terminal P3.3 (provider parity/exit conformance) and P5.3 (both-provider recovery/failure evidence), and P6 continues to consume that parity evidence from its actual carriers. `G-OWNER-P5.4-SINGLE`, retired by D85, is NOT revived — it was a verdict-only gate and authorized no dispatch; D126 authorizes dispatch scope, not a waiver of any floor. **Consequences:** P5.4 stops being the carrier of provider-parity evidence and its terminal packet must say so explicitly rather than implying parity; the codex business lane remains unproven for business dispatch and P6 may not claim it as a shipped capability without its own evidence; and the sandbox/network trade-off stays undecided and open rather than being resolved by silence. RAG:✅ 2026-08-06 first-party namespace probe and the recorded codex sandbox diagnosis (`findings/P5.4-metric-surface-gap-2026-08-06.md` F11, `findings/P5-repository-pilot.md` §8); owner-grounded: `brief/35-…` Q4.

## Почему

Spending two irreplaceable one-shot grants on a lane whose blocker is an unresolved security trade-off would have bought refusals, not measurements, and dropping to N<5 would have predetermined `NO-GO` by wave count alone.
