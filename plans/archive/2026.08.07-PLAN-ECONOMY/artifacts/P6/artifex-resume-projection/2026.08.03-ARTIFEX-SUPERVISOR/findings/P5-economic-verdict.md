# P5.4 — five paired battle waves, measured; independent verdict `NO-GO` (2026-08-07)

**Session:** claude-opus-5[1m]/high, `/task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P5.4` (D18 mode).
**Base tree:** `HEAD` = `9005fa92` (P5.8 terminal). **Ten provider processes started; ten D125
admissions spent; zero D105/D122 rows touched; `packages/artifex` untouched by a byte.**

This is the first pass of this item that reached dispatch. Both prior passes stopped before intent
(`findings/P5.4-preflight-blockers-2026-08-06.md`, `findings/P5.4-package-authority-gap-2026-08-06.md`).
The verdict below is `NO-GO`: it keeps P5.4 and the plan non-terminal and names the exact failed
floors, per the item's own rule and `plan.md` §2.

## 1. Pre-intent gate — fifteen of fifteen green, on this item's own start tree

Every check named in the item's Implementation Rules was re-run here, not inherited from
`findings/P5.8-unowned-gate-repair.md`'s record (the tree could have moved between P5.8's close and
this start; it had not).

| # | Check | Owner | Result |
|:--|:--|:--|:--|
| a | `validate-shadow.py --package packages/artifex --assurance …/P4/assurance-manifest-v1.json` | P5.6 | **OK** exit 0 — `9 archive files; 135 transition cells; 31 bank cases; 14 frozen dispatches; 0 provider calls` |
| b | `validate-package-promotion.py …` | P5.6 | **OK** exit 0 — `package promotion validator: OK` |
| c | `validate-repository-pilot.py` | P5.6/D130 | **OK** exit **2** — `not accepted: […] (0/3 accepted) — honest report, not a validator defect` (exit 2 is this gate's green) |
| d | `validate-contract-set.py --manifest …/contract-manifest-v2.json` | P5.7 | **OK** exit 0 — `8 contracts, 7 live and 1 superseded; 22 logical enums with one live owner each; acyclic; hashes resolved` |
| e | `validate-economy-evidence.py --contract-version 2.0.0 …` | P5.7 | **OK** exit 0 — `20 v2 cases; rules 1/2/3 closed and both directions enforced; 20 v1 cases re-run under v2 with unchanged verdicts` |
| f1 | `validate-trial-admissions.py` (v1/D105) | P5.1 | **OK** exit 0 — `14 D105/G2-bound non-reusable admissions; P3 smoke refused pre-intent` |
| f2 | same, `--owner-decision D122 --expected-count 3` | P5.1 | **OK** exit 0 — `3 D122/G2-bound non-reusable admissions; …` |
| f3 | same, `--owner-decision D125 --expected-count 10` | P5.1 | **OK** exit 0 — `10 D125/G2-bound non-reusable admissions; …` |
| g | `validate-business-successor.py …` | P5.5 | **OK** exit 0 — `G2→G2B; 14/14 D105 rows unused; 2 non-business probes` |
| h | `validate-recovery-pilot.py --ledger …` | P5.8 | **OK** exit 0 — `6/6 catalogued trials + 1 pre-intent duplicate refusal; …; G2B live; main tree clean` |
| i | `validate-provenance-reconciliation.py --record … --plan-dir … --self-test` | P4.7 | **OK** exit 0 — `P4.1–P4.6 Git/status/journal map` |
| j | `validate-assurance.py …` (twelve-argument list, P5.8 form) | P5.8 | **OK** exit 0 — `P4 assurance validator: OK` |
| k | D134 anchor, two commands | P5.6/P5.8 | **OK** — `git diff --exit-code 3533234c … ':(exclude)…/validate-assurance.py'` empty; `git log --format=%h 3533234c..HEAD -- …/validate-assurance.py` → exactly `8a3974c1` |
| l | `bash packages/artifex/scripts/test.sh` | package | **OK** exit 0 — `Ran 128 tests in 3.222s … OK` |
| m | seam-admission smoke, validate-only `dispatch-business` of ONE v3 row | P5.5 | **OK** exit 0 — `{"intent_written":false,"provider":"claude-code","status":"admitted","trial_id":"p5.4w-wave-01-recovery-fixture","usage":0}`; no `runs-root` directory created |

`used_slices` sums re-read from disk after the smoke and before the first dispatch: D105 `0/14`,
D122 `0/3`, D125 `0/10`.

## 2. D109 generation-aware P0–P5 fan-in — 34 of 35 green, one out-of-scope red

Recorded machine-readably in `artifacts/P5/pilot-manifest-v1.json` (each check with its command, its
tree anchor, its exit code and its output tail; reproducible with
`run-battle-waves.py fan-in --manifest-out …`). Historical leaves ran at their **owning commits** in
temporary worktrees, the current G2B chain on the current tree, no stale-status replay:

- `P2/prototype` at `6c2c2ef3`, `P3/adapters` at `ea141189` (the plan-local prototype was promoted
  away by P3.8), `P4/authority-requalification` at `124df816` — all green at their own anchors.
- `P1/contract-set` was run on the **v2** eight-contract manifest only; the superseded v1
  six-contract manifest is recorded as superseded rather than replayed.

**The one red, and why it is not repaired here:** `P1/dispatch-admission` exits 1 with
`task p3-smoke-codex-v1: PARENT_ITEM_AS_TASK`, both on the current tree **and at its own owning
commit `140a9b53`**. Cause, established first-party: the frozen `parent_task_contract_hash`
`72553d6c…` in `artifacts/P1/p3-smoke-task-set-v1.json` matches neither the current recomputation of
the P3.4 Task Contract (`e4832db5…`) nor the recomputation at `140a9b53` (`326a0551…`) — the leaf
pins a `task.task_contract` compiler generation this repository no longer carries (cross-plan drift;
that compiler is owned by `2026.07.24-AGENT-RELIABILITY`, not by this plan). It is **not** a member
of P5.4's declared pre-intent gate set, **not** an input to the G2B chain this item measures, and
repairing a gate is in this item's Scope Excluded. Recorded, not silenced; remediation named in §7.

## 3. What was dispatched

Ten dispatches, frozen catalog order, one fresh provider process each, each on its own disposable
`git worktree` at the row's own base commit, each diff read BEFORE removal. The candidate lane went
through `security.indexed_business_admission` + `activity.BusinessProviderActivityPort.run` (D135:
the runner IMPORTS the port, because `cli.py`'s `dispatch-business-intent` drops the measured
`economy` envelope and adding it would be a package byte). The baseline lane used the same admission
gate, the same `business_dispatch.request`, the same `claude_code.build_business_argv`, the same
prompt (produced by the candidate's own `_prompt`) and the same `claude_code.fold_business_records`
extraction — with no supervisor: one direct headless single-shot invocation, no scheduler, no
bounded worker, no journal, no retry.

| pair | lane | reason_code | accepted | changed/declared | tokens | cost µunits | turns | duration ms |
|:--|:--|:--|:--|:--|--:|--:|--:|--:|
| wave-01-recovery-fixture | candidate | `OK` | **yes** | 1/1 | 387 640 | 1 019 133 | 22 | 194 615 |
| wave-01-recovery-fixture | baseline | `OK` | **yes** | 1/1 | 339 487 | 834 468 | 23 | 148 147 |
| wave-02-worktree-isolation | candidate | `PROVIDER_NONZERO` | no | 8/8 | — | — | — | — |
| wave-02-worktree-isolation | baseline | `PROVIDER_NONZERO` | no | 8/8 | — | — | — | — |
| wave-03-security-boundary | candidate | `BUDGET_TURN_COUNT` | no | 7/7 | — | — | — | — |
| wave-03-security-boundary | baseline | `PROVIDER_NONZERO` | no | 7/7 | — | — | — | — |
| wave-04-telemetry-assurance | candidate | `BUDGET_TURN_COUNT` | no | 7/18 | — | — | — | — |
| wave-04-telemetry-assurance | baseline | `BUDGET_TURN_COUNT` | no | 10/18 | — | — | — | — |
| wave-05-committed-gates | candidate | `OK` | **yes** | 5/5 | 2 532 570 | 4 512 510 | 30 | 738 152 |
| wave-05-committed-gates | baseline | `OK` | **yes** | 5/5 | 1 973 992 | 3 729 466 | 34 | 707 118 |

Two of five waves are accepted (both members accepted). **This is the first admitted, accepted
business dispatch in this plan's history** — every prior live attempt (P5.2 v1 and v2, P5.3) ended
`0/n accepted`, so the D121/D122/§8 seam repairs (`--allowedTools`, `item.started`, `errors`) are
now proven by an admitted dispatch, exactly as `research/39` §6 said they would first be.

**A measured budget fact, not a harness defect.** The three failed waves are the three largest file
scopes (8, 7, 18 declared files) and they fail in BOTH lanes, at the same scopes, under the raised
D125 budgets (`max_turns 40`, `timeout_ms 900000`). Symmetry across lanes is the load-bearing part:
whatever exhausts the work is the scenario and the turn budget, not the supervisor. `max_turns: 40`
was derived by D125 from a single observation (8 turns exhausted on 3 files) and is empirically
insufficient at 7+ files; wave 05 succeeded at 5 files using 30/34 turns, i.e. just inside the wall.

## 4. Verdict — `NO-GO`, three failed floors

`artifacts/P5/economic-verdict-v1.json`, adjudicated by the FROZEN `economy-evidence-v2` adjudicator
(`artifacts/P1/validate-economy-evidence.py::adjudicate_v2`, imported by path — this item
re-implements no threshold, formula, denominator, verdict or reason code):

```
verdict  : NO-GO
branches : []
reasons  : FLOOR_FAILED:REL-BUDGET · FLOOR_FAILED:REL-RECOVERY · FLOOR_FAILED:SEC-WORKTREE
scope    : single-provider claude-code, owner_grant_ref D123 (D126 excludes codex) — no parity claim
```

Floors green: `REL-ACCEPTED-SCOPE`, `REL-IDEMPOTENCY`, `REL-VALIDATION`, `SEC-AUTHORITY`,
`SEC-PRIVACY`, `SEC-HOOK-INTEGRITY`, `EVD-SOURCE-HASHES`, `EVD-INDEPENDENT-ADJUDICATOR`,
`EVD-UNKNOWN-PRESERVATION`.

Branch 1 was independently ineligible on three counts even before the floors: three of five waves
not accepted (`BRANCH1_WAVES_NOT_5`), null token/cost inputs on those attempts
(`BRANCH1_UNKNOWN` — unknown is never zero), and the intervention ratio (§6). Branch 2 is
`UNMATCHED_SCOPE` by construction: D124/D126 dispatched no Workflow lane, and the lane is declared
present-but-unmatched with all fourteen metric fields null and a source reason each, never as a
matched comparison.

## 5. The economic signal, stated honestly and with its limits

Only two of five pairs produced numbers, so **no D14 branch-1 verdict rests on them**. As raw
measurement, on both completed pairs the supervised candidate consumed MORE than the direct headless
baseline:

| pair | candidate tokens | baseline tokens | candidate cost µu | baseline cost µu |
|:--|--:|--:|--:|--:|
| wave-01 | 387 640 | 339 487 | 1 019 133 | 834 468 |
| wave-05 | 2 532 570 | 1 973 992 | 4 512 510 | 3 729 466 |

Both `coordinator` envelopes are measured structural zeros with a declared `zero_basis` (rule 2):
Artifex's scheduler makes no model call, and this runner makes none either. So the comparison is
worker-vs-worker with a provable zero on both sides — the weaker, honest claim `research/39` §2
already committed to. On this evidence the owner's token-economy hypothesis is **not** supported;
two pairs are far too few to conclude anything stronger, and this document claims nothing stronger.

## 6. Three defects of THIS item's own harness, disclosed rather than quietly patched

All three derivations were authored and committed BEFORE the first dispatch (proof: the
adjudicator's `--self-test` runs with no live result on disk, and both banks passed before any
dispatch). Defects (1) and (3) change a recorded NUMBER, so patching them after seeing results would
be exactly the post-hoc threshold replacement this item's Scope Excluded forbids — they are recorded
as measured and carry a forward fix in §7 instead. Defect (2) changes NO number: it is a
self-referential re-derivation bug that made the gate contradict itself across time, so it was fixed
in place and the fix is stated here.

1. **`rollback` reads `false` on eight of ten rows, and the tree is nevertheless provably clean.**
   The runner proves rollback with `git reset --hard <base>` plus an empty `git status`. Five of
   wave 02's eight declared files (and equivalents in waves 03/04/05) do not exist at the frozen base
   — the prompt explicitly instructs the worker to create them — and `git reset --hard` does not
   remove untracked files, so the status is non-empty and the flag reads `false`. Verified per file:
   `git cat-file -e bde07fb0:<path>` fails for `worktree.py`, `test_worktree_isolation.py`,
   `validate-worktree.py`, `worktree-cases-v1.json`, `worktree-results-v1.json`. Every disposable
   root was then removed with `git worktree remove --force`, so **zero residue exists**:
   `git worktree list` shows no `p5-p5-4-*` root, and `git status --porcelain -- packages/artifex`
   plus both G2B manifests are empty before, between and after all ten dispatches. `REL-RECOVERY`
   and `SEC-WORKTREE` therefore read `fail` from a measurement artifact, not from an isolation
   failure. The verdict is `NO-GO` on `REL-BUDGET` independently of these two.
2. **The intervention numerator had no derivation anchor, and its own closing row broke it
   (found by the gate itself, fixed in place).** Re-running `validate-economic-verdict.py` on the
   committed tree failed: `owner_decision_events 3 != journal-derived 4`. The journal is append-only
   and this item's own closing bookkeeping row (`result: blocked`) lands AFTER assembly, so an
   unanchored count over the whole file counts itself and can never be re-derived to the recorded
   value on any later tree. Fixed in this item's own `Files` by anchoring the count at the run's
   start row: the verdict now records `journal_cutoff_ts` (`2026-08-07T03:43:15Z`), the assembler
   counts qualifying rows strictly before it, and the validator re-derives against that recorded
   anchor and refuses if it is not a start row of this item. **No value and no verdict moved**:
   `owner_decision_events` is `3` before and after, the verdict is `NO-GO` with the same three failed
   floors. This is a fix to a self-referential re-derivation defect, not a change to a threshold,
   formula or verdict rule — those stay exactly where the pre-dispatch authoring put them. Landed as
   a commit OVER the two-commit topology (never an amend), so the defect and its repair are both
   traceable.
3. **`owner_intervention_ratio` reads `3/10`, and no owner intervened during this run.** The
   pre-declared numerator counts P5.4 journal rows whose result is `escalated`/`blocked`; it is not
   scoped to rows at or after this run's first dispatch, so it counts three historical rows
   (`2026-08-06T14:48:03Z` routing-blocked, `2026-08-06T15:00:48Z` and `2026-08-06T18:46:50Z` — the
   two pre-intent stops), all of which predate the first dispatch of this run
   (`2026-08-07T03:43:15Z`). Run-scoped fact: **zero** owner-decision events and **zero** attention
   events during the ten dispatches.

## 7. Forward remediation (this item stays open; nothing below was executed)

Ordered, each with its owner. `NO-GO` is not terminalized as success (`plan.md` §2), and P6 receives
no `GO`.

1. **Budgets (blocks re-measurement).** `max_turns: 40` is empirically insufficient at 7+ declared
   files in BOTH lanes; D125's value came from one observation. A new owner grant is required to
   raise it (this item may not raise, lower or re-derive a budget), together with a fresh carrier set
   — the ten D125 rows are one-shot and now spent, so any re-run needs new admissions regardless.
   Owner decision + P5.1-style mint.
2. **`PROVIDER_NONZERO` on waves 02/03 (both lanes).** The provider exited non-zero after editing
   every declared file. Whether that is turn exhaustion surfacing as a non-zero exit, a
   structured-output failure at the end of a long session, or something else cannot be determined
   from this item: retaining raw provider output is banned, and the fold layer is a package byte
   (P5.5-owned). A diagnostic pass with its own probe authority is needed — the same shape as
   `findings/P5-repository-pilot.md` §8's owner-directed investigation.
3. **This item's two value-changing harness defects (§6.1 and §6.3).** Prove rollback by comparing
   the root against its base tree object (or `git clean -fdx` after `reset --hard`) rather than by an
   empty status; scope the intervention numerator to journal rows at or after the run's first
   dispatch (§6.2's anchor fix makes the count reproducible, but it deliberately did not change WHICH
   rows qualify). Both live in `artifacts/P5/run-battle-waves.py`, this item's own `Files`.
4. **`P1/dispatch-admission` (§2).** Owned by P1.6 but red for a cross-plan reason; either re-freeze
   `parent_task_contract_hash` against the current compiler generation under a new D#, or record an
   explicit exemption for a leaf whose pin depends on another plan's evolving code. Neither is
   P5.4's to decide.

## 8. Integrity of this pass

- **Provider processes started: 10** — exactly one per dispatch (`process_count == 1` on every row);
  no eleventh process, no `codex` invocation, no diagnostic probe outside the ten admissions.
- **Admissions consumed: 10**, all D125, all distinct, each `used_slices: 1` in the run evidence.
  D105 (`0/14`) and D122 (`0/3`) sums re-read from disk after the last dispatch are still `0`; every
  v3 admission FILE is byte-unchanged (the package treats an admission as read-only frozen evidence,
  so consumption is recorded in the run evidence, not written back into the carrier) — verified by
  `sha256` per row against the frozen index and by an empty `git status` over
  `artifacts/P5/trial-admissions-v3`.
- **`packages/artifex` bytes touched: 0**; both G2B manifests unchanged; G3 pins the exact measured
  generation `4773f67e…` (= live = assurance = ledger entry 7 of 7), 50 recorded package files
  re-hashed from disk with **zero** post-P5.5 delta.
- **Adjudicator authored before the first dispatch**: `validate-economic-verdict.py --self-test`
  (22 contract cases through the frozen `adjudicate_v2` + 9 structural cases) passed on a tree with
  no `battle-wave-results-v1.json` on disk. Full run after the dispatches: `economic-verdict: OK
  (22 contract cases, 9 structural cases; 10 dispatches in 5 matched pairs; verdict NO-GO […];
  single-provider claude-code, no parity claim; 3 P6.1 inputs resolve)`, exit 0.
- **Forward conformance (`brief/37` §3(c))**: all three inputs P6.1 declares from P5 exist and
  resolve — `artifacts/P5/economic-verdict-v1.json`, `artifacts/P5/pilot-manifest-v1.json`,
  `artifacts/P5/validate-economic-verdict.py` — checked by the validator's own
  `check_forward_conformance`. Honest statement attached: the verdict they carry is `NO-GO`, so
  **P6.1's substantive input (a terminal `GO` over G2B) is not yet produced.**
- **Privacy**: no raw provider stream, prompt, transcript, tool payload, reasoning text or
  environment value was persisted. A scan of the three JSON artifacts for the six forbidden key
  classes plus `private_material` and for the repository's own secret-value pattern
  (`security.py:19`) is clean; the only `thinking` occurrence is the word inside the frozen
  `inclusion_bases` evidence prose, byte-identical to the P5.7 fixture.
- **JSON parse, `py_compile`, scoped `git diff --check`** — all green.
- Carried unchanged, untouched by this pass: the underived `bcd5443f…` aggregate carrier digest; the
  `rg`-dependent no-op on `packages/artifex/scripts/validate.sh:7`; the inherited inexact `commit`
  literal on the seventh ledger entry; the large foreign diff across other packages and the stale
  `git worktree` entries from other sessions.

RAG:— (repo-grounded throughout: every command above was executed first-party in this session on
`9005fa92`; no external fact class is load-bearing for any measurement or finding here).
