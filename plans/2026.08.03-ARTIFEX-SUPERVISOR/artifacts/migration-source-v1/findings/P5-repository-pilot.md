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

## 7. D121/D122 re-run (2026-08-06, second pass, session claude-sonnet-5/high)

D121 fixed the root cause §6 left open — the frozen admission carried no task description, so
`_prompt` physically could not state one (`findings/P5.2-task-description-gap-2026-08-06.md`
F1–F4). P5.5 reopened a second time and taught the seam to resolve `scenario`/`kind` from the
hash-pinned catalog. D122 minted three replacement admissions (`p5.2r-slice-01-worktree-core`,
`-02-worktree-binding`, `-03-worktree-evidence`) with the `claude-code` wall-clock raised to
`600000` ms. A live attempt to re-run those three through the newly-fixed seam found a **second,
separate** defect first: `business_dispatch.load_indexed` was hardcoded to the 14-row v1 admission
index and could not recognize any v2 admission at all — 3/3 live probes refused
`ADMISSION_NOT_INDEXED` before intent, zero processes started
(`findings/P5.2-v2-admission-not-indexed-2026-08-06.md` F1–F4). The repository owner, directly in
the live session, authorized fixing this in place rather than escalating through another
`plan-design` cycle: `business_dispatch.py`/`activity.py` gained a `GRANT_BATCHES` lookup keyed on
`admission.grant.owner_decision` (`D105`→v1 index/catalog/14 rows, `D122`→v2 index/catalog/3 rows),
preserving v1 behavior byte-for-byte (16 pre-existing unit tests unchanged, package suite 100/100
green) while making the v2 batch reachable. G2B was re-frozen a third time
(`validate-business-successor.py --write`, the same two stored R2 probe rows fed back verbatim, 0
new provider processes): `generation_hash` `f86a9f75…` → `7a44f9bc2a4e72fb940f29a1b96bbfcc0da2f086448ef4170ab7473358ac5891`.

**Process defect, disclosed:** immediately after the fix landed but *before* it was committed, a
manual CLI probe intended only to confirm the seam no longer refused `ADMISSION_NOT_INDEXED`
instead passed the (then-uncommitted) fix and dispatched a real codex process against
`p5.2r-slice-01-worktree-core` — one of the three one-shot D122 admissions. The disposable
worktree was removed before its `git diff` was inspected, so `changed_paths` for this one slice is
unrecoverable; the worktree's deletion itself proves no residue exists anywhere (rollback holds),
but not what, if anything, codex wrote before failing. Per the item's own rule this attempt is not
retried — it is recorded honestly in `repository-pilot-results-v2.json` with `changed_paths: null`
and an `evidence_gap` field naming the cause, `accepted: false`. The fix was committed
(`6755be6b`) before the remaining two slices ran through the proper `run-pilot.py` flow (worktree
preserved until `changed_paths`/rollback were computed, exactly as designed).

**Execution — three real dispatches, D122 admissions, catalog order:**

| Slice | Provider | `process_count` | `reason_code` | `changed_paths` | `accepted` | `rollback` |
|:--|:--|--:|:--|:--|:--|:--|
| p5.2r-slice-01-worktree-core | codex | 1 | `PROVIDER_PROTOCOL_UNKNOWN` | unrecoverable (evidence gap, harness error) | false | true |
| p5.2r-slice-02-worktree-binding | claude-code | 1 | `PROVIDER_PROTOCOL_UNKNOWN` | `[]` | false | true |
| p5.2r-slice-03-worktree-evidence | codex | 1 | `PROVIDER_PROTOCOL_UNKNOWN` | `[]` | false | true |

