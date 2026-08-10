# P5.3 — Crash / resume / duplicate / provider-failure pilot

Session: sonnet/high, `/task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P5.3`.

## 1. What this proves

The P5.2 business seam (`bin/artifex dispatch-business-intent`) is deliberately
**journal-free**: a single synchronous subprocess call with no internal
cut-points, no persisted admission-usage bookkeeping (the one-shot D105 limit
is enforced only by whatever harness calls it — exactly as P5.2's
`run-pilot.py` already proved with its own order/reuse ledger). P4's
`faults.py` crash simulator targets the *journaled* P2 path via a synthetic
dummy child; it doesn't apply here and can't be reused unmodified since
`packages/artifex/**` is out of P5.3's `Files` scope. This pilot therefore had
to invent, from scratch, an *external*, black-box mechanism for crashing a
real provider subprocess at precise process-state boundaries — and prove that
mechanism correct before spending any of the six real, one-shot, irreplaceable
D105 admissions this item was granted (expiry `2026-08-12T23:59:59Z`).

## 2. Owner decision on the crash mechanism (2026-08-06)

Before touching any real admission, the executor surfaced the invented,
plan-unspecified nature of the crash-injection mechanism and its irreversible
cost (`AskUserQuestion`, three options: execute now / escalate to plan-design
/ dry-run against fake binaries first). The owner delegated to executor
judgement, asking for "the ideal package" (verbatim: *"на твое усмотрение, как
будет лучше всего и правильнее, мне нужен идельный пакет!"*). The executor
chose the dry-run-first path: validate the mechanism synthetically and against
the real `dispatch-business-intent` CLI wrapped around fake, zero-cost
binaries, *before* running the official six real trials.

## 3. Mechanism, and what the dry run actually caught

Three `/proc`-based, poll-until-condition primitives (never a fixed sleep as a
*decision* — every wait reacts to real kernel-observed process state, bounded
by a deadline):

- `find_dispatch_child` — detects the moment the artifex process spawns its
  real provider child (filtering out the transient `--version` probe child).
- `wait_gone` — detects full disappearance of a child from `/proc` (fully
  reaped by its parent).
- Killing only the artifex PID (never its process group) reliably **orphans**
  its provider child rather than killing it, because `worker.run()` spawns
  the provider with `start_new_session=True` — verified directly against the
  kernel in this sandbox before any code was written.

The dry run caught two real bugs before they could waste a real admission:

1. **Zombie-state detection was originally the "after_observation" cut
   signal** and passed a synthetic self-test cleanly — then failed against
   the *real* seam. Root cause: `worker.run()` reaps its child essentially
   immediately after stdout EOF, with no artificial delay; the true zombie
   window measured sub-millisecond in this environment, unobservable at any
   reasonable external poll granularity. Fixed by switching the cut signal to
   full child disappearance (`wait_gone`) instead — an empirical dry run
   measured a reliable ~46ms window between "child gone" and "parent has
   finished decoding/printing", wide enough for a 5–10ms poll to land inside.
2. **A `tempfile.TemporaryDirectory` context manager would have destroyed the
   call-06 "preserve for owner inspection" worktree** regardless of any
   in-process "keep" flag, the instant the function returned — defeating the
   entire point of that trial and risking corrupting a still-running orphaned
   process's own working directory out from under it. Fixed by switching to
   manual `tempfile.mkdtemp()` with explicit (non-auto) cleanup.

Both fixes, and the self-test's own zombie-fixture rewrite (a bash `(...)&`
subshell non-deterministically let `$!` name the wrong PID — a real,
independently-discovered race, fixed by switching the synthetic fixture to a
direct `os.fork()`), are visible in `run-recovery-pilot.py`'s inline
commentary at the point of the fix.

Self-test (`self_test` block in `recovery-pilot-results-v1.json`, run first,
required by `main()` before any `--slice` may execute): 3/3 spawn-detections,
3/3 reap-window detections, 3/3 orphan confirmations — all true, run twice
independently during development plus once as the official first step.

## 4. The six real trials

