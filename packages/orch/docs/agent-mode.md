# Agent mode: an agent chooses the pieces of work and conducts them

The procedure for an agent that does not follow a fixed command line: it asks the work source which
pieces may run now, hands the chosen lane to the conductor, watches the run and decides what to do after a stop. The
agent decides; every step is a command with a closed output, so nothing here needs a model.

Run it through the project launcher (`python3 -I .swissknifeman/launcher.py orch conduct ...`; `swissknifeman project init` writes it once). The work source of the plan engine in use says which pieces are ready;
its bridge documents the exact command and the fields of its answer (for the planner: the section "Agent mode" of
`bridges/planner-orch/README.md`).

## Terms

"Orchestration" means `orch conduct`: the conductor starts the roles of a run itself, so an agent that is asked to
orchestrate a plan runs `orch conduct run` and watches it. Driving the pieces by hand (starting, finishing and
committing them itself, with the Agent tool as the executor) is manual execution; it is a fallback for a conductor that
cannot start, and each such piece is recorded as a deviation in the journal of the work source. A plan says what to do
and how it is proved; it does not prescribe the executor, its model or the review loop (those come from the route and
review of a piece and from the run options). A piece started by hand is owned by that session until
`orch conduct run --adopt` takes it over.

## 1. Ask for the lanes

Ask the work source which pieces may start now, for at most `N` parallel lanes. The answer must give, per lane, the pieces
to conduct in order (`items`) and what is running, in conflict, waiting or deferred; its structure is pinned by a golden file
in the tests of the plan engine, so this procedure cannot go stale silently.

Take a lane that runs pieces. One lane is one run: its items are conducted in order, and two lanes never touch the same
paths (the conflicts of the answer say which pieces were left out for that). A lane that is planning work, not pieces, is
not a conductor run. An empty list of lanes with waiting entries means nothing is ready: read the reasons, do not guess.

## 2. Conduct the lane

From the root of the project, on a clean working tree:

```text
python3 -I .swissknifeman/launcher.py orch conduct run --plan <plan> --items <item> [<item> …] [--options FILE]
```

`--dry-run [--scenario S]` first shows the routes, their availability and the merged options without claiming anything.
For parallel lanes use one worktree and one branch per lane; the conductor of a lane works in its own tree. Items outside a plan: `orch conduct run --input FILE` (see `conductor.md`).

## 3. Watch

```text
python3 -I .swissknifeman/launcher.py orch conduct status [--run RUN] [--json]     # state, the current step, the last beacon, the agent runs
python3 -I .swissknifeman/launcher.py orch conduct observe [--run RUN] [--follow]  # the observer report; --follow prints the notable lines
python3 -I .swissknifeman/launcher.py orch conduct questions [--run RUN] [--json]  # open questions of the executor and their age
```

A beacon (`STAGE_SLOW`, `STAGE_IDLE`, `CHECK_SLOW`, `BUDGET_OVER`, `LIMIT_OVER`, `RUN_SLOW`, `RESULT_SILENT_DENIAL`,
`QUESTION_QUEUED` …) is a report, not a stop: look at what runs and decide. Exit code 0 means the run finished, 1 it
stopped (`CODE: message` on stderr, the code is in `status`), 130 it was interrupted. `stop` in `status --json` and in the state file belongs to a run that is stopped now; a `resume` moves it to `last_stop` (`code`, `message`, `resume` number), so a finished run has no `stop`.

## 4. After a stop

| Stop | What to do |
| --- | --- |
| `ITEM_BLOCKED` with an escalation (a question, `CHECKS_RED`, `REVIEW_LIMIT`, …) | read the escalation in the report of the piece. A question of the executor (`QUESTION: <id> …`): `orch conduct answer --run RUN --item ITEM --question ID (--option ID \| --text T)`, then `resume --run RUN --retry ITEM` (a plain `resume` does not take a blocked piece back). Anything else: amend the plan (or give what is missing), reopen the item in the work source, then `resume --retry ITEM` |
| `PROVIDER_QUOTA`, `PROVIDER_AUTH`, `PROVIDER_AUTHZ` | fix the account or wait for the reset the message names, then `resume --run RUN` |
| `ROLE_FAILED`, `ROLE_OUTPUT_*`, `OPTIONS_INVALID`, … | fix the cause named in the message (provider, options, the work itself), then `resume --run RUN` |
| `WORKTREE_DIRTY` | the tree holds changes the run did not make: commit or set them aside; `run --adopt` takes over an earlier attempt of the first piece |
| the piece was finished or given up outside the conductor | `orch conduct settle --run RUN --item ITEM --outcome done\|done_with_deviations\|blocked --reason TEXT` |
| the run died before any work began | `orch conduct release --run RUN --item ITEM` gives the claim back |

```text
python3 -I .swissknifeman/launcher.py orch conduct resume --run RUN [--retry ITEM …]
```

`resume` repeats no closed step; `--retry ITEM` takes a blocked piece back from the executor round that reported
`blocked` (the answers to its questions reach the executor only while the input of the piece is unchanged).

## 5. Then

When the lane is done, ask the source again (step 1): it decides what is ready, not the agent's memory of the last run.
Findings of a closed piece are recommendations, not new work of the run.