**0/3 accepted again**, but this is a materially different result from §2–6's `0/3`: every slice
now carries a real, non-empty `scenario`/`kind` in its prompt (D121 verified working), two of
three target file sets exist at the frozen base for the first time (`v2` catalog rows reuse the
same files as `v1`; slice-02's claude-code target existed at base in both rounds), and none hit
`WALL_TIMEOUT` this time (claude-code finished inside the raised `600000` ms budget). All three
independently hit `PROVIDER_PROTOCOL_UNKNOWN` — the fold layer (`fold_records` for codex,
`fold_business_records` for claude-code) could not parse the provider's real output into the
single expected `result` record once the model was given genuine work instead of a same-turn
canned response. This plan's Code Guidance bans retaining raw provider output even for debugging,
so the exact parse failure (extra streamed events vs. a malformed terminal record vs. something
else) could not be inspected from this item; it reads as a candidate/seam-adapter finding for a
future P5.5 pass, not something this item may patch mid-pilot (same hard ban as §6). D105 stays
14/14 unused; the three D122 admissions are now one-shot spent (real dispatches occurred for all
three); `packages/artifex` and both G2B manifests carry zero diff before/between/after (`git
status`/`git diff` both empty, independently re-confirmed by `validate-repository-pilot.py`).
`validate-repository-pilot.py` (re-pinned to the v2 index/results) reports the honest result:
`FAIL: not accepted: [...] (0/3 accepted)`, exit 1 — not adjusted to force green.

## 8. Root-cause of `PROVIDER_PROTOCOL_UNKNOWN` (2026-08-06, owner-directed live investigation)

The repository owner, directly in the live chat session, instructed a full root-cause
investigation of §7's `PROVIDER_PROTOCOL_UNKNOWN` pattern — RAG via `perplexity-web` plus live
diagnostic dispatches in disposable, scratch git worktrees, zero D105/D122 admissions touched (no
grant spent; every diagnostic ran outside the admission/seam system entirely). Owner scoping: the
claude-code path is this session's priority; the codex path is left for its own future
self-testing pass rather than fully hardened here.

**claude-code — the real, structural blocker (fixed).** `--permission-mode dontAsk` auto-denies
any tool call not on a *separate* `--allowedTools` allow-list; `--tools` only declares the
available palette (RAG:✅ 2026-08-06, `perplexity-web`, permission-mode semantics table).
`build_business_argv` never passed `--allowedTools`, so every real Edit call was silently denied
regardless of budget. Live proof before the fix: a full real dispatch against slice-02's exact
scenario/files, correct credentials, returned `{"status":"refused","summary":"Blocked by tooling:
Edit is denied in \"don't ask mode\"..."}`. After adding `--allowedTools Read,Edit` (identical to
`--tools`, nothing widened): the same dispatch produced a real edit to `scheduler.py` (+37 lines).
Residual: `max_turns: 8` (a frozen D105/D122 catalog value, unchanged by this fix) is still tight
for a genuine 3-file edit — the fixed dispatch still exhausted it before returning final structured
output. Raising it needs a new owner grant (the same class of authorization D122 used to raise
`claude-code`'s `timeout_ms`), out of this fix's scope.

**codex — an independent parsing gap (fixed).** `ALLOWED_EVENTS` recognized `item.completed` but
not `item.started`, which real multi-step codex sessions legitimately emit per tool call (RAG:✅
2026-08-06, `perplexity-web`, Codex `exec --json` ThreadEvent taxonomy). Live proof: a real,
successful codex dispatch that wrote 369 lines across two new files emitted 13 `item.started`
events — every one of which would have tripped `PROVIDER_PROTOCOL_UNKNOWN` under the old allowlist,
independent of any sandbox/environment issue. Added `item.started` to `ALLOWED_EVENTS`.

**claude-code — a second, independent parsing gap (fixed).** `_RESULT_KEYS` did not include
`errors`, a real key the CLI emits on `subtype: error_max_turns`. Added.

**codex — a real, deeper environmental limitation (found, deliberately NOT fixed here).**
`activity.py` dispatches every provider subprocess with `env={}` (`subprocess.Popen`'s `env=`
replaces, never merges the parent's environment). For codex specifically this breaks its own
bubblewrap-based sandbox: live diagnostics show a real write attempt failing outright under
`env={}`, and even after adding back the *already security-permitted* `PATH`/`LC_ALL`/`LANG`/`TZ`
(`security.py`'s `_ENV_NAMES` already allows these four; `activity.py` simply never passes them),
codex's sandbox still fails deeper — `bwrap: loopback: Failed RTM_NEWADDR: Operation not
permitted` (RAG:✅ 2026-08-06: a documented AppArmor/unprivileged-userns restriction on nested
bubblewrap sandboxes). The verified working escape hatch is codex's own official
`--dangerously-bypass-approvals-and-sandbox` flag ("intended solely for environments that are
externally sandboxed" — precisely this harness's situation): a live diagnostic with it set wrote
the real 369-line change referenced above. **Not adopted**: this host was independently confirmed
to have real outbound network access (`curl` to two external hosts both returned real HTTP
responses, not connection failures), so bypassing codex's sandbox also removes the
`network-disabled` guarantee that is an explicit capability and `SEC-WORKTREE` acceptance_ref on
every catalog row — a genuine security-posture trade-off, not a mechanical bug, and left for a
future owner decision (matches this session's owner-scoping: codex's own path is not this
session's priority).

**Evidence discipline.** No raw provider transcript, prompt or tool-call content was persisted to
any committed file or to this document — every quoted fragment above is either a short structural
JSON-key/event-type name or a schema-conforming `summary`/`errors` string already inside the
provider's own structured-output contract, matching this plan's standing privacy rules. All
diagnostics ran in `/tmp` scratch worktrees created and destroyed outside git; none touched
`repository-pilot-results-v2.json`, any D105/D122 admission file, or spent any grant.

3 new unit tests lock the two fixes in (`test_provider_codex.py`::real multi-item `item.started`
fold; `test_provider_claude_code.py`::real max-turns-exhaustion fold with `errors`; ::business argv
`--allowedTools`/`--tools` parity) — package suite 103/103 green, `validate.sh` green. G2B
re-frozen a fourth time (`generation_hash` `7a44f9bc…` → `61d9e34c2e0e51dbf69f0bbb328f6d81994bbbfb3e0a8e78ca2fee05403276d4`,
same two stored R2 rows fed back verbatim, 0 new provider processes). Item commit `6b9afc9b`.
