---
id: D124
date: 2026-08-06
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

[OWNER-SELECTION:P5.4-BASELINE-LANE] Shown that no incumbent lane exists — all four `artifacts/P0/baseline-catalog.json` rows carry `eligible_for_battle_wave: false`, the only `eligible_for_matching` row is `classification: synthetic` with four null token fields, and P5.4 declares no producer, harness or `Files` entry for a live comparator — the owner literally selected «Прямой headless-вызов провайдера тем же скриптом (реком.)» (`brief/35-…` Q2). The `baseline` lane is henceforth defined as: the SAME slice, base commit, acceptance refs, validation set, provider, model class, effort and budget envelope as its paired candidate wave, executed as ONE headless single-shot provider invocation WITHOUT the supervisor, launched by a plan-local runner that itself performs no model call — so the baseline `coordinator` envelope is a structural zero under D123 rule (2) and the `worker` envelope is extracted by the SAME code path as the candidate's. The catalog's `baseline_lane` vocabulary `live-manual`/`live-harness-run`/`live-workflow` is retired for P5.4 rows and replaced by the single value `live-direct-provider`; `baseline_evidence_class: live-paired` is unchanged and is now satisfiable. D14 branch 2 (matched Workflow) is NOT pursued: the owner did not select it and no carrier exports a Workflow coordinator envelope per attempt, so it stays `BRANCH2_UNKNOWN` and disables only itself. **Consequences:** the measured claim narrows honestly to worker-vs-worker with a provable coordinator zero on both sides — this design can no longer claim a coordinator-context saving it does not measure (which D7 already forbade calling a saving); P0's baseline catalog is superseded as P5.4's comparator source without being edited (its rows stay exactly as frozen, and the `synthetic` row remains inadmissible); and the wave count doubles from five dispatches to ten. RAG:— (owner-grounded: `brief/35-…` Q2; repo-grounded: `artifacts/P0/baseline-catalog.json`, `root/contracts/economy-evidence-v1.md` lane/match rules, `research/39-p5.4-forward-topology.md` §2).

## Почему

An incumbent lane that a human drives cannot export a coordinator envelope the executor can observe, so it could never satisfy the contract; making the incumbent a scripted headless call of the same provider on the same slice is the only comparator this repository can actually measure, and it is exactly the question the owner asked — supervisor versus doing it directly.
