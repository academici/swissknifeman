# P5.1 — the additive D125 v3 paired-wave carrier set (2026-08-06)

**Layer:** 1 (raw, first-party repo measurement) · **Session:** claude-opus-5[1m]/high,
`/task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P5.1` · **Base tree:** `46442303`.

Records what was minted under D125/D127 (the third and by design final P5.1 reopen), how each
authorized bound was verified before the first write, where the item's own spec text is internally
inconsistent and how that was resolved, and which pre-existing defect this pass found but is not
authorized to repair.

## 1. What was minted

Ten paired P5.4 identities — five `candidate` and five `baseline` — additive to the frozen v1 and
v2 sets. Not one v1 or v2 byte moved (`git diff --exit-code` over every v1 and v2 carrier path is
empty before the first write and after the last; §6).

| Carrier | Path | Identity |
|:--|:--|:--|
| catalog | `artifacts/P5/trial-catalog-v3-p5.4-paired.json` | `catalog_hash` `91c7fc0f6df4da127141781c6ed4c89eec21d108d52f532f58791c9be4d45858` |
| request | `artifacts/P5/business-grant-request-v3-p5.4-paired.json` | `request_hash` `47f0a7408efb19b073e27933e7e68f91ca604eeaf723821661543301fc6bd70d` |
| grants | `artifacts/P5/business-grants-v3-p5.4-paired.json` | `owner_decision: D125`, ten grants |
| replay | `artifacts/P5/trial-replay-v3-p5.4-paired.jsonl` | ten identities, `used_slices: 0` |
| admissions | `artifacts/P5/trial-admissions-v3/` | ten files |
| index | `artifacts/P5/trial-admission-index-v3-p5.4-paired.json` | ten rows |

| trial_id | lane | pair_id | base | files | task_hash | admission_hash |
|:--|:--|:--|:--|--:|:--|:--|
| `p5.4w-wave-01-recovery-fixture` | candidate | `wave-01-recovery-fixture` | `618adbea` | 1 | `3bc984fe7b920d77b86298d0a952d425d85e1b899cfee600f3344474262c878b` | `98748df8ec07bae205a0e7ca37109c8c87634ffc5d156a9f8abffcf52f1d9a88` |
| `p5.4b-wave-01-recovery-fixture` | baseline | `wave-01-recovery-fixture` | `618adbea` | 1 | `9b832ca818d08e64f29290e43ce58dba9e2f0fea9b1ac91dfe0a2895a2a33dfe` | `07c5b3b133db84811ce806fadcfd7f03a133850e4d1d231d9ee3c92bdd60ea3c` |
| `p5.4w-wave-02-worktree-isolation` | candidate | `wave-02-worktree-isolation` | `bde07fb0` | 8 | `ecbbd4e7365fe3cf1497630f83b76ec0ad45ece06057eeb0d65a8c3c41b71c13` | `edebba313950f77bb256d8c904a7aa2ad2dd147ff9c7ae8cf8b658ff45248b81` |
| `p5.4b-wave-02-worktree-isolation` | baseline | `wave-02-worktree-isolation` | `bde07fb0` | 8 | `a9a76685a2db94ef76cca52639904d24d6acccfc0d388454c5b4b750eb405a55` | `253da36749e85612cca252e9c6064c3a0048ec5afb7c9d5fbf6a7d6c5da3f70a` |
| `p5.4w-wave-03-security-boundary` | candidate | `wave-03-security-boundary` | `56c4c1bc` | 7 | `2baa6e65462c445248fa6c55cb8d46c83c510026e80437822a847379a13a937a` | `c6a2cd07b6cda55d65bd57d7a8a4d98a673cea33ff586d71519943f8404d8fdc` |
| `p5.4b-wave-03-security-boundary` | baseline | `wave-03-security-boundary` | `56c4c1bc` | 7 | `12440b20bcb5a0cba895199064f1869b83ff2791f8140d81955e1e8ba36b2f90` | `07709b27d7297398ac2d2a19c4464652f064ced0ca5a5489a857ec18913716f0` |
| `p5.4w-wave-04-telemetry-assurance` | candidate | `wave-04-telemetry-assurance` | `17a57adc` | 18 | `81c54f8e418dcb550b825d55bc905338824ef8e698c23f5b89d122acf79582fa` | `5177eb8b1a15242bf7020c8f757a4fd424971c70011a0f1d869bcef9b2ed7409` |
| `p5.4b-wave-04-telemetry-assurance` | baseline | `wave-04-telemetry-assurance` | `17a57adc` | 18 | `655a8047710aa684644ae4f60377cbe05a9a471261bf3a26b10cabe2eb397563` | `1c0ba11a9b33e287c0909811264d93c1cb09ab441cb515cbac09adbe82a6d4a6` |
| `p5.4w-wave-05-committed-gates` | candidate | `wave-05-committed-gates` | `bd861202` | 5 | `242cacbe029367ecea449f22c299363bfaad165abce5cc027765ef27615497a2` | `81453915338062b75055c7b1fd937cd7a04c517755d531a3413cb9b2b0f6245e` |
| `p5.4b-wave-05-committed-gates` | baseline | `wave-05-committed-gates` | `bd861202` | 5 | `dd431fd91438582a5d64cbf6f3f3013cb0a278abb437a413985524bb0ec718c3` | `acb96a3e7c894a53a6c91ab1e141fbed6cf48bee7d0a2b6e9fa89c611d38031f` |

