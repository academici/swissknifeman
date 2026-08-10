---
id: D133
date: 2026-08-06
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

New item **P5.8** consolidates the three gate defects that today are owned by NO live item, applying the settled two-sided pattern (D121/D122 rule 6, D130 ledger membership): (1) `artifacts/P5/validate-recovery-pilot.py` compares its recorded `g2b_generation_hash` with `!=` against the live manifest (line 124) and therefore can never go green after any re-freeze — repaired to ledger membership plus «ledger last entry equals live generation», with the `--ledger` argument the script does not yet have; (2) `artifacts/P4/validate-assurance.py` recomputes `g2.package_files` from the current tree and fails `G2 manifest drift` because the package legitimately advanced to G2B — repaired two-sided (frozen G2 side proven against its own snapshot, live side against the current G2B generation resolved at run time), keeping `--contracts contract-manifest-v1.json` because the P4 freeze is a six-contract fact and the v2 aggregate is P5.7's forward artifact; (3) the latent `TypeError` in `artifacts/P1/validate-economy-evidence.py:lane_units` — `duration_ms`/`turns` are summed without the `None` guard the token/cost fields have, while `economy-evidence-v2` explicitly admits a `null` metric with an `unknown_reasons` entry — repaired so an unknown propagates as unknown and blocks its branch, never as a silent `0` and never as a crash. Rejected: reopening P5.6 (its Scope Included is an exhaustive four-repair list already closed with its evidence; three more repairs is not the «exactly one repair» case `findings/P5-retry-carrier-set.md` §3 allows an item to be extended for) and reopening P5.3 (its six one-shot D105 trials are spent; returning terminal evidence to `🟡` to edit a validator buys nothing). Execution order is **P5.5 → P5.8 → P5.4**, derived not chosen: repair (1) survives only as ledger membership, and the ledger's last entry becomes the seventh freeze inside P5.5. RAG:— (repo-grounded: `findings/P5.4-forward-conformance-sweep-2026-08-06.md` §2–§3/§6 with each failing command and output, `findings/P5-paired-wave-carrier-set.md` §6, D127/D130/D131, `root/contracts/economy-evidence-v2.md` lines 119–125).

## Почему

Four red gates everyone «knows are expected» is exactly the state P5.6 existed to end; leaving two of them unowned while P5.4's pre-intent gate names one of them would put a permanent exemption inside the last gate before release.
