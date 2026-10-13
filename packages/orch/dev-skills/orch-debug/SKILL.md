---
name: orch-debug
bucket: repository-bootstrap
version: 0.2.0
description: "Debug-mode protocol for an agent that drives the orch conductor run by run (team-lead observer): estimate, watch the beacons, measure, fix the mechanism, log, hand the logs to a final reviewer. Activate ONLY when the user names this skill; without it the agent is a plain supervisor."
when_to_use: "Only on an explicit request to run orch in debug mode (for example 'use orch-debug' or '/orch-debug'); never by inference from a plan or a conductor command."
risk: write
persona: oss-dev
tags: [orch, conductor, debug, observer, root-bootstrap]
requires: []
produces_for: []
outputs: [chat, "docs/orch-*-run-findings.md", "docs/orch-*-observer-journal.md"]
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# orch debug mode (team-lead observer)

Internal skill. It changes the role of the agent that starts and watches `conduct.py` runs: without this skill the
agent is a plain supervisor (start a run, report its progress, stop on an error code, change nothing in the package).
With it the agent is a team lead: it watches the work of the role agents, measures it, fixes the mechanism in the
package, and leaves a record that a later reviewer can audit. Never activate it on your own.

## Invariants

- **Useful work is never discarded or cut.** The conductor stops nothing for being long: it prints beacons
  (`STAGE_SLOW`, `STAGE_IDLE`, `CHECK_SLOW`, `BUDGET_OVER`, `LIMIT_OVER`) that say what runs now. On a beacon, look at
  what it names: a test run or a build in progress is healthy, wait; a silent model call with no child process for a
  long time, or a loop of the same command, is not. Never kill a working role and never reset a working result to get
  a "clean" run. A blocked piece with good work continues with `resume --retry` after the plan is fixed, a dirty tree
  with an earlier attempt with `run --adopt`, a piece finished by hand with `settle`.
- **One item per run, one item at a time.** After the item closes: analyze, improve, log, only then start the next.
- **The main tree is the conductor's.** While a run is active change no file in it, not even a journal. Develop fixes in a
  separate git worktree, merge between items. Commit only with explicit paths (`git commit -- <paths>`); never sweep the
  index. Run `python3 scripts/public-hygiene.py` before committing documents (no concrete plan ids in committed docs).
- **Fix at the root, as a configurable option.** A package change gets a schema entry, docs, a test that fails without the
  fix, and `python3 scripts/affected-tests.py --tier full --run` green (it runs the touched units and the bridges that
  require them). No hardcoded patch.
- **Only the owner changes machine state** (installing or logging in a provider CLI, credentials, pushes). Ask for it plainly.
- **Each role gets only the instructions of its own prompt** (`instructions.isolate_roles`, default every role; the
  module rules arrive as a short Repository rules block). Check in the prompts of the first item that the block is there.

## Per item loop

1. **Preflight.** Tree clean (or `--adopt` on purpose), item `todo`, `conduct.py run --dry-run --scenario S --options F`
   shows every route with `available: true` and the isolation flags. The run itself refuses to start a piece when a
   required role cannot start. Monitors: `tail -n0 -F err | grep --line-buffered -E '"event": "(stage.end|info|item.end|run.end)"'`
   (no `cut` in the pipe: it buffers and the events never arrive); one monitor per run, stop the old one first.
2. **Estimate before the run.** `python3 packages/orch/scripts/estimate.py --input <the item's input.json> --effort E`
   (or `--cmd` per acceptance command): the history medians of the roles and the measured seconds of the same
   commands. Write it down; after the run compare each step; a deviation over 30% needs a recorded cause.
3. **Watch.** Arm the completion monitor (`Monitor`, unbounded `tail -F` of the run log, filter on `run end|item end|STAGE_|CHECK_SLOW|BUDGET_OVER|LIMIT_OVER|RESULT_|WORKTREE|Traceback|stopped`, max timeout, re-arm on expiry) in the SAME turn as the run start — never start a run without it, and report the end of every item in the chat at once; the owner must never learn of a finished item before you. Status on every notification and at least every 30 minutes (`conduct.py status` prints the latest beacon of
   the running step). Answer each beacon by its content, not by its clock.
4. **Before the commit.** The conductor reads the changed paths from git and reports paths outside the write set as a
   deviation (shown to the reviewer, committed with the piece); review that list and widen the plan for the next items
   like this one.
5. **Profile.** `packages/orch/scripts/step-profile.py <stream>` for each role step (model wait vs commands, own test runs,
   polling waits, reads through Bash; grok streams are timed by their `.times` file) and
   `packages/orch/scripts/run-usage.py <run>` for time and tokens per role; `observer.md` of the run counts the beacons,
   the mends (`RESULT_HEALED`, `RESULT_REPAIRED`) and the share of the wall time spent in checks.
6. **Analyze and fix** what slowed or broke the item; test, document, commit, merge to the branch.
7. **Log** (below), then start the next item. An item is not closed for the observer until its metrics row is complete: estimate versus actual, step profile, deviations, block of Repository rules; an empty cell is written as «not measured» with the reason, never skipped silently.

## Metrics per item

Record for every item, in one table row: wall time and the estimate; executor, review, checks and correction minutes;
checks share of the wall time; check rounds and review rounds (and `LIMIT_OVER` count); repeats of roles; heals and
repairs; beacons by code; fresh tokens in/out per role; deviations (paths outside the write set); confirmed and rejected
findings by severity, and the rejected Majors (each is a plan note). A metric that grows from item to item is a finding.

## What to log (for a final reviewer and for correcting instructions)

- Defects: numbered entries with symptom, cause, fix (commit), what to rethink.
- Per item: disputed decisions (rejected findings, deviations, work outside the write set, corrections not re-reviewed), with
  where to look.
- Instructions that caused or failed to prevent a failure and what to change in them.
- Time and tokens per role and step; the estimate-versus-actual table; the observer's own mistakes.
- A chronological journal of actions and decisions of the observer, written when they are made.
- At the end of the run: a prompt for the reviewer model that links these files and lists the open questions.

## Where things are

- Findings and tables: `docs/orch-*-run-findings.md`; observer journal: `docs/orch-*-observer-journal.md`.
- Options (`review.*`, `checks.*`, `scope.*`, `instructions.*`, `limits.*`) and beacons: `packages/orch/docs/conductor.md`.
- Tools: `packages/orch/scripts/estimate.py`, `run-usage.py`, `step-profile.py`; `scripts/affected-tests.py`.
- Editing this skill: follow the `skill-authoring` workflow (registry, `golden.py check`, affected tests).

## Provenance (root-bootstrap, P1.2)

Class-A private/source-only root-bootstrap identity (D31/D38):
canonical source is this `SKILL.md`; thin projections —
`.claude/skills/orch-debug/SKILL.md` and `.agents/skills/orch-debug/SKILL.md`
(generated by `skiller registry`, never hand-edited). Bucket `repository-bootstrap` is
private/source-only: never published as an ordinary unit/core/marketplace entry, never
vendored/connected into a consumer project.