Every row is `claude-code` (D126), carries `usage {used_slices: 0, max_slices: 1, reusable: false}`,
`grant_id D125:<trial_id>`, owner marker `[OWNER-GRANT:G-OWNER-P5.4-PAIRED-WAVES]`, branch
`p5-paired-battle-waves`, expiry `2026-09-30T23:59:59Z` and the unchanged immutable G2 predecessor
pin `ef08406d7ca630d46e9e9e8bca0d10ea73b141d984615bded75f19d7eea13f09`. All eight D125 budget values
are identical on all ten rows: `max_slices 1`, `timeout_ms 900000`, `max_envelope_bytes 65536`,
`max_event_count 512`, `max_turns 40`, `max_output_bytes 65536`, `token_limit 200000`,
`cost_limit_microunits 5000000`.

## 2. Derivation — what changed and what did not

Each **candidate** row is a deep copy of its frozen v1 `p5.4-wave-0N-*` row into a new object graph.
Each **baseline** row is a deep copy of its candidate twin inside the same object graph (D125/D127
rule 4 — never a second read of the historical patch or the current tree).

Candidate vs its frozen v1 source — six differences and three new keys:

- `trial_id` — the new D125 identity (`p5.4w-…`), so no frozen v1 row is reused;
- `controlled_root` — D125's own template `mktemp:p5-p5-4-<trial_id>`;
- `order` — 1–10 inside the ten-row catalog, interleaved so each pair is adjacent (candidate `2N-1`,
  baseline `2N`), which is also the dispatch order P5.4 inherits: running a pair back-to-back keeps
  the comparison as close in time as the carrier can make it;
- `provider` — forced to `claude-code` on every row (D126); waves 01 and 04 were `codex` in v1;
- `baseline_lane` — the retired `live-manual`/`live-harness-run`/`live-workflow` vocabulary replaced
  by the single value `live-direct-provider` (D124);
- `budgets` — exactly the five raised keys (`max_turns` 8→40, `timeout_ms` 180000→900000,
  `token_limit` 8000→200000, `max_output_bytes` 16384→65536, `max_event_count` 64→512); the other
  three are byte-equal to v1 **and** to D125's caps;