All six ran through the identical `dispatch-business-intent` seam P5.2 used,
against real, unused, one-shot D105 admissions (`p5.3-call-01`..`06`), each
admission's on-disk bytes/usage/replay counters independently re-verified
unchanged by `validate-recovery-pilot.py` after the fact (the package persists
no usage state at all — the one-shot proof is entirely in this harness's own
bookkeeping plus the admission's static contents never having moved).

| Trial | Provider | Mechanism | Outcome |
|:--|:--|:--|:--|
| call-01 crash-after-intent | codex (real) | kill artifex the instant its child is observed spawned | `crash_verified: true`, reconciled to clean **preimage**, rollback proven |
| call-02 crash-after-observation | claude-code (real) | kill once the child is confirmed reaped | `crash_verified: true`, reconciled to clean **preimage**, rollback proven |
| call-03 duplicate-dispatch | codex (real, once) | real dispatch, then a second attempt against the same admission | first: real dispatch (`process_count: 1`, `reason_code: OK`, no accepted edit); second: refused by this harness's own ledger **before any subprocess was spawned** (`process_spawned: false`, `SLICE_ALREADY_RUN`) |
| call-04 provider-timeout | fake codex binary | deterministic hang past the frozen `180000ms` budget | `WALL_TIMEOUT`, refused, rolled back |
| call-05 schema-refusal | fake claude-code binary | deterministic single malformed output line | `PROVIDER_PROTOCOL_UNKNOWN`, refused, rolled back |
| call-06 unknown-third-state | claude-code (real) | kill mid-flight, **deliberately discard the child PID** | `owner_unknown` / `PID_TRACKING_DISCARDED_BY_DESIGN` — see §5 |

Calls 04/05 deliberately used a fake binary rather than the real pinned
provider: P5.2 showed real codex slices reliably return in ~20s and this
session's earlier `--allowedTools` fix now makes real claude-code dispatches
*more* likely to succeed than schema-refuse — neither is a deterministic way
to exercise these two scenarios without gambling a one-shot admission on
uncertain real-world timing ("no random cuts", Code Guidance). Every other
trial used the real, version-pinned provider binary.

## 5. Call-06: the trial this pilot exists to prove

Unlike calls 01/02 (which retain the crashed process's PID and positively
confirm its termination before trusting the worktree's Git diff), call-06
**deliberately discards** the child PID immediately after confirming it
spawned — simulating the one failure mode that actually matters here: the
business seam persists *no* resume state at all, so a real supervisor
resuming after its own crash has no reliable way to reassociate an orphaned
process with the admission that spawned it. Without a PID, a clean Git diff is
genuinely ambiguous (nothing happened vs. not written yet) — so this trial
never inspects the diff to decide, and unconditionally reconciles to
`owner_unknown` with **zero further mutation**: no rollback, no `accepted`
verdict, and the worktree was left in place (not removed) for owner
inspection, exactly as `Implementation Rules` require for an unverified
orphan.

At verdict time the real claude-code process (PID recorded only in this
findings doc, not in the results file, precisely because the pilot's own
logic never used it) was still actively running in the preserved worktree,
bounded by the frozen `--max-turns 8`/`--max-budget-usd 5` admission budget.
**Post-verdict forensic note** (does not and must not change the recorded
`owner_unknown` verdict — "no post-hoc expected-row changes"): the process has
since exited on its own; the preserved worktree's Git diff was empty. This is
informational only. The recorded verdict is correct as written — the pilot
could not have known this in advance, which is exactly the property under
test. The now-idle, diff-clean worktree was removed as ordinary operational
cleanup after this forensic check, separately from and after the pilot's own
verdict.

## 6. Validation

Green (this session, before the item commit): `validate-trial-admissions.py`
(v1 args, terminal P5.1) · `validate-business-successor.py` (terminal P5.5,
G2B) · `validate-fault-matrix.py` / `validate-recovery.py` /
`validate-worktree.py` / `validate-security.py` (directly consumed P4
validators) · `validate-recovery-pilot.py` (this item, new) · JSON parse ·
privacy scan (grep for raw prompt/thinking/tool-payload/secret markers over
the new artifacts) · scoped `git diff --check` · `bash
packages/artifex/scripts/test.sh` (103/103, package untouched).

**Red, pre-existing, out of this item's Scope:** `validate-repository-pilot.py`
(terminal P5.2's own validator) fails —
`results g2b_generation_hash stale: '7a44f9bc…' != live
'61d9e34c2e0e51dbf69f0bbb328f6d81994bbbfb3e0a8e78ca2fee05403276d4'`.
Root cause: P5.2's `repository-pilot-results-v2.json` was frozen against G2B's
*third* freeze; this same session (recorded in P5.2's own Completion Notes)
later re-froze G2B a *fourth* time while fixing two real provider-adapter
bugs, *after* P5.2 had already closed. `packages/artifex/**` and
`repository-pilot-results-v2.json` are both outside P5.3's `Files` — this
harness cannot fix it without violating scope. This is the same shared root
cause already carried in `handoff.md`'s Open risks for the four
`validate-shadow.py`/`validate-assurance.py`/`validate-package-promotion.py`/
`validate-contract-set.py` gates (D108's additive seventh contract / D118–119
package divergence from G2); it does not block P5.3 (this item's own
`g2b_generation_hash` correctly pins the current, fourth-freeze value and
`validate-recovery-pilot.py` is green against it) but it does mean the plan's
own Validation line item ("Terminal P5.1/P5.5/P5.2 … validators are green")
is not fully satisfiable on the current tree without a P5.2-owned fix.
**Remediation proposal:** a small P5.2-scoped follow-up (or bundled into
P5.4's consolidated fan-in, which already re-validates the current G2B
successor) should re-run `run-pilot.py`'s three D122 slices once more (zero
new admissions — P5.2's own three are already spent, so this specifically
needs either a fresh owner-approved admission triple or, more cheaply, a
`validate-repository-pilot.py` mode that accepts a *historically pinned* G2B
hash for slices whose admissions are already exhausted, matching how P4's
leaves are validated "on their own tree" rather than the live one. Left open,
named here, in Pending Work below and in `handoff.md` Open risks — not
silently absorbed into a P5.3 status change.

## 7. Sources

`recovery-pilot-results-v1.json` · `run-recovery-pilot.py` ·
`validate-recovery-pilot.py` · terminal `trial-admission-index-v1.json` ·
terminal `business-successor-{generation,assurance}-v1.json` · P4
`fault-matrix-v1.json`/`recovery-results-v1.json`/`worktree-results-v1.json`/
`security-results-v1.json` (consumed as immutable predecessor evidence, not
replayed).
