---
name: orch-debug
bucket: repository-bootstrap
version: 0.4.0
description: "Debug-mode protocol for an agent that drives the orch conductor run by run (team-lead observer): estimate, watch the beacons, measure, fix the mechanism, log, hand the logs to a final reviewer. Activate when the user names this skill or a run prints the DEBUG_MODE beacon ([orch] debug = true, --debug); otherwise the agent is a plain supervisor."
when_to_use: "On an explicit request to run orch in debug mode ('use orch-debug', '/orch-debug', 'conduct with --debug') or when a conductor run prints DEBUG_MODE; never by inference from a plan alone."
risk: write
persona: oss-dev
tags: [orch, conductor, debug, observer, root-bootstrap]
requires: []
produces_for: []
outputs: [chat, "<run>/debug/*.md", "docs/orch-*-run-findings.md", "docs/orch-*-observer-journal.md"]
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# orch debug mode (team-lead observer)

Internal skill. It changes the role of the agent that starts and watches `conduct.py` runs: without this skill the
agent is a plain supervisor (start a run, report its progress, stop on an error code, change nothing in the package).
With it the agent is a team lead: it watches the work of the role agents, measures it, fixes the mechanism in the
package, and leaves a record that a later reviewer can audit. Never activate it on your own.

## Switching it on

Debug mode is one setting, `[orch] debug` (boolean, default `false`), read like every `[orch]` key, the most
specific layer winning:

| Level | Where | Example |
|---|---|---|
| machine | `~/.config/swissknifeman/config.toml` | `[orch]` `debug = true` — every run of this machine |
| project | `<project>/.swissknifeman/config.toml` | `[orch]` `debug = false` — this project, over the machine |
| run | `conduct.py run ... --debug` / `--no-debug` (also `resume`) | this run only, over both |

`SKM_ORCH_DEBUG=true` and a `--config FILE` sit between the project and the flag. With it on, the run prints
`DEBUG_MODE` right after `run.start` (and after every resume): the layer that switched it on, this file, and the run's
journal folder `<runs>/<run>/debug/` with `journal.md`, `metrics.md` and `findings.md` skeletons (created once, a
resume keeps them). That beacon is the cue to follow this protocol. The roles, their prompts and every decision of
the conductor are the same with the mode on or off: it changes only what the observer does and where it writes.
The run folder is outside the tracked tree, so writing the journal there does not break "the main tree is the
conductor's"; copy the finished journal and findings into the plan or `docs/` after the run.

## Invariants

- **Useful work is never discarded or cut.** The conductor stops nothing for being long: it prints beacons
  (`STAGE_SLOW`, `STAGE_IDLE`, `CHECK_SLOW`, `BUDGET_OVER`, `LIMIT_OVER`) that say what runs now. On a beacon, look at
  what it names: a test run or a build in progress is healthy, wait; a silent model call with no child process for a
  long time, or a loop of the same command, is not. Never kill a working role and never reset a working result to get
  a "clean" run. A blocked piece with good work continues with `resume --retry` after the plan is fixed, a dirty tree
  with an earlier attempt with `run --adopt`, a piece finished by hand with `settle`.
- **One run = one roadmap batch, one executor session.** Start the pieces of a roadmap row together (`run --items A B C D`, never one run per item): by default (`--batch`, `session.executor: shared`) all pieces go in progress together and the executor keeps ONE session across them, knows the whole batch from the first prompt and builds each piece on the earlier ones; checks, review, register and commit stay per piece. One common review per batch after the last piece: `packages/orch/scripts/batch-review.py RUN` (grok, `--effort medium` when the diff is small); fix Major+ in a separate commit. `--no-batch` is for a deliberate separate-session start; `--ready` (not `--batch`) selects the next ready pieces. When a piece closes: measure, log, fix the mechanism in a separate worktree and merge between pieces; the run itself goes on.
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

1. **Preflight.** Decide per item whether review is needed and with which settings (`review.*`, model, effort, rounds), pass them with `--options FILE` and write the choice with its reason into the journal; never take the default by habit. Tree clean (or `--adopt` on purpose), item `todo`, `conduct.py run --dry-run --scenario S --options F`
   shows every route with `available: true` and the isolation flags. The run itself refuses to start a piece when a
   required role cannot start. Monitors: `tail -n0 -F err | grep --line-buffered -E '"event": "(stage.end|info|item.end|run.end)"'`
   (no `cut` in the pipe: it buffers and the events never arrive); one monitor per run, stop the old one first. Keep the options file, the journal and the logs outside `/tmp` (a disk cleanup wipes it, and `resume` re-reads the options path of the run).
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

- While the run goes: `<runs>/<run>/debug/` (named by the `DEBUG_MODE` beacon). After it, the committed copies:
  findings and tables `docs/orch-*-run-findings.md`, observer journal `docs/orch-*-observer-journal.md`.
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