- new keys `lane` (`candidate`|`baseline`), `pair_id` (the shared wave slug) and `paired_trial_id`
  (the twin's `trial_id`).

`scenario`, `kind`, `historical_patch_sha256`, `files`, `base_commit`, `route`, `capabilities`,
`acceptance_refs`, `validation`, `item`, `purpose`, `repository`, `candidate_dispatch` and
`baseline_evidence_class` are byte-equal to the v1 counterpart on all ten rows — proven
independently of the writer (§4 case P01, §5).

Catalog top level keeps the v1 key set exactly; `catalog_version`/`request_version` are `3.0.0`;
`counts` becomes `{candidate_dispatches: 10, p5_2_slices: 0, p5_3_calls: 0, p5_4_battle_waves: 10}`
— both numbers count catalog ROWS (all ten carry `kind: "battle-wave"`, copied verbatim), and the
five *waves* of D14's `N=5` are the five distinct `pair_id` values, not these counters.
`historical_commits` is copied verbatim: all five entries are cited by the ten rows.
`contract_sha256` is likewise byte-equal to v1 — it is the catalog-time binding to the six contracts
frozen when the trials were frozen, and nothing in this reopen's exhaustive Scope authorizes
re-cutting it; the contract set the ECONOMIC verdict is adjudicated against is named by the
evidence document's own `contract_set_hash`, which P5.4 produces against
`artifacts/P1/contract-manifest-v2.json` (P5.7).

`candidate_dispatch` stays `true` on baseline rows: D125 fixes the pair to differ in its identity
fields only, and the `lane` key is the field that carries the candidate/baseline distinction. Read
it as "this row is one of the ten authorized dispatches", not as "this row runs the candidate".

### Two spec-text inconsistencies, disclosed and resolved toward the artifact spec

1. **The `base_commit` literal.** Scope Included says each pair shares «`base_commit`
   `618adbeafb428f259e4c83c79759fcf5dbfdd08b`» while in the same sentence requiring every copied
   field to be taken VERBATIM from the corresponding frozen v1 row, and acceptance (j) requires
   byte-equality with that counterpart on `base_commit`. The five v1 waves have five DIFFERENT
   bases (`618adbea`, `bde07fb0`, `56c4c1bc`, `17a57adc`, `bd861202`); `618adbea` is wave 01's
   alone. Each row therefore carries its own v1 base — the reading the governing rule and the
   acceptance both enforce, and the only coherent one, since a historical patch applies at its own
   base.
2. **The fifth name in the pair-diff list.** Implementation rule (4) and acceptance (j) say the
   twins differ in exactly `trial_id`, `controlled_root`, `order`, `lane` and `pair_id`, while
   Scope Included defines `pair_id` as «the shared wave slug» and separately requires that each
   candidate row «names its baseline twin's `trial_id` and vice versa». A field cannot be both
   shared and differing. The artifact follows Scope Included: `pair_id` is shared and identical
   within a pair, and the twin pointer is the separate key `paired_trial_id`, which is what
   necessarily differs. The pair diff is therefore proven over
   `{trial_id, controlled_root, order, lane, paired_trial_id}` — same cardinality, fifth name
   corrected — plus an explicit proof that `pair_id` IS equal within each pair and unique across
   the five. Both scripts encode exactly this (`PAIRED_TWIN_DIFF_FIELDS`).

## 3. Grant verification — D125 is machine-readable where D122 was not

Unlike the `| D122 |` row, the `| D125 |` row states its grant in `key=`value`` fields, so each is
read and compared to a frozen literal rather than pattern-matched as prose. It does interleave prose
BETWEEN its fields, so D105's two-field anchor regex (`name=`value`; next_name=`) cannot cross it;
each field is captured on its own instead (`capture_field`). Verified before any write:

| Bound | Source literal | Checked against |
|:--|:--|:--|
| owner marker | `[OWNER-GRANT:G-OWNER-P5.4-PAIRED-WAVES]` | request `owner_marker`, every grant, and the absence of the D105/D122 markers from the row |
| `branch` | `p5-paired-battle-waves` | every grant's `branch` |
| `providers` | `claude-code` | request `providers`, every row's `provider` |
| `maximum_dispatch_count` | `10` | request count and the ten-row closed set |
| `trial_ids` | `p5.4w-wave-0{1..5}-*` / `p5.4b-wave-0{1..5}-*` | the exact ten ids derived from the five frozen v1 wave slugs |
| `controlled_roots` | `mktemp:p5-p5-4-<trial_id>` | every row's `controlled_root`, expanded per id |
| `per_trial_caps` | the eight `key:value` pairs | request caps and every row's budgets, key by key |
| `expiry` | `2026-09-30T23:59:59Z` | every grant's `expiry`, plus a not-yet-expired check |
| `revoked` | `false` | plus a scan for any later `D#` row naming this `request_hash` with `revoked=`true`` |
| `owner-message` | `brief/35-…-2026-08-06.md` | exact literal |
| owner answer | «Поднять до max_turns 40 / timeout 900000 ms / token_limit 200000 (реком.)» | exact literal |
| `max_slices`/`reusable` | `` `max_slices:1`, `reusable:false` `` | exact literal, plus every admission's `usage` |

The five raised budgets are proven against their own baseline, not merely against the cap: each
raised key must have held the exact frozen v1 value (`8`/`180000`/`8000`/`16384`/`64`) AND now hold
D125's value. A row whose v1 base was something else refuses, so the raise cannot silently move a
base as well as a ceiling.

## 4. Negative cases — every one refuses before write

Authored before the positive path, pairing invariants first, run against the REAL scripts inside a
scratch mirror of the repository (plan + artifacts copied, `packages/` symlinked); nothing was
written into `plans/` by any of them. **22/22 behaved as specified.**

| # | Case | Enforced by | Refusal |
|:--|:--|:--|:--|
| N01 | baseline `files` differ from its twin by one path | builder | `paired row diverges from v1: p5.4b-wave-02-worktree-isolation:files` |
| N02 | baseline `base_commit` differs from its twin | builder | `paired row diverges from v1: …:base_commit` |
| N03 | baseline `route` differs from its twin | builder | `paired row diverges from v1: …:route` |
| N04 | one budget key differs between twins | builder | `budget raise outside the D125 grant: …:max_turns` |
| N05 | pair pointer names a nonexistent twin | builder | `paired twin unresolved: p5.4w-wave-05-committed-gates` |
| N06 | two candidate rows claim the same baseline | builder | `paired twin unresolved: p5.4w-wave-02-worktree-isolation` |
| N07 | candidate file scope drifts from its frozen v1 row | builder | `paired row diverges from v1: …:files` |
| N08 | D105 marker substituted for D125 | builder | `request owner marker is not the D125 grant` |
| N09 | D122 marker substituted for D125 | builder | `request owner marker is not the D125 grant` |
| N10 | `max_slices: 2` | builder | `budget outside the D125 grant: …:max_slices` |
| N11 | an eleventh row | builder | `paired rows outside the D125 closed set` |
| N12 | a `codex` row (D126) | builder | `D125 authorizes claude-code only: …` |
| N13 | a frozen v1 trial id reused | builder | `paired rows outside the D125 closed set` |
| N14 | `timeout_ms` raised beyond the D125 cap | builder | `budget raise outside the D125 grant: …:timeout_ms` |
| N15 | the `\| D125 \|` row absent from `plan.md` | builder | `exact D125 owner grant row unavailable` |
| P00 | the legitimate v3 mint | builder | `written (10 D125-bound admissions; 0 dispatch intents)` |
| P01 | validator over the legitimate v3 set | validator | `OK (10 D125/G2-bound non-reusable admissions…)` |
| N16 | v3 carriers presented where v1 is expected | validator | `D105/request mismatch` |
| N17 | v3 carriers presented where v2 is expected | validator | `D122 cap outside the grant: max_event_count` |
| N18 | v1 carriers presented as the D125 set | validator | `D125 caps outside the grant` |
| N19 | v2 carriers presented as the D125 set | validator | `D125 caps outside the grant` |
| N20 | an admission with `reusable: true` (index re-hashed) | validator | `admission reuse state: p5.4w-wave-01-recovery-fixture` |

N06 refuses at the builder as an unresolved twin because the builder DERIVES the expected twin id
from the wave slug and never trusts the row's own pointer; the validator resolves the pointer from
the rows instead and carries a separate duplicate-claim refusal for the same case, so the invariant
is enforced two different ways rather than once twice.

## 5. Acceptance evidence

| # | Acceptance | Result |
|:--|:--|:--|
| (g) | v1 AND v2 immutability before first and after last write | `git diff --exit-code` over all thirteen v1/v2 carrier paths — empty both times |
| (h) | deterministic re-generation of the v1 and v2 sets | both re-generated into a scratch tree and compared byte-for-byte: 14 + 3 admission files identical (`diff -r`), and `business-grants`/`trial-replay`/`trial-dispatch-manifest-index`/`trial-admission-index` of each set identical (`cmp`) |
| (i) | validator green on all three argument sets | v1: `OK (14 D105/G2-bound …)`; v2: `OK (3 D122/G2-bound …)`; v3: `OK (10 D125/G2-bound …)` — ten `used_slices: 0`, every row `claude-code`, expiry `2026-09-30T23:59:59Z`, exactly D125's eight budget values |
| (j) | programmatic pair diff + v1 byte-equality | five pairs, each differing in exactly `{trial_id, controlled_root, order, lane, paired_trial_id}` (see §2 note 2), `pair_id` shared and twins naming each other; each of the ten rows byte-equal to its frozen v1 counterpart on all nine named fields |
| (k) | independent recomputation outside the generator | 78/78 match — `catalog_hash`, `request_hash`, the request/catalog binding, and per row `task_hash`/`grant_hash`/`replay_hash`/`admission_hash`/file `sha256` cross-checked against the index, plus the twenty pairing/v1 assertions |
| (l) | no package mutation, no provider process, D105 unspent | `git status --porcelain -- packages/artifex` empty; **0 provider processes started** (the only subprocesses of this pass were `python3` scripts, `git`, and one temporary `git worktree` at `124df816`, removed afterwards); all 14 D105 admissions still `used_slices: 0`, the five `p5.4-wave-*` rows untouched, v3 replay `used_slices` sum 0 |

Other item Validation commands on the current tree: historical
`validate-authority-requalification.py` passes on an isolated worktree at `124df816`
(`OK (D104, 18 paths, closed semantics, P4.7/G1)`); `validate-provenance-reconciliation.py
--self-test` passes; `validate-shadow.py --package packages/artifex --assurance …` passes
(`9 archive files; 135 transition cells; 31 bank cases; 14 frozen dispatches; 0 provider calls` —
so the `df5d7545…`/`ec16d0c5…` checkpoint hashes are preserved); `validate-package-promotion.py`
passes; `validate-contract-set.py --manifest contract-manifest-v2.json` passes
(`8 contracts, 7 live and 1 superseded`); `validate-security.py` and `validate-hook-integrity.py`
pass; `git diff --exit-code 3533234c -- phases/P4.md artifacts/P4` is clean (the P5.6/D131 anchor);
JSON/JSONL parse, `py_compile`, privacy scan (14 JSON docs + 10 JSONL rows, no forbidden key) and
scoped `git diff --check` are green.

## 6. Pre-existing defect found and NOT repaired here (out of the reopen's scope)

`validate-assurance.py` is **red** on the current tree and named in this item's own Validation:

```
$ python3 …/artifacts/P4/validate-assurance.py --manifest …/P4/assurance-manifest-v1.json … \
    --contracts …/P1/contract-manifest-v1.json …
P4 assurance validator: FAIL: G2 manifest drift
```

Same class and same cause as the four gates `findings/P5-retry-carrier-set.md` §6 recorded: a
frozen P1–P4 gate asserting equality against a package/contract set that D108 and D118/D119
deliberately extended. Three of those four are now green — P5.6 repaired `validate-shadow.py`,
`validate-package-promotion.py` and `validate-repository-pilot.py`, P5.7 repaired
`validate-contract-set.py` — but **`validate-assurance.py` was substituted out of that remediation
set** (P5.1's own Pending Work lists P5.6 as owning `validate-shadow.py`,
`validate-package-promotion.py` and `validate-repository-pilot.py`, i.e. the third slot changed
hands), so today it is owned by no item. It is red for reasons entirely outside this reopen's
exhaustive Scope Included — this pass wrote no P4 byte, no package byte and no contract byte — and
it is a green-before-G3 obligation for P5.4.

Proposed remediation (a design decision, not an executor's): assign it to a P5.6-style forward
repair that applies the same generation-aware pattern already proven three times — assert the live
tree against the CURRENT G2B generation while every frozen carrier keeps its G2/six-contract
predecessor pin — and, in the same pass, either point its `--contracts` argument at
`contract-manifest-v2.json` or record why the v1 six-contract manifest stays its input.

Carried forward unchanged: the `bcd5443f…` aggregate carrier digest still has no recorded
derivation (`findings/P5-retry-carrier-set.md` §2.2); and `packages/artifex/scripts/validate.sh`
line 7 uses `rg`, absent here, so its plan-path guard silently no-ops while the script prints `OK`.
