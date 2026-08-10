# P5.1 — the additive D122 v2 replacement carrier set (2026-08-06)

**Layer:** 1 (raw, first-party repo measurement) · **Session:** claude-opus-5[1m]/high,
`/task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P5.1` · **Base tree:** `73b41188`.

Records what was minted under D121/D122, how each authorized bound was verified before the first
write, and which pre-existing defects this pass found but is not authorized to repair.

## 1. What was minted

Three replacement P5.2 identities, additive to the frozen v1 set. Not one v1 byte moved
(`git diff --exit-code` over the six v1 carrier paths is empty before the first write and after the
last; §5).

| Carrier | Path | Identity |
|:--|:--|:--|
| catalog | `artifacts/P5/trial-catalog-v2-p5.2-retry.json` | `catalog_hash` `0b1a1b313974f482f789cf0d405d07aa6d01049f0133132a2b9c5b80a827da60` |
| request | `artifacts/P5/business-grant-request-v2-p5.2-retry.json` | `request_hash` `aed83dffa0bc65e7adba0743afb239c27175c82822c07262519ab93f1bbcc0ec` |
| grants | `artifacts/P5/business-grants-v2-p5.2-retry.json` | `owner_decision: D122`, three grants |
| replay | `artifacts/P5/trial-replay-v2-p5.2-retry.jsonl` | three identities, `used_slices: 0` |
| admissions | `artifacts/P5/trial-admissions-v2/` | three files |
| index | `artifacts/P5/trial-admission-index-v2-p5.2-retry.json` | three rows |

| trial_id | provider | timeout_ms | task_hash | admission_hash |
|:--|:--|--:|:--|:--|
| `p5.2r-slice-01-worktree-core` | codex | 180000 | `e3aee8a038c0993ac1903b8e1051b90cb283c5bbce3913a6c3bb4c8a2f7d09fb` | `b865ebf8eb57bff3fa8f135fa169e89eacbea95273bc846c92ec890faeb3e722` |
| `p5.2r-slice-02-worktree-binding` | claude-code | **600000** | `521b658352964ef7299e13ffc113584ea356a5982961d00305dc5ed33e012ec3` | `09f3c54612589dbb941504283d43065a68c2289c028c03c9deb72b2d1a813e79` |
| `p5.2r-slice-03-worktree-evidence` | codex | 180000 | `d7bb636dfbdfe6db8b2265bc8b0e5fddf7b303b8ed65b7277eb91066665254ae` | `b9ddc9dd2dbae2252eb579555706ea73b4e10fa378e5f9de4d5b26ae63b87bca` |

