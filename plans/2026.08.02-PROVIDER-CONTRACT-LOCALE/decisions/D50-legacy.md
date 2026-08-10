---
id: D50
date: 2026-08-03
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

P4.3–P4.6 source checkpoints use one machine state, `deferred-derived-only`, only when the checkpoint verifier recomputes an exact ordered set of stable `DERIVED_TARGET_STALE` rows (`cwd`, command ID, target path and owning generator), proves zero non-freshness failures and binds the set to the cumulative ledger/resume cursor. P4.6 terminal regeneration consumes that exact union; its frozen helper plan records its canonical payload hash and the Harness writable targets in alphabetic `target_path` order, and Harness `apply` receives them byte-for-byte through `--authorize`. After regeneration every package/docs command must return 0, the deferred set must be empty and a second owner run must be byte-stable. RAG:— (repo-grounded: audit F19/F20, `packages/harness/lib/harness/instructions.py:512-535`, `roadmap.md` checkpoint carrier and plan-protocol derived-artifact coherence).

## Почему

Gives expected generated drift one reproducible checkpoint/resume representation without greenwashing unrelated validation failures; exact positional authorization preserves the Harness write boundary and the terminal all-green gate.
