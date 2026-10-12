---
name: orch-debug
bucket: repository-bootstrap
version: 0.1.0
description: "Debug-mode protocol for an agent that drives the orch conductor run by run (team-lead observer): estimate, watch, profile, fix, log, hand the logs to a final reviewer. Activate ONLY when the user names this skill; without it the agent is a plain supervisor."
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

- **Useful work is never discarded or cut.** No kill for wall-clock length (a role is stopped only when its output is
  silent: `limits.stage_idle_timeout_s`), no reset of a working result to get a "clean" run. A finished item stays as it
  is; optimizations apply to the next item. Reset only a result that is wrong in substance.
- **One item per run, one item at a time.** After the item closes: analyze, improve, log, only then start the next.
- **The main tree is the conductor's.** While a run is active change no file in it, not even a journal. Develop fixes in a
  separate git worktree, merge between items. Commit only with explicit paths (`git commit -- <paths>`); never sweep the
  index. Run `python3 scripts/public-hygiene.py` before committing documents (no concrete plan ids in committed docs).
- **Fix at the root, as a configurable option.** A package change gets a schema entry, docs, a test that fails without the
  fix, and `scripts/test.sh` + `scripts/validate.sh` + `python3 scripts/ecosystem-units.py check` green. No hardcoded patch.
- **Only the owner changes machine state** (installing or logging in a provider CLI, credentials, pushes). Ask for it plainly.
- **Each role gets only the instructions of its own prompt** (`instructions.isolate_roles`); check this for every provider
  the run uses (Claude Code reads the repository `CLAUDE.md` and project memory by itself; probe other providers).

## Per item loop

1. **Preflight.** Tree clean, item `todo`, provider probe passes (the same argv as the catalog with a one-line prompt), the
   monitor works on a test line. Monitors: `tail -n0 -F err | grep --line-buffered -E '"event": "(stage.end|info|item.end|run.end)"'`
   (no `cut` in the pipe: it buffers and the events never arrive).
2. **Estimate before the run.** From the scope (files, checks, route) and the earlier items write down the expected duration
   per step and tokens. After the run compare each step with its estimate; a deviation over 30% needs a recorded cause.
3. **Watch.** Status on every notification and at least every 30 minutes. A step with no new stream line for the idle limit is
   stuck; a long step with a live stream is working.
4. **Before the commit.** Compare `git status` with the item's `task_files` (a path outside the write set refuses the
   commit); add legitimate paths to the plan, never use `--leave-outside` to hide a file.
5. **Profile.** `packages/orch/scripts/step-profile.py <stream>` for each role step (model wait vs commands, own test runs,
   polling waits, reads through Bash) and `packages/orch/scripts/run-usage.py <run>` for time and tokens per role.
6. **Analyze and fix** what slowed or broke the item; test, document, commit, merge to the branch.
7. **Log** (below), then start the next item.

## What to log (for a final reviewer and for correcting instructions)

- Defects: numbered entries with symptom, cause, fix (commit), what to rethink.
- Per item: disputed decisions (rejected findings, deviations, work outside the write set, corrections not re-reviewed), with
  where to look.
- Instructions that caused or failed to prevent a failure and what to change in them.
- Time and tokens per role and step; the estimate-versus-actual table; the observer's own mistakes.
- A chronological journal of actions and decisions of the observer, written when they are made.
- At the end of the run: a prompt for the reviewer model that links these files and lists the open questions.

## Editing this skill

The projections (`.claude/skills/orch-debug`, `.agents/skills/orch-debug`, `bootstrap/publication-lock.json`) are generated.
After a change to `SKILL.md`: `bash packages/skiller/bin/skiller registry`, then `python3 scripts/golden.py check`; when it
reports the generated files as not in the digests, `python3 scripts/golden.py capture --only skiller-registry --reason "..."`
and commit those goldens with the skill (a red `golden.py check` turns the acceptance check of every following item red).

## Where things are

- Findings and tables: `docs/orch-*-run-findings.md`; observer journal: `docs/orch-*-observer-journal.md`.
- Options (`review.*`, `checks.*`, `instructions.*`, `limits.*`): `packages/orch/docs/conductor.md`.
- Tools: `packages/orch/scripts/run-usage.py`, `packages/orch/scripts/step-profile.py`.

## Provenance (root-bootstrap, P1.2)

Class-A private/source-only root-bootstrap identity (D31/D38):
canonical source is this `SKILL.md`; thin projections —
`.claude/skills/orch-debug/SKILL.md` and `.agents/skills/orch-debug/SKILL.md`
(generated by `skiller registry`, never hand-edited). Bucket `repository-bootstrap` is
private/source-only: never published as an ordinary unit/core/marketplace entry, never
vendored/connected into a consumer project.
