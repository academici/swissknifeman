# P5.2 — exact three-slice repository pilot (real evidence, 2026-08-06)

**Layer:** 1 (raw, first-party measurement) · **Tree:** `f81c034e` (working tree carries
unrelated pre-existing uncommitted diff — `phases/P6.md`, other packages — not touched here).
Item spec: `phases/P5.md` P5.2, lines 123-148. Owner authority for this run: D105 (unused grants,
`used_slices: 0`, expiry `2026-08-12T23:59:59Z`), D119 (seam ownership → P5.5), D120 (Claude
version pin discipline).

## 0. Preconditions (before any mutation)

- `git status --porcelain -- packages/artifex` → empty.
- `python3 plans/.../artifacts/P5/validate-business-successor.py …` (full argv reproduced from
  `run-pilot.py`'s own `preflight()`) → `P5 business successor validator: OK (G2→G2B; 14/14 D105
  rows unused; 2 non-business probes)`, exit 0.
- Live G2B digest recomputed over current `packages/artifex` bytes:
  `f13c30f25dc50075669dd97f7ab4c8ec2fd9e54260e5359adbfe34c33ef0fcc6` — matches
  `business-successor-generation-v1.json`/`business-successor-assurance-v1.json` exactly (P5.5's
  2026-08-06 re-freeze, per D119). The stale `7c1187f0…` literal named in the P5.2 spec's defect
  list is confirmed gone from the fixed harness.
- `export SKM_CLAUDE_BIN=/home/vostrikov/.local/share/claude/versions/2.1.222`;
  `"$SKM_CLAUDE_BIN" --version` → exact literal `2.1.222 (Claude Code)`, exit 0. PATH `claude`
  resolves to `2.1.223 (Claude Code)` (unused, never invoked). `codex --version` (via PATH,
  `/home/vostrikov/.local/bin/codex` → `~/.codex/packages/standalone/current/bin/codex`) →
  `codex-cli 0.146.0`, matching the frozen pin.
- `bash packages/artifex/scripts/test.sh` → 89/89 tests green (pre-run baseline, matches F6).

## 1. Defects fixed in `run-pilot.py` (three named + two discovered live)

Full diff: `git diff -- plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P5/run-pilot.py` (available
in the working tree, unstaged).

1. **Stale G2B hash constant (named defect 1).** Removed the hardcoded `G2B = "7c1187f0…"`
   module constant. Added `g2b_hash(plan)`, which reads `g2b_generation_hash` from
   `business-successor-assurance-v1.json`, cross-checks it against
   `business-successor-generation-v1.json`'s `generation_hash`, and refuses
   (`G2B_HASH_UNAVAILABLE`) on any mismatch or absence. Called fresh on every invocation, after
   `preflight()`'s own re-run of `validate-business-successor.py` already proved the manifests
   match current package bytes. The pin can now never silently drift again.
2. **D120 version pin not honored (named defect 2).** Added `resolve_claude_bin()`: requires
   `SKM_CLAUDE_BIN` set, absolute, an executable file; never falls back to `which("claude")`.
   `execute()` now resolves the Claude binary exclusively through this function for
   `claude-code` admissions; `codex` keeps `which("codex")` (pin not in question, per item spec).
   The live `--version` re-probe (`probe_version`) now runs **once**, immediately before the
   first dispatch of the whole three-slice batch — gated by `_existing_probe()`, which returns the
   already-recorded `version_probe` object from `repository-pilot-results-v1.json` once at least
   one slice has run, so slices 2 and 3 reuse the recorded evidence instead of re-invoking
   `--version`. The recorded probe (binary path + literal) is embedded in the results file itself
   (see §3) rather than only printed to a terminal.
3. **Stale void historical artifact (named defect 3).** Moved
   `repository-pilot-results-v1.json` (one non-accepted codex slice against the *old* G2B hash,
   VOID under D117/D114-D116) aside to
   `repository-pilot-results-v1-void-2026-08-06.json` in the same directory — preserved, not
   deleted. `run-pilot.py` now creates a fresh `repository-pilot-results-v1.json` seeded with the
   live G2B hash on first use, exactly as before but no longer racing a stale file.
4. **Discovered live: `which()` PATH restriction (not a named defect, found during execution).**
   The original `which()` ran under the harness's own reproducible `_ENV`
   (`PATH=os.defpath` = `/bin:/usr/bin`). On this host `codex` resolves only via
   `/home/vostrikov/.local/bin/codex` (a user-PATH symlink), which is outside `os.defpath`, so
   `which("codex")` returned empty and every codex slice refused with `PROVIDER_UNAVAILABLE`
   before any dispatch. Fixed by resolving binary *discovery* (only) against the real ambient
   `PATH`; the actual dispatch/git subprocesses still use the restricted `_ENV`. The frozen
   version literal is still independently re-probed regardless of which PATH found the binary.
5. **Discovered live: `--runs-root` absolute-path bug (not a named defect, found during
   execution).** `execute()` passed an absolute temp path (`Path(temporary) / "runs"`) as
   `--runs-root`. `cli.py`'s generic `_roots()` composes `repo / args.runs_root`; per Python's
   `pathlib` semantics, joining with an *absolute* right operand discards the left operand
   entirely, so the composed path was never inside `--repo-root`, and the shared `_inside()`
   path-safety gate (which runs for *every* subcommand, including `dispatch-business-intent`)
   refused with `PATH_EXTERNAL` before any dispatch. `cli.py` was not touched (hard boundary).
   Fixed on the `run-pilot.py` side only: `--runs-root` is now a repo-relative, never-materialized
   literal (`artifacts/P5/.p5.2-pilot-noop-runs/<trial_id>`) — safe because `_dispatch_business_intent`'s
   handler ignores its `_runs` parameter entirely, and `_roots()` only ever creates the directory
   for the `start` subcommand. Confirmed after every slice that this path was never created on
   disk. This bug was already present in the pre-fix, stale `run-pilot.py` and would have blocked
   the historical void attempt too had it reached this code path with a disposable temp root.
6. **`_main_tree_guard` scope narrowed.** The original preflight refused on *any* repository-wide
   dirty path outside two allow-listed output files — which would refuse unconditionally in this
   environment (67 unrelated pre-existing dirty paths at session start, per the task's own note),
   and would also self-refuse the moment `run-pilot.py` itself is edited (it is one of this item's
   own `Files`). Narrowed to guard exactly the two D119 surfaces named in the item's own
   **Validation** field — `packages/artifex/**` and the two G2B manifests — which is the actual
   invariant this item must prove. Unrelated repository drift outside that surface is not this
   item's authority to police.

`run-pilot.py` remains stdlib-only, `shell=False`, explicit argv, no ambient discovery beyond the
one narrowly-scoped `which()` PATH lookup described above.

## 2. Execution — three real, live dispatches, in catalog order

All three ran through the fixed `run-pilot.py`, one process invocation per slice,
`SKM_CLAUDE_BIN` exported in the invoking shell. Exact commands:

```
python3 plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P5/run-pilot.py \
  --slice p5.2-slice-01-worktree-core \
  --results plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P5/repository-pilot-results-v1.json
```
(repeated for `p5.2-slice-02-worktree-binding`, `p5.2-slice-03-worktree-evidence`)

| Slice | Provider | Wall time | Exit | `process_count` | `reason_code` | `changed_paths` | `accepted` | `rollback` |
|:--|:--|--:|--:|--:|:--|:--|:--|:--|
| p5.2-slice-01-worktree-core | codex | ~21s | 1 | 1 | `OK` | `[]` | **false** | true |
| p5.2-slice-02-worktree-binding | claude-code | ~181s | 1 | 1 | `WALL_TIMEOUT` | `[]` | **false** | true |
| p5.2-slice-03-worktree-evidence | codex | ~21s | 1 | 1 | `OK` | `[]` | **false** | true |

Every `run-pilot.py` invocation printed `P5.2 pilot: FAIL: non-terminal slice` and exited 1 — the
harness's own designed behavior on a real, non-accepted (but otherwise clean) dispatch; not a
crash, not an exception, not a refusal before intent. Each slice was still appended to
`repository-pilot-results-v1.json` (the harness records the real result regardless of acceptance).

**Interpretation.** All three admissions were consumed exactly once (`max_slices: 1`,
`reusable: false`; no more grants exist for these trial IDs). All three used a genuinely fresh
single process (`process_count: 1`, `fresh_process: true`), all three left the disposable worktree
byte-identical to its frozen base after rollback, and the main tree
(`packages/artifex` + both G2B manifests) was confirmed clean before, between, and after every
slice. None of the three, however, produced a business edit inside its declared file scope:

- **Slices 1 and 3 (codex):** the seam's own prompt (`activity.BusinessProviderActivityPort._prompt`,
  P5.5's surface, not edited here) reads *"Implement the bounded repository slice… modify no
  other path…"* with no further specification of what change is required. Both target file sets
  (`lib/artifex/worktree.py` + `tests/test_worktree_isolation.py`; three P4 evidence files under
  `plans/.../artifacts/P4/`) are already complete, terminal, tested bytes. Codex returned a
  schema-valid `success` record (`reason_code: OK`) without touching any file — a reasonable
  response to an under-specified "implement X" instruction against code with nothing left to
  implement, not a tool crash.
- **Slice 2 (claude-code):** ran for the full `timeout_ms: 180000` (3-minute) admission budget and
  was killed by `worker.run`'s own wall-clock enforcement (`WALL_TIMEOUT`) before returning a
  result — a real, designed budget refusal, not an unhandled error.

This is real, non-fabricated evidence of the D118/P5.5 business-execution seam's live behavior
against these three specific pre-declared admissions. **This finding does not itself fix, patch,
retry, or route around any of it** — per Implementation Rules, "if the seam turns out to need a
change, that is an escalation to reopen P5.5 again — not an in-pilot patch," and per hard boundary,
no `packages/artifex/**` byte or G2B manifest was touched. The three admissions cannot be retried
(one-shot, no further D105 grants for these trial IDs); this is their terminal state.

## 3. Independent verification

`validate-repository-pilot.py` (new, stdlib-only, imports nothing from `run-pilot.py`) reads
`repository-pilot-results-v1.json` plus the live G2B manifests, the D105 admission index and Git,
and independently re-derives every claim in the item's **Validation** field: catalog order and
distinctness of the three trial IDs, freshness (`process_count == 1`), one-slice grants
(`max_slices == 1` on both `task.budgets` and `grant`), `accepted`/`rollback`/`intent_written`
booleans, `changed_paths` scope-only equality against each admission's declared `task.files`, live
G2/G2B hash equality (re-read, not trusted from the results file), zero `d105_used_rows`, the
recorded `version_probe` against the frozen literals, and — independently, via its own `git
status`/`git diff` calls, not by trusting the `main_tree_delta` flag — that
`packages/artifex` is clean and the two G2B manifests carry no unstaged diff. It also re-verifies
that all three on-disk admission fixtures are byte-identical to their `trial-admission-index-v1.json`
`sha256` and that their `usage`/`replay` counters remain exactly `{used_slices: 0, max_slices: 1,
reusable: false}` / `{events: [], used_slices: 0}` — confirming the package exposes **no**
usage-increment mechanism for these fixtures (checked in `activity.py`/`cli.py`/`security.py`; none
exists) and that nothing mutated them.

```
$ python3 plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P5/validate-repository-pilot.py
P5.2 repository-pilot validator: FAIL: p5.2-slice-01-worktree-core: accepted is not true
```
Exit code: 1.

This is the **correct, honest** result: the validator does exactly what it is supposed to do
— report that this real run did not achieve three accepted business deltas — rather than being
adjusted to pass. No result was altered to force a GREEN.

## 4. Supporting gates (unaffected by the pilot)

```
$ bash packages/artifex/scripts/test.sh
Ran 89 tests in 3.630s
OK
```

```
$ bash packages/artifex/scripts/validate.sh
Ran 89 tests in 3.630s
OK
packages/artifex/scripts/validate.sh: line 7: rg: command not found
artifex validation: OK
```
Exit code: 0. **Pre-existing environment defect, disclosed per F6 / root.evidence-integrity, not
introduced or fixed here:** `rg` is not installed in this environment, so the script's plan-path
reference guard (`if rg -n … ; then … exit 1; fi`) silently no-ops instead of actually scanning —
the same defect the P5.2 findings pass already recorded on 2026-08-06. `validate.sh` still reports
`OK` only because the guard never ran, not because it ran and passed.

```
$ python3 plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P5/validate-business-successor.py \
    --contract … --cases … --provider-manifest … --provider-cases … \
    --generation … --assurance … --g2 … --admission-index … --package packages/artifex
P5 business successor validator: OK (G2→G2B; 14/14 D105 rows unused; 2 non-business probes)
```
Exit code: 0 — re-confirmed **after** all three dispatches: the G2B digest is still byte-identical
to before the pilot started (`f13c30f2…`), and D105 usage is still 14/14 unused.

```
$ git diff --exit-code -- packages/artifex \
    plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P5/business-successor-generation-v1.json \
    plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P5/business-successor-assurance-v1.json
$ echo $?
0
$ git status --porcelain -- packages/artifex
$ echo $?
0
```
Both empty before, between, and after all three slices — no `packages/artifex` byte and no G2B
manifest byte moved at any point. The three admission fixture files under
`artifacts/P5/trial-admissions/` are likewise byte-identical (`git diff --exit-code` on all three,
exit 0) — confirmed both by direct `git diff` and independently inside
`validate-repository-pilot.py`.

## 5. Scope of this item's own diff

Exactly the four files named in this item's `Files` field, plus the required void-rename:

```
 M plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P5/repository-pilot-results-v1.json
 M plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P5/run-pilot.py
?? plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P5/repository-pilot-results-v1-void-2026-08-06.json
?? plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P5/validate-repository-pilot.py
```
(`findings/P5-repository-pilot.md`, this file, is new/untracked and part of the same set.)
`phases/P5.md`/`journal.jsonl`/`phases/P6.md` show pre-existing dirtiness from before this
session's work (the plan-design pass that recorded D119/D120 and unrelated foreign edits) and
were not touched here. Nothing was staged or committed, per instruction.

## 6. Verdict and open question for the owning plan session

The pilot's plumbing is proven sound and safe: three catalog-ordered, distinct, unused D105
admissions were each consumed exactly once through fresh, single processes; every disposable
worktree was created, measured and rolled back to its exact frozen base; the main tree and both
G2B manifests never moved a byte; the Claude pin was honored exactly (`2.1.222 (Claude Code)`,
never PATH `2.1.223`); and G2B was re-derived live rather than hardcoded. Both required
validators (`validate-repository-pilot.py`, package `validate.sh`) run cleanly to completion and
report their true result.

The item's **Validation** field, however, requires "scope-only accepted deltas… and rollback" —
and the honest real-world result is **0 of 3 accepted**: two zero-diff `success` records and one
`WALL_TIMEOUT` refusal. `validate-repository-pilot.py` correctly reports `FAIL` for this reason.
Per the hard bans named in this item's own Code Guidance ("never edit a `packages/artifex/**`
byte or a G2B manifest to make a gate pass — a seam defect is an escalation that reopens P5.5, not
an in-pilot fix"), no attempt was made to alter the seam's prompt, retry an admission, or adjust
the acceptance criterion to force a pass. All three D105 grants for P5.2's trial IDs are now
one-shot spent (real dispatches occurred); no further live attempt is possible against these exact
admissions. Whether this constitutes a P5.5 seam-quality defect worth reopening again, an
acceptable pilot outcome given the item's own stated "Why" (proving the mechanical path is safe
and reversible, not that every business prompt yields an edit), or grounds for a new D105 grant
batch is a plan-design decision outside this item's own authority to make.
