---
id: D125
date: 2026-08-06
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

[OWNER-GRANT:G-OWNER-P5.4-PAIRED-WAVES] branch=`p5-paired-battle-waves`; consumer=`P5.1 mints, P5.4 spends`; providers=`claude-code` only (`Claude Code 2.1.222`, honored through `SKM_CLAUDE_BIN` per D120); maximum_dispatch_count=`10` — five `candidate` rows and five `baseline` rows, one dispatch each, `max_slices:1`, `reusable:false`, no retry of a started attempt; trial_ids=`p5.4w-wave-0{1..5}-*` (candidate) and `p5.4b-wave-0{1..5}-*` (baseline), each baseline row copying its candidate twin's scenario, kind, `historical_patch_sha256`, files, `base_commit`, route, capabilities, `acceptance_refs`, `validation` and budgets VERBATIM and differing only in `trial_id`, `controlled_root`, `lane` and `order`; controlled_roots=`mktemp:p5-p5-4-<trial_id>` for all ten; per_trial_caps=`max_slices:1, timeout_ms:900000, max_envelope_bytes:65536, max_event_count:512, max_turns:40, max_output_bytes:65536, token_limit:200000, cost_limit_microunits:5000000`; expiry=`2026-09-30T23:59:59Z`; revoked=`false`; owner-message=`brief/35-p5.4-economic-adjudication-owner-decisions-2026-08-06.md` Q3. The owner literally selected «Поднять до max_turns 40 / timeout 900000 ms / token_limit 200000 (реком.)», whose option text also named `max_output_bytes` 16384→65536 and `max_event_count` 64→512; `max_slices`, `max_envelope_bytes` and `cost_limit_microunits` are byte-equal to D105 and were not raised. Two parameters are composed by this design pass from the selected option's own shape, exactly as D105 was composed from `brief/22` and D122 from `brief/34`, and are auditable against `brief/35-…`: the expiry `2026-09-30T23:59:59Z` (the remediation chain contains a frozen-contract freeze and two producer reopens, so binding this grant to D105's `2026-08-12` clock would guarantee forfeiture before the first dispatch) and the ten trial IDs/roots. Carriers are minted by P5.1 as an ADDITIVE v3 set with its own catalog/request/grants/replay/admissions/index and its own `catalog_hash`; not one v1 or v2 byte moves. **Consequences:** the five unused `p5.4-wave-*` D105 rows are written off explicitly — they are never re-minted, reset or reused, they keep `used_slices: 0`, and they will simply expire unspent on `2026-08-12T23:59:59Z` together with the other six unused D105 rows; D105's 14-row ceiling and expiry are NOT extended by this grant; and the raised caps apply only to these ten rows, creating no precedent for any other item. RAG:— (owner-grounded: `brief/35-…` Q3 literal answer; repo-grounded: D105/D122 carrier shape, `artifacts/P5/trial-catalog-v1.json` P5.4 rows, `findings/P5-repository-pilot.md` §8 measured turn exhaustion).

## Почему

The frozen budgets were empirically disproven — a real editing dispatch exhausted 8 turns on three files and an earlier one hit the 180 000 ms wall — so dispatching ten irreversible one-shot grants under them would have measured the budget rather than the candidate; a single new grant of the same shape as D122 raises exactly the caps that bound and nothing else.