Each admission carries `usage {used_slices: 0, max_slices: 1, reusable: false}`, `grant_id
D122:<trial_id>`, owner marker `[OWNER-GRANT:G-OWNER-P5.2-RETRY]`, expiry `2026-08-12T23:59:59Z`
(D105's own expiry, which D122 forbids extending) and the unchanged G2 predecessor pin
`ef08406d7ca630d46e9e9e8bca0d10ea73b141d984615bded75f19d7eea13f09`.

## 2. Derivation — what changed and what did not

Each v2 row is a deep copy of the v1 row it replaces, into a new object graph. Exactly four fields
differ, three of them identity:

- `trial_id` — the new D122 identity (`p5.2r-…`), so no spent v1 row is reused;
- `controlled_root` — derived by v1's own convention `mktemp:p5-p5-2-<trial_id>`; keeping the v1
  literal would collide with a spent root, and D122 states no roots of its own;
- `order` — 1–3 inside the three-row catalog;
- `budgets.timeout_ms` — `180000` → `600000` on the `claude-code` row **only** (D122).

`scenario`, `kind`, `historical_patch_sha256`, `files`, `base_commit` `bde07fb0…`, `provider`,
`route`, `capabilities`, `acceptance_refs`, `validation`, `item`, `purpose`, `repository`,
`candidate_dispatch`, `baseline_evidence_class`, `baseline_lane` and every other budget key are
byte-equal to the v1 counterpart. This is not asserted by the writer alone: the committed proof is
`validate-trial-admissions.py --owner-decision D122 --baseline-catalog <v1 catalog>`, which
re-derives the correspondence independently (§4, case P01).

Catalog top level keeps the v1 key set exactly; `counts` becomes `{candidate_dispatches: 3,
p5_2_slices: 3, p5_3_calls: 0, p5_4_battle_waves: 0}` and `historical_commits` keeps only the one
entry the three rows cite (`patch_sha256 eae2807e…`, commit `e3c932aa`). `catalog_version` /
`request_version` are `2.0.0`; `schema_version` is unchanged, so a consumer resolving a catalog by
hash parses both sets with one code path.

The admission `task` object is deliberately **unchanged in shape** — it still carries no `scenario`.
That is the D121 design: the description reaches the provider producer-side, through P5.5 resolving
the catalog whose hash the admission already pins (`task.catalog_hash` = the v2 `catalog_hash`
above), not through an admission or contract edit.

### Two verification asymmetries, disclosed

1. **D122 carries no machine-parseable fields.** D105 states its grant as `key=`value`` pairs, which
   `build-trial-admissions.py` parses and compares field-by-field against the frozen request. The
   `| D122 |` row states its bounds in prose. Every bound is therefore verified as an **exact
   literal of that row** — the owner marker, the verbatim owner answer «Поднять до 600000 ms в новых
   строках (реком.)», the brief path, `exactly three replacement P5.2 repository-slice trials`,
   `` `reusable:false` ``, `` `180000` to `600000` ``, the expiry — plus a cross-check that the
   request's caps equal **D105's own caps literal** except the one authorized `timeout_ms` raise,
   that the marker is not D105's, that there are exactly three named trial ids and the two frozen
   providers, and that no later Decision Log row revokes the request hash. What cannot be checked
   the D105 way is the catalog/request hash binding: D122 states no hashes, so that comparison is
   satisfied from the request itself. Every negative in §4 (N01–N03) exercises what remains
   enforceable.
2. **The `bcd5443f…` aggregate carrier digest has no recorded derivation.** Acceptance (b) names it,
   but no script in the repository computes it and the closing P5.1 Completion Notes cite it without
   the command that produced it (`git log --all -S` finds it only in `phases/P5.md`). Eight
   candidate constructions over every subset of the v1 carriers, in four path spellings, reproduce
   nothing. It is proven here in a strictly stronger form instead: deterministic re-generation of
   the v1 set reproduces **every v1 carrier byte** (§5), which implies any digest that is a function
   of those bytes, including this one. See §6 for the remediation this owes the record.

## 3. The rule (6) validator repair

`validate-trial-admissions.py` asserted that `packages/artifex` equals the immutable G2 digest. Since
D118/D119 deliberately moved the business-execution seam into the package, that assertion is
structurally false — before the repair the validator failed with `current G2 drift:
packages/artifex/lib/artifex/activity.py` (on `73b41188`). It now asserts the two-sided invariant the
admission contract actually names:

- the current package equals the **sole G2B digest** of `business-successor-generation-v1.json` (its
  own `generation_hash` re-verified, lineage `G2 → G2B` checked, all 50 `successor.package_files`
  rows re-hashed against the live tree);
- the manifest's `predecessor.digest` is still the immutable G2 digest, and **every** frozen task and
  grant still pins exactly that digest.

The check is neither deleted nor widened to "any digest": a package equal to neither fails, and a
frozen carrier that stops matching the predecessor fails (§4, N15–N17).

The identical broken assertion also sits in **`build-trial-admissions.py`** (`current G2 package
drift: …`), where it blocked the generator outright — acceptance (b)'s deterministic v1 re-generation
and the whole v2 mint were unreachable until it was repaired the same way. That repair is inside the
file rule (2) authorizes this pass to extend, and it is the only way the item's own Validation
command line can be green; it is recorded as a deviation from rule (6)'s single-validator wording in
the item's Known Deviations.

## 4. Negative cases — every one refuses before write

Authored before the positive path, run against the real scripts with mutated inputs in a scratch
tree (nothing written into `plans/`). 19/19 behaved as specified.

| # | Case | Enforced by | Refusal |
|:--|:--|:--|:--|
| N01 | request carries the D105 owner marker | builder | `request owner marker is not the D122 grant` |
| N02 | D105 marker substituted for D122 in `plan.md` | builder | `D122 literal unavailable: [OWNER-GRANT:G-OWNER-P5.2-RETRY]` |
| N03 | D122 owner literal missing from `plan.md` | builder | `D122 literal unavailable: «Поднять до 600000 ms…»` |
| N04 | a fourth replacement row | builder | `exactly 3 frozen trials required` |
| N05 | a spent v1 trial id reused | builder | `replacement rows outside the D122 closed set` |
| N06 | changed file scope | builder | `replacement row diverges from v1: …:files` |
| N07 | changed base commit | builder | `replacement row diverges from v1: …:base_commit` |
| N08 | a second changed budget key (`token_limit`) | builder | `budget outside the D122 grant: …:token_limit` |
| N09 | `max_slices: 2` | builder | `budget outside the D122 grant: …:max_slices` |
| N10 | changed provider | builder | `replacement row diverges from v1: …:provider` |
| N11 | `claude-code` row left at 180000 ms | builder | `budget outside the D122 grant: …:timeout_ms` |
| P00 | the legitimate v2 mint | builder | `written (3 D122-bound admissions; 0 dispatch intents)` |
| P01 | validator over the legitimate v2 set | validator | `OK (3 D122/G2-bound non-reusable admissions…)` |
| N12 | an admission with `reusable: true` (index re-hashed) | validator | `admission reuse state: p5.2r-slice-01-worktree-core` |
| N13 | v2 carriers presented where v1 is expected | validator | `D105/request mismatch` |
| N14 | v1 carriers presented as the D122 set | validator | `D122 cap outside the grant: timeout_ms` |
| N15 | current package equals **neither** G2 nor G2B | validator | `current package differs from G2B: packages/artifex/AGENTS.md` |
| N16 | G2 predecessor digest drifts from the frozen carriers | validator | `request G2 predecessor drift` |
| N17 | predecessor moved while frozen admissions keep the old pin | validator | `carrier catalog/request binding` |

Rule (6)'s third named case — **a package equal to G2B but not to G2 must PASS** — is the green run
itself: on the current tree `packages/artifex` differs from the immutable G2 bytes and equals the
G2B manifest, and both validator invocations (v1 and v2 argument sets) exit 0.

## 5. Acceptance evidence

| # | Acceptance | Result |
|:--|:--|:--|
| (a) | v1 immutability before first and after last write | `git diff --exit-code` over the six v1 paths — empty both times |
| (b) | deterministic v1 re-generation | every v1 carrier byte reproduced (`git diff --exit-code` empty after re-running the v1 command line, including the manifest index); the `bcd5443f…` literal itself has no recorded derivation (§2.2) |
| (c) | validator green on both argument sets | v1: `OK (14 D105/G2-bound …)`; v2: `OK (3 D122/G2-bound …)`, `used_slices: 0`, `600000` ms on the `claude-code` row, every other budget key byte-equal to v1 |
| (d) | independent recomputation outside the generator | `catalog_hash`, `request_hash` and all three `task_hash`/`grant_hash`/`replay_hash`/`admission_hash` plus file `sha256` — 17/17 match |
| (e) | repaired G2 check green, three named cases | see §3 and §4 (N15/N16/N17 + the green run) |
| (f) | no package mutation, no provider process, D105 unspent | `git status --porcelain -- packages/artifex` empty; **0 provider processes started** (no dispatch intent written; the only subprocesses of this pass were `python3` validators/generator, `git` and one temporary `git worktree` at `124df816`); all 14 v1 admissions still `used_slices: 0`, replay `used_slices` sum 0 |

Other item Validation commands on the current tree: historical `validate-authority-requalification.py`
passes on an isolated worktree at `124df816` (`OK (D104, 18 paths, closed semantics, P4.7/G1)`);
`validate-provenance-reconciliation.py --self-test` passes; JSON/JSONL parse, `py_compile`, privacy
scan (7 JSON docs + 3 JSONL rows, no forbidden key) and scoped `git diff --check` are green.

## 6. Pre-existing defects found and NOT repaired here (out of the reopen's scope)

All four are the same class as the one rule (6) names — frozen P1–P4 gates asserting equality against
a package/contract set that D108 and D118/D119 deliberately extended — and all four are red on
`73b41188` **before** this pass touched anything:

1. `validate-shadow.py --package packages/artifex --assurance …/P4/assurance-manifest-v1.json` →
   `FAIL: current package differs from G2`. Named in P5.1's Validation; P5.1-owned file, but the
   reopen's Scope Included enumerates exactly two work items and this is not one of them.
2. `validate-assurance.py …` → `FAIL: G2 manifest drift` (same cause, P4-owned artifact).
3. `validate-package-promotion.py --package packages/artifex` → `FAIL: current package or
   source/provenance drift` (same cause, P3-owned artifact).
4. `validate-contract-set.py --contracts root/contracts` → `FAIL: contract directory mismatch:
   ['business-dispatch-admission-v1.md']` — the frozen six-contract manifest predates D108's
   additive seventh contract.

Proposed remediation (needs a design pass, not an executor decision): one bounded fix-item that
applies the rule (6) pattern to all four — assert the live tree against the **current generation**
(G2B) while every frozen carrier keeps its G2/six-contract predecessor pin — plus recording the
derivation of the `bcd5443f…` aggregate digest or replacing it with a reproducible anchor. All four
are green-before-G3 obligations for P5.4 and none blocks P5.5 or P5.2, whose gates re-derive G2B
live.

Carried forward unchanged: `packages/artifex/scripts/validate.sh` line 7 uses `rg`, absent here, so
its plan-path guard silently no-ops while the script prints `OK`
(`findings/P5.2-task-description-gap-2026-08-06.md` F8).
