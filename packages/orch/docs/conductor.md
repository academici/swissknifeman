# Conductor

Before claiming named plan items, run `orch conduct preflight --plan PLAN --items REF...` with the same invocation
configuration intended for the run. The read-only work-source `inspect` operation supplies each item's real execution
input, scenario and option layers. No claim, stored brief or model request is made. Every item is checked even when an
earlier one is refused; JSON `admitted: false` returns exit 1. Optional scout/repair refusals are reported separately.
An enabled advisor is required: disable it explicitly when the selected provider cannot run that role.
Invocation `--options`, `--scenario`, `--batch`, `--fence` and `--allow-path` retain their usual precedence.
The result is static admission, not proof of dependency readiness, credentials, live quota or complete delivered input.
Antigravity still requires its separate explicit owner exceptions described below; preflight does not grant them.
`run --dry-run` remains an invocation projection without source items and must not be used as an admission gate.

`orch conduct` (`swissknifeman orch conduct`, or `python3 -I .swissknifeman/launcher.py orch conduct` in a project) takes pieces of work from the work source and drives each one through the roles of its
run-policy until it is green or stops honestly. It is shipped with orch and tuned by configuration and by the run
options of the work; it is never rewritten for a run. The conductor itself decides nothing: it branches only on exit
codes, on the verdicts of the closed role results (`schemas/conductor/v1`) and on the limits of the run options.
Models are used only for the narrow roles: context scout, executor, reviewer, triager and, when asked for, the registrar that records the result.

```text
orch conduct [--config FILE] [--project DIR] run --plan P (--items REF… | --ready [--max-items N]) [--plans-root DIR]
           [--options FILE] [--batch | --no-batch]
           [--fence project|plan] [--allow-path DIR ...] [--adopt] [--detach | --frozen] [--dry-run [--scenario S]]
           [--quiet | --json-lines] [--model-catalog FILE]
orch conduct [--config FILE] [--project DIR] run --input FILE [--commit] [--scenario S] [--options FILE] [--dry-run]
           [--quiet | --json-lines] [--model-catalog FILE]
orch conduct [--config FILE] resume --run RUN [--retry ITEM ...] [--raise-limit KEY=N ...]
           [--fresh-context --options FILE --model-launch-ceiling TOTAL] [--detach | --frozen] [--quiet | --json-lines]
orch conduct settle --run RUN --item REF --outcome done|done_with_deviations|blocked --reason TEXT
orch conduct answer --run RUN --item REF --question ID (--option ID | --text TEXT) [--by WHO]  (without `--by`: the shell user at a terminal, `cli:USER` without one — an agent's answer is never recorded as the owner's)
orch conduct questions [--run RUN] [--json]
orch conduct prompt explain [--run RUN] --item REF --step STEP [--json]
orch conduct prompt diff [--run RUN] --item REF --step STEP [--against RUN:ITEM:STEP] [--json]
orch conduct timeline [--run RUN] [--item REF] [--json]
orch conduct status [--run RUN] [--json]
orch conduct observe [--run RUN] [--follow]
orch conduct gates [--json] [--clear [PROVIDER]]
orch conduct supervise [--run RUN] [--once] [--interval S] [--recover notify|stop-only|resume] [--max-recoveries N] [--json] [--notify-send]
orch conduct supervise --print-systemd-unit [--interval S]
orch conduct supervise --check-systemd-unit [--interval S]
orch conduct reap --run RUN
```

`prompt diff` compares two prompt manifests (`prompt explain`): the step against its previous attempt (`executor.2`
against `executor.1`; a first attempt is `PROMPT_BASELINE_MISSING`) or against `--against RUN:ITEM:STEP`. Blocks are
matched by kind and origin (a block without an origin by kind and order); the answer names each block `added`,
`removed`, `changed` (another digest) or `same` with its tokens on both sides, and the token totals; a missing manifest is
`PROMPT_MANIFEST_MISSING`. `timeline` reads `progress.jsonl` and gives every step of a piece as an interval (`start`,
`end`, `duration_s`, `verdict`, `status`: `done`, `stopped`, `interrupted` when the run ended or was resumed while the
step was open (the resumed step is an interval of its own), `open` while it runs, without an end); gui-orch shows it as
its `timeline` view. With `state.json` at hand a `checks.N` interval also carries `checks` (`--json`): one entry per result
row with `id`, `seconds`, `green`, `skipped`, `skip_reason`, `reused` (plus `executed`, `context`, and for a reused row
`reused_from` and `original_seconds`); the text output prints them under the interval, `  - V3 12.4 s green`,
`  - V5 skipped (fail_fast)`, `  - V2 reused (40 s)`.

For an agent that picks its own pieces (ask the source for ready lanes → `run --items` → `status`/`observe` → `resume`/`settle`) see [agent-mode.md](agent-mode.md).

Exit codes: 0 the run finished, 1 it stopped (or a command was refused; `CODE: message` on stderr), 2 usage,
4 the run waits for a decision (`run.end` outcome `waiting`, status `waiting`: a piece waits for the answer to a question;
`orch conduct answer`, then `orch conduct continue`; code 1 keeps its meaning for every other stop),
130 interrupted (Ctrl-C, SIGTERM or SIGHUP: the role and check processes of the run are killed with their groups; `resume` continues).
A conductor that inherits an ignored SIGINT (started in the background of a shell) still takes SIGINT as an interrupt while its
loop runs, so `autopilot stop` and the supervisor reach it; a SIGINT handler the caller installed is kept.

## Detached runs

`run --detach` and `resume --run RUN --detach` start a conductor in a separate session with stdin closed and output
appended to `<runs root>/detached/<run>.log` (private directory, mode `0700`). Closing the terminal or restarting the GUI
leaves it running. `--detach` excludes `--dry-run` and `--frozen`; `--quiet` and `--json-lines` control the child log.
The parent prints a `conductor/v1` `detach-result` document (`$schema`, `run_id`, `pid`, `log`, `detached: true`) and exits 0
only after the child acknowledges startup. This confirms ownership and initialization; later run outcomes remain visible
through `status` and the log. Pruning a run also removes its detached log.

Each launch uses a fresh nonce and `<runs root>/detached/<run>.<nonce>.ack.json` (`records/v1` `detach-ack`). The child
atomically writes `started` after acquiring the checkout lock and run lease and initializing state (new run: after the
first save; resume: after retry/limit validation, recovery and the saved `run.resume` transition), or `refused` with the original reason code. The parent checks the schema, nonce,
run id and child pid every 0.1 seconds for at most 20 seconds. An existing `run.json` never confirms startup.
A refusal returns exit 1 with its code. A child that exits without acknowledging yields `DETACH_FAILED` and up to twenty
sanitized log lines; a timeout names the pid and log and leaves the child alone. The hidden `--run-id` is restricted to
internal launches (`SKM_ORCH_DETACHED=1`), a correctly formatted id and a run directory that does not exist.
`spawn` sets up the acknowledgement channel itself: it takes an optional `ack_nonce` (16 hex digits; generated when not given,
as for `--detach`; the autopilot gives its launch id), returns `{pid, start_ticks, log, ack, nonce}`, and accepts a per-launch
environment overlay. Roles and checks receive neither that channel nor `SKM_ORCH_DETACHED` / `SKM_ORCH_LAUNCHER` nor the
startup fence variables of the autopilot (below); the owning conductor retains its launcher in leases and events.

The lease and lifecycle events identify the launcher: `detached` from the terminal, `gui` from gui-orch,
`supervisor` from automatic recovery, or `autopilot` for its future caller. The supervisor uses the same session/log
launcher and returns immediately; its action records a spawn, while the child independently acquires ownership.

## Ownership of a run

`run` and `resume` hold local exclusive `flock` locks for the entire command: first the checkout lock under
`<runs root>/checkouts/<sha256(realpath(git toplevel))[:16]>.lock`, then `<run>/lease.lock`. Separate worktrees
have independent checkout locks. Ownership starts before reading `run.json` or `state.json` on resume and before
the first state save of a new run. A second conductor is refused with `WORKTREE_BUSY` or `RUN_BUSY`.
`settle` and `release` take the run lease for their updates; a busy run keeps its state unchanged.

`lease.json` shows the owner's pid, host, start time and command, and its identity: `start_ticks` (Linux
`/proc/<pid>/stat` field 22, `null` without `/proc`), `boot_id` (`/proc/sys/kernel/random/boot_id`, `null` without it) and
`launcher` (`terminal` by default, or `detached`, `gui`, `supervisor`, `autopilot` from the environment variable
`SKM_ORCH_LAUNCHER`; any other value is `terminal`); the checkout's adjacent `.json` also names its run. A process is
identified by `(pid, start_ticks, boot_id)`: a pid alone, which another process may have after a restart or a reuse, is never
a reason to send a signal. These are display metadata: only the kernel lock proves ownership. Metadata is removed before
unlocking. Lock files are never deleted, and their descriptors cannot survive exec into a role. Locks are local to one
host; there is no cross-machine ownership protocol. A lease from before the identity fields reads as before. That the
owner still moves is shown by the heartbeat (next section).

If the conductor dies while the journal says `running`, `status`, `status --json` and `runs` report
`orphaned` / `RUN_ORPHANED` when a separate lock probe succeeds. The probe writes nothing. Runs without the
`run.json.lease` flag keep their legacy status. Resume first stops surviving process groups of unfinished roles,
using each agent's atomic `process.json` (`pid`, `pgid`, Linux `/proc` `start_ticks`, `started_at`). It checks process
identity before signalling, sends SIGTERM, allows 10 seconds, then sends SIGKILL if needed. No new role starts
while that group remains alive. Each stopped group produces an `info` event `ROLE_ORPHAN_KILLED`.
Unfinished agents whose process died or whose group was stopped receive `result.json` with error code `ORPHANED`
and an `orch.agent.failed` event with class `orphaned`. An existing result is preserved, and resume does not emit
the failure again. A reused pid is never signalled; the old agent is closed as orphaned.

`answer` can update questions while the conductor owns the run. All updates of an item's `questions.json` use
`questions.lock` for their read-modify-write, including merging answers before a conductor save. A lock held for
10 seconds gives `QUESTIONS_LOCKED`. `observe`, `status`, `runs` and prompt explanation do not take run ownership; their
probe opens `lease.lock` read-only, and where it cannot open it at all (a read-only context) the run is not called
orphaned: `status --json` says `lease: {"lock": "unavailable"}`.
`prune --apply` skips busy leases with a reason, rereads eligibility under the lease, then renames an eligible old
terminal or orphaned run to `<runs root>/.pruning-<id>` before removing it. The latest run is retained.

## Heartbeat and health

The lease proves who owns a run; `<run>/heartbeat.json` (`records/v1` `heartbeat`, replaced atomically, never locked) proves that
the owner still makes progress. It holds the identity of the conductor (`pid`, `start_ticks`, `boot_id`, `host`), `run_id`, a
`seq` that grows with every write and `at`, and, when known, the piece (`item`), the step (`step`) and the role, the last sign
of progress (`last_progress_at`, `last_progress_kind`: `run_start`, `stage_start`, `stage_end`, `tool_use`, `tool_result`,
`check_evidence`, `tree_change`, `answer`), the size of the stream and when it last grew (`stream_bytes`, `last_growth_at`), the
CPU seconds of the process tree and when they last grew by a second (`tree_cpu_s`, `last_cpu_at`), the command the role repeats
(`repeat`: `command`, `count`) and the blocking call in progress (`waiting`: `kind` one of `work_source`, `provider`, `git`,
`question`, `budget`, `lock`, `subprocess`; `reason_code`; `since`; `deadline`, required for every kind but `question`).

It is written only by the thread of control of the conductor: at every progress line, at every look at a running role or
check (five seconds apart at most; a change of the kind of progress is written at once) and around a blocking call with a
known limit (`waiting`: the call of the work source, up to 600 s; the wait for a provider limit, which also rewrites the
heartbeat every 30 s). There is no timer thread: a stuck main loop must show as a stale heartbeat. A heartbeat that cannot be
written (`OSError`) never stops the run: one `info` line `HEARTBEAT_NOT_WRITTEN` per run says so. `status` and `runs` only
read it; a missing or broken file is a class of its own, never a failure.

Signs of progress besides the size of the stream: the tool steps in it (`tool_use` and `tool_result` of claude-code and grok,
`item.started` and `item.completed` of codex, read from the new bytes only) and the CPU of the process tree of the role or
check (`/proc`, measured at most every 30 s and once more before an idle stop). A tree that spent a second of CPU since the
measure before is at work: the idle timers (`stage_idle_timeout_s`, `check_idle_timeout_s`) and the idle beacons start again,
so a long test run that writes nothing is not stopped, while a sleeping tree still is. Without `/proc` only the growth of the
stream counts, as before.

`STALL_SUSPECTED` and `CHECK_IDLE` are beacons: they stop nothing, only the explicit limits do. A role that runs the same tool
command `limits.stall_repeat_n` times in a row (default 5) gets one `STALL_SUSPECTED` per command; a role whose stream keeps
growing for `limits.stall_window_s` (default 1800) without a tool step gets one every window; a check without output and
without CPU for `limits.check_idle_warn_s` (default 600) gets a `CHECK_IDLE` every such period. 0 switches each off.

`orch conduct status --json` has the field `health` and the text status a line `health: <class> (silent <time>) — <reason>`;
`orch conduct runs --json` has `health` (the class) in every row of a readable run. It is the pure function
`orch.conductor.health.classify` (no IO, no clock of its own) over the journal, the state, the heartbeat and the lease probe;
the first rule that fits decides:

| # | Condition | Class | `reason_code` |
| --- | --- | --- | --- |
| 1 | the run finished | `finished` | |
| 2 | stopped with `PROVIDER_QUOTA` and the journal gives a reset time in the future | `waiting_budget_reset` | `PROVIDER_QUOTA` |
| 3 | the run ended `waiting`, or its state does (a piece waits for an answer) | `waiting_owner` | `WAITING_DECISION` |
| 4 | stopped or interrupted | `stopped` | the stop code |
| 5 | running, the run has a lease flag and nobody holds the lease | `orphaned` | `RUN_ORPHANED` |
| 6 | running, the lease cannot be probed (read-only) | `unknown` | `LEASE_UNKNOWN` |
| 7 | running, no heartbeat (a run from before heartbeats, or its first seconds) | `running` | `HEARTBEAT_MISSING` (in `detail`) |
| 7 | running, a heartbeat that cannot be read | `unknown` | `HEARTBEAT_INVALID` |
| 8 | pid, `start_ticks` or `boot_id` of the heartbeat differ from the lease owner's | `suspected_stall` | `HEARTBEAT_OWNER_MISMATCH` |
| 9 | the heartbeat waits for a question | `waiting_owner` | `QUESTION_WAITING` |
| 10 | a wait whose deadline has not passed (however old the heartbeat) | `waiting_provider` (kind `provider`) or `waiting_tool` | `PROVIDER_WAIT` or the reason of the wait |
| 11 | a wait more than `hung_after_s` past its deadline | `hung` | `HEARTBEAT_STALE` |
| 12 | a wait more than 60 s past its deadline | `suspected_stall` | `WAIT_DEADLINE_PASSED` |
| 13 | a wait just past its deadline | `waiting_tool` | the reason of the wait |
| 14 | no wait, the heartbeat older than `hung_after_s` | `hung` | `HEARTBEAT_STALE` |
| 15 | a role runs, the last tool step is older than `stall_window_s`, and the CPU did not grow for that long or the command was repeated `stall_repeat_n` times | `suspected_stall` | `STALL_SUSPECTED` |
| 16 | otherwise | `running` | |

The thresholds are `hung_after_s` 300 and, for rule 15, `stall_window_s` and `stall_repeat_n` of the piece the run is on (its
`options.json`, else the defaults). Only `hung` is a reason to stop a conductor (the supervisor, next section): a wait with a deadline in
the future is protected, because the call of the work source may take ten minutes without a line. `suspected_stall` is for a
person to look at. A run from before heartbeats, and a lease without the identity fields, are read as before.

## Supervisor

The heartbeat tells that a conductor stopped moving, the lease that it is gone; the supervisor (`orch conduct supervise`, the library
`application/supervisor.py`) acts on the classes of *Heartbeat and health*, within a policy. `reap` is its one safe step on its own.

```text
orch conduct supervise [--run RUN] [--once] [--interval S] [--recover notify|stop-only|resume] [--max-recoveries N] [--json] [--notify-send]
orch conduct reap --run RUN
```

`supervise` looks at every run of the project once (`--once`) or every `--interval` seconds (default `[orch.supervisor] interval_s`,
60) until SIGINT or SIGTERM; `--run` limits it to one run. `--json` prints each pass as a `conductor/v1` `supervise-result`
(`busy`, `recover`, `actions`). One supervisor serves a project: `<runs root>/supervisor.lock` is taken without waiting, and a
second supervisor prints `{"busy": true}` (text: `busy: another supervisor holds this project`), does nothing and exits 0.
`reap --run R` stops the role processes an orphaned run left and closes their agent records; exit 0, or 1 with `RUN_BUSY` /
`WORKTREE_BUSY` while a conductor holds the run or the checkout, `RUN_UNKNOWN` for a run that is not there.

**Policy.** `[orch.supervisor] recover` is `notify` (default: say so and do nothing else), `stop-only` (also stop a hung
conductor and reap the processes of a dead one) or `resume` (also resume a dead run). The order is `notify` < `stop-only` <
`resume`, and the effective value is the lowest of the machine value (the default when the machine sets none) and the
invocation values (`--config` file, `--recover`): a flag can only weaken what the machine allows. `max_recoveries` follows the
same rule (`--max-recoveries` can only lower it). A project file cannot set `recover`, `max_recoveries` or `window_s`
(`CONFIG_LAYER_FORBIDDEN`): what a machine does on its own is the owner's decision. `interval_s`, `hung_after_s` (age of
the heartbeat of a conductor that waits for nothing, default 300), `grace_s` (default 60) and `notify_send` are set in every layer.
Machine policy for a supervisor that recovers:

```toml
[orch.supervisor]
recover = "resume"
max_recoveries = 2
window_s = 3600
```

**Classes and actions.** A pass classifies each run that is not finished (`runs.health_of`, with `hung_after_s`) and acts as follows;
a bounded wait with a deadline in the future (`waiting_provider`, `waiting_tool`) is never touched, however old the heartbeat is.

| Class | `notify` | `stop-only` | `resume` |
| --- | --- | --- | --- |
| `running`, `waiting_provider`, `waiting_tool`, `waiting_budget_reset`, `stopped`, `finished`, `unknown` | nothing | nothing | nothing |
| `waiting_owner` | a notification when a question waits past `limits.question_warn_s` | same | same |
| `suspected_stall` | a notification, never a signal | same | same |
| `hung` | a notification | `snapshot`, `stop`, and when the lease is free: `reap` | `snapshot`, `stop`, `reap`, `resume` |
| `orphaned` | a notification | `reap` | `reap`, `resume` |

Each action is a line of `<run>/supervisor.jsonl` (`records/v1` `supervisor-action`: `at`, `run_id`, `health`, `reason_code`, `action`,
`detail`, and `pid` and `signal` for a stop), written and flushed before the next step. The `action` is one of `notify`, `snapshot`,
`stop`, `reap`, `resume`, `given_up`, `identity_mismatch` and `busy`. The same trouble is said once: while the class and the
count of resumes stay the same, a notification, a refused identity, a `busy` or an empty `reap` is not repeated.

**Stopping a hung conductor.** Before any signal the supervisor writes `<run>/supervisor/snapshot-<UTC>.json` (`records/v1`
`supervisor-snapshot`: the health, what `status --json` prints, `heartbeat.json`, `lease.json`, the last 50 lines of the journal and the
processes of the conductor tree and of the role groups of `process.json`: `pid`, `ppid`, `pgid`, `stat`, `cpu_s`, `args` up to 200
characters; everything passes the redaction of the status display). It then sends SIGINT and waits up to `grace_s` for the run lease to
be freed, then SIGTERM and `grace_s`, then SIGKILL. A signal goes to the one pid the lease names (`os.kill`, never a group: a
conductor started from a terminal shares its process group with the shell), and only while `(pid, start_ticks, boot_id)` of
`lease.json` still match `/proc` and the boot of the machine, `pid` is not the supervisor's own and the lease is held. Any other
case is `identity_mismatch` and **nothing is sent**; an older lease without `start_ticks` or `boot_id` is such a case. The role
groups, which live in sessions of their own, are not signalled here: `reap` stops them. A conductor that handles SIGINT ends the
run `interrupted`; the pass then stops there (the run is `stopped`, not orphaned), and the owner resumes it.

**Reap and resume.** `reap` takes the checkout lock and the run lease without waiting, like a resume, and runs the recovery of
`resume` that is already there: `recovery.kill_orphaned_roles` stops each role group of an unfinished step whose `process.json`
still matches (pid, `start_ticks`, own group) and closes the agent records of dead or stopped roles as `ORPHANED` with the
`orch.agent.failed` event. It writes no heartbeat, no state and no step. A lease a live conductor holds is `RUN_BUSY` (the pass
records `busy` and goes on); the supervisor never takes the lease of a live run. `resume` then starts `orch conduct resume --run R`
as a process of its own (new session, no terminal, `SKM_ORCH_LAUNCHER=supervisor`, output in `<runs root>/detached/<run>.log`); it
takes the locks itself and continues from the receipts of the closed steps (I4), so a commit or a registration is never repeated.
A run is **not** resumed when its last stop (`state.stop`, else `state.last_stop`, else the journal) is one of
`STAGE_RECOVERY_UNKNOWN`, `TOKEN_BUDGET`, `STATE_CORRUPT`, `OPTIONS_INVALID`, `OPTIONS_UNTRUSTED`, `SANDBOX_UNAVAILABLE`,
`PROVIDER_AUTH` and `PROVIDER_AUTHZ`: the pass reaps and says why (`notify`).

**The breaker.** `<runs root>/supervisor-state.json` (`records/v1` `supervisor-state`, replaced atomically under `supervisor.lock`)
keeps per run the times of the resumes the supervisor started (`recoveries`), when it gave up (`given_up`) and the last class and action. When
`max_recoveries` resumes lie within `window_s`, the next recovery is `given_up`: the run is reaped, not resumed, and not touched again
until the owner resumes it by hand (a `run.resume` in the journal that the supervisor did not start closes the breaker and forgets
the recoveries). A damaged `supervisor-state.json` stops the pass with `STATE_CORRUPT` and nothing is done: the breaker must not forget.

**Records and events.** Besides `supervisor.jsonl`, every action except `snapshot` and `busy` is an `info` line of the journal, and
every action is an `orch.conductor.health` event (see [events](events.md); `[orch.events] enabled` gates it). These codes are not
stops or beacons:

| Code | Action | Meaning |
| --- | --- | --- |
| `SUPERVISOR_NOTIFIED` | `notify`, `identity_mismatch` | the supervisor saw trouble it does not act on, or refused to signal a process that is not the lease owner |
| `SUPERVISOR_STOPPED` | `stop` | the hung conductor freed the lease after the signal named in the line |
| `SUPERVISOR_REAPED` | `reap` | orphaned role groups were stopped and their agent records closed |
| `SUPERVISOR_RESUMED` | `resume` | a detached `conduct resume` was started (pid and log in the line) |
| `SUPERVISOR_GAVE_UP` | `given_up` | the breaker opened; resume by hand |

`--notify-send` (or `[orch.supervisor] notify_send`) also calls `notify-send "SKM run <id>: <health>"` for a notification, a stop and
a given-up run; a missing command or a failure is ignored. A recovery that has started the resume is up to that process: the
supervisor does not wait for it and does not write the state of the run. The detached start uses `infrastructure/detach.spawn`, shared with the CLI.

### A systemd user timer

`orch conduct supervise --print-systemd-unit [--interval S]` prints a oneshot service and timer with file headers
under `~/.config/systemd/user/skm-supervise-<project-key>.{service,timer}`. The key is the first twelve hex digits of
SHA-256 of the real project path. `ExecStart` uses the absolute `swissknifeman` found on PATH and runs
`orch conduct --project <project> supervise --once`; the timer starts after 120 seconds and repeats every S seconds
(default: the supervisor interval). Paths are escaped for systemd, including spaces and specifiers.
`SUPERVISE_UNIT_UNAVAILABLE` (exit 1) means the executable is unavailable or verification could not start.

`--check-systemd-unit` prints the same text and invokes `systemd-analyze --user verify` on both files in a temporary
directory; its exit code is returned. Without that tool it prints `systemd-analyze not found: unit text printed only`
and exits 0. Neither command installs units, enables timers or changes a running service. The owner installs the
printed files and enables the timer when desired.

## Autopilot

The autopilot (`orch conduct autopilot`, the controller `application/autopilot.py`, its rules `policies/autopilot.py`) works
through a plan lane after lane without the owner and without a model: it asks the work source which lane comes next, checks
that exactly the phase of that lane is ready, starts one conductor run for the lane, waits for it and decides from how it
ended whether to go on, to continue, to resume or to stop. A `conduct run --ready` takes one lane and exits; the autopilot
starts a run per lane. It never calls a model and never reads the streams of the roles: a semantic question is answered
inside the run (questions, advisor, panel), a decision the run leaves to the owner is a stop with one action in its message.

```text
orch conduct autopilot start --plan P [--phase Pn] [--wait-blocked] [--max-runs N] [--max-wall-s S] [--run-tokens-hard-max T] [--detach] [--json-lines]
orch conduct autopilot status [--json]
orch conduct autopilot pause | resume | drain | stop
orch conduct autopilot explain [--plan P] [--json]
```

A monitor of an agent that drives the autopilot (a tool with a timeout of its own) expires while the run goes on: an expired monitor says nothing about the run, so the check text is "finished, waiting or stopped: report; otherwise re-arm" and `orch conduct status --run RUN` is read again by hand.

`start` runs the controller in the foreground until a stop code (`--detach`: in a session of its own, printing a
`detach-result` once the controller holds its lock; progress lines go to `<runs root>/detached/<label>.log`). `status` shows
the session (`--json`: a `conductor/v1` `autopilot-status` with `status` `none`, `running`, `paused`, `draining`, `stopped`
or `dead`: a session that did not stop and whose controller no longer holds the lock). `pause` takes no new work after the
current run, `resume` takes work again, `drain` lets the current run end and stops, `stop` interrupts the current run: they
write `<runs root>/autopilot.request.json`, which the controller reads and removes at its next look; without a live controller
they refuse with `AUTOPILOT_NOT_RUNNING` (exit 1). `explain` prints the effective policy with the layer of each value, the
readiness answer of the source and the next action a controller would take now (`--json`: `autopilot-explain`); it starts and
writes nothing.

`start --phase Pn` restricts new lanes to that exact phase and requires its readiness even if configuration disables the
readiness check. The source must name the phase: an absent or different phase stops with `AUTOPILOT_PHASE_BOUNDARY` (exit 1),
without launching the lane. A waiting run or source stops with `AUTOPILOT_PHASE_WAITING`, a blocked run with
`AUTOPILOT_PHASE_BLOCKED` (exit 1); `terminal` or `archive` stops with `AUTOPILOT_PHASE_COMPLETE` (exit 0). Other readiness
failures retain their normal codes. The phase is recorded in `autopilot.json`, shown by `status`, passed through detach and
retained on restart, including recovery and answered runs. An unfinished session cannot change its phase or adopt unbounded
work with a new phase (`AUTOPILOT_PHASE_CONFLICT`); a stopped session with no outstanding run can explicitly start a different
phase. Omitting the flag on restart retains an existing boundary. Without the flag on a new session the existing behavior applies.

With `--phase Pn --wait-blocked`, a phase waiting or blocked result keeps the controller alive and records `phase_wait` in
its state. It polls at `poll_s`; each saved run must confirm its relevant items are no longer blocked, and the source must select a ready lane of the same phase before a new run starts. Other blocked items remain outstanding across lanes, including while a later run waits for answers or becomes blocked itself; their run references survive recovery.
An answered run also needs a clear run blocker and phase readiness before continuation. Source refusals stop with
`AUTOPILOT_NOT_READY`; phase boundaries, requests and budgets remain in force. The option and outstanding wait survive
detach and recovery. A stopped session with an outstanding wait retains its phase boundary.
`explain` reports a saved phase hold while it awaits the controller's next evaluation; the controller rechecks run evidence and
readiness before releasing it. A run finished by hand releases an answer wait only after its lease is free, and closed or still
blocked items cannot be relaunched from a stale lane.

**Policy.** `[orch.autopilot]` (see [configuration](configuration.md)): `allowed` (default `false`) is set by the machine
only: a project file that sets it is refused by the configuration (`CONFIG_LAYER_FORBIDDEN`), the project layer is then left
out and the session stops with `AUTOPILOT_NOT_ALLOWED` unless the machine allows it. `enabled` (default `false`) is the
project's switch (the machine may set it for every project). `require_readiness` (default `true`) is on when the machine or
any other layer turns it on. `max_runs` (20), `max_wall_s` (43200), `max_no_progress_runs` (2), `max_auto_decisions` (10),
`quota_wait_max_s` (21600) and `max_recoveries` (1, per run) are the lowest of the machine value and the values of the other
layers and the flags of `start`: a project or a flag can only narrow. `poll_s` (30) is the pause between two looks. Machine
policy of an owner who lets the autopilot run:

```toml
[orch.autopilot]
allowed = true
```

and in the project `.swissknifeman/config.toml`: `[orch.autopilot] enabled = true`.

**The loop.** One controller per checkout holds `<runs root>/autopilot.lock` (taken without waiting; a second `start` stops
with `AUTOPILOT_BUSY` and touches nothing). Then, at every step:

1. A request is applied; a stop request or a passed deadline interrupts the current child (below).
2. A current run is watched every `poll_s` with `health.classify`: `hung` is stopped by its identity and `orphaned` reaped
   (the supervisor library: `stop_conductor`, `reap`), then resumed by an ordinary `conduct resume` while the resumes of that
   run stay below `max_recoveries` (else `AUTOPILOT_RECOVERY_EXHAUSTED`). A hung child is stopped only when its whole saved
   identity `(pid, start_ticks, boot_id)` is confirmed; otherwise nothing is signalled or reaped, `current` stays and the
   session stops with `AUTOPILOT_CHECKOUT_LOST`. An ended run is classified (below).
3. A draining session stops (`AUTOPILOT_DRAINED`) and a paused one waits, before any next child: a run that waits for a
   provider quota reset is resumed after it only while the session runs; `max_runs` started runs stop (`AUTOPILOT_MAX_RUNS`).
4. First the runs that wait for answers: when every blocking question of the waiting pieces of one of them is answered
   (`answered`, `applied` or `open` with a resolution, as `orch conduct answer` writes it), `conduct continue --run R` is
   started, and readiness is not asked.
5. Else `orch.py source readiness` (the work-source op `readiness`) gives the phases and the next step. A `run-items` lane
   with `require_readiness` needs its own phase `ready` or `ready_with_advisories` (other phases, finished or unrelated, do not
   matter); then `conduct run --plan P --items <lane> --options <runs root>/autopilot-options.json --json-lines` starts. While
   runs wait for answers and nothing else can start, the controller waits; a plan with no work left (`terminal`, `archive`) is
   `AUTOPILOT_NO_WORK`, any other next step `AUTOPILOT_NOT_READY` with `NEXT_<KIND>`, a lane whose phase is not ready
   `AUTOPILOT_NOT_READY` with `READINESS_<STATUS>`, and a source without the op `AUTOPILOT_NOT_READY` with
   `READINESS_UNSUPPORTED`.

`autopilot-options.json` is `{"scope": {"outside": "block"}}` (a path outside the write set blocks the piece, D14), plus
`limits.run_tokens_hard_max` with `--run-tokens-hard-max` (the run cap of the trusted invocation layer). Every child starts
through `detach.spawn` (launcher `autopilot`) with a run id chosen before (`--run-id`) and a fresh `launch_id` (16 hex) as the
nonce of its detach acknowledgement: **before** the child exists, `autopilot.json` holds the launch intent `current = {run_id,
launch_id, state: launching, kind, since}`; after the acknowledgement `state: running` with `pid` and `start_ticks`. The child
takes the checkout lock and the run lease itself: while another conductor holds them it refuses (`RUN_BUSY`, `WORKTREE_BUSY`) and
the session stops with `AUTOPILOT_CHECKOUT_LOST`, never with a second conductor on the checkout.

**Startup fence.** The controller holds `autopilot.lock` for its whole session. The short transitions of a launch intent take a
second lock, `<runs root>/autopilot-launch.lock`, which is never held while a child or an acknowledgement is awaited. Order of
locks: `autopilot-launch.lock`, then the checkout lock, then the run lease. The controller writes the intent under the launch
lock before the spawn. Every child gets `SKM_ORCH_AUTOPILOT_STATE=<runs root>/autopilot.json`,
`SKM_ORCH_AUTOPILOT_LAUNCH_ID=<launch_id>`, `SKM_ORCH_DETACH_NONCE=<launch_id>` and the acknowledgement path
`<runs root>/detached/<run_id>.<launch_id>.ack.json` (`run`, `continue` and `resume` alike). Before the checkout lock, the run
lease, the run folder, any claim and any role, `run`, `continue` and `resume` of such a child take the launch lock (waiting up to
30 s), read `autopilot.json` (records/v1) and require `current` to be `launching` with their `run_id` and `launch_id`. Otherwise
the child acknowledges `refused` with `AUTOPILOT_LAUNCH_CANCELLED` and exits 1, having taken no lease and created, claimed and
started nothing. When the intent matches, the child keeps the launch lock while it takes the checkout lock and the run lease,
creates or loads the run and writes its `started` acknowledgement; only then does it let the launch lock go, keeping the run
until its end. `continue` passes the fence once (its `resume` does not take it again). The variables are dropped before roles
and checks.

A controller decides about an intent that is still `launching` (after a crash of the one that wrote it, or a child that did not
acknowledge within 20 s or exited first: an acknowledgement written after the wait ran out still adopts the child) only under the
launch lock, so it sees either the acknowledgement of the launch or a child that has not passed its fence yet:

- a `started` acknowledgement of this run and launch id adopts the child (`state: running` with its identity);
- a new run (`run`) whose folder exists without one is adopted when `run.json` and `state.json` are valid, and is otherwise a
  partial record: `AUTOPILOT_STATE_INVALID`, the folder and `current` are kept, nothing replaces them;
- for `continue` and `resume` the folder of the existing run proves nothing about this launch (P8.3): only the acknowledgement does;
- younger than 30 s (and the child, when known, still alive): wait. Else a new run with no folder is cancelled (`current`
  cleared, `history` `never_started` once) and the next lane may start. An existing run whose lease is held without the
  acknowledgement of this launch stops the session with `AUTOPILOT_CHECKOUT_LOST`, no second child. An existing run whose lease
  is free keeps its id and resumable state: in the same save that cancels the intent, `current` becomes the intent of its next
  attempt with a new launch id (no `never_started`), so a crash, a `stop` or `max_runs` before that attempt is spawned leaves it
  `current` and the next start goes on with it before asking readiness. A `continue` saves the waiting pieces it takes back in
  its intent (`retry`) before its child exists; its next attempt is `resume --retry <pieces>`, because a child may have taken them
  back and died before its acknowledgement (taking a piece back again is idempotent, so no `NOT_WAITING`). The attempt is counted
  in `runs`; at `max_runs` the session stops `AUTOPILOT_MAX_RUNS` with the attempt kept. A child that exited without an
  acknowledgement is classified like a run that stopped `DETACH_FAILED`, its next attempt kept `current`.

A child of a cancelled launch id that reaches its fence later is always refused. A timeout or a missing folder alone never
proves that a child died: the lock and the launch id close the window between the check of the intent and the lease.
`AUTOPILOT_LAUNCH_CANCELLED` is a refusal of the child's startup, not a stop code of the controller.

**How a run ended.** Exit 0: no piece taken is `AUTOPILOT_NO_WORK`; closed pieces go on (the streak of runs without a closed
piece is reset; `max_no_progress_runs` of them in a row is `AUTOPILOT_NO_PROGRESS`). Exit 4 (a piece waits for an answer): with
tracked changes in the checkout (`git status --porcelain --untracked-files=no`, outside `.swissknifeman/` and the folder of the plan, compared by whole folders;
the plan folder is only the one the work source named for the run, `<folder>/artifacts/<piece>` of its briefs inside the
checkout: a plan kept in a workspace, or an unknown one, leaves nothing else out, so `plans/<plan>/x` is then a change too) the owner
is needed (`AUTOPILOT_OWNER_NEEDED`; nothing is reset, stashed or checked out), else the run joins `waiting_runs` and independent
lanes go on (three waiting runs at once need the owner). Exit 1, by the stop code of the run: `PROVIDER_QUOTA` with a reset
within `quota_wait_max_s` waits, then resumes (else `AUTOPILOT_QUOTA`); `TOKEN_BUDGET*` is `AUTOPILOT_BUDGET`; the one-time
failures `TIMEOUT`, `ROLE_FAILED`, `ROLE_OUTPUT_EMPTY`, `ROLE_OUTPUT_INVALID`, `MODEL_UNAVAILABLE`, `GROUP_REVIEW_FAILED`,
`QUESTIONS_LOCKED` and `CONDUCTOR_CRASHED` are resumed, and `QUESTION_ANSWERED_NOT_RETRIED` resumed with `--retry` of the named
pieces, within `max_recoveries` of the run; `ITEM_BLOCKED` whose escalations are all `WRITE_PROTECTED_PATH: <path> -> <staged
path>` needs the owner to place the files (the pairs are in the message); `ITEM_BLOCKED`, `CHECKS_RED` and `REVIEW_LIMIT` go on
once and stop the second time in a row for the same piece and code (`AUTOPILOT_REPEATED_BLOCKER`; with tracked changes at once
`AUTOPILOT_OWNER_NEEDED`); `RUN_BUSY`/`WORKTREE_BUSY` is `AUTOPILOT_CHECKOUT_LOST`; `STATE_CORRUPT`, `STATE_INVALID`,
`RUN_INVALID` is `AUTOPILOT_STATE_INVALID`; any other code `AUTOPILOT_RUN_STOPPED`. Exit 130 that no stop request caused is
`AUTOPILOT_INTERRUPTED`. Before all of these, a group review with Blocker or Major findings whose follow-up is not settled
(`state.group_reviews[*].followup`) needs the owner with the follow-up command, and `QUESTION_ADVISED` lines of the session's runs
(questions answered by the advisor or panel) reaching `max_auto_decisions` stop with `AUTOPILOT_DECISIONS_EXCEEDED`. The info
beacons of a run (`STAGE_SLOW`, `STAGE_IDLE`, `RUN_SLOW`, `RESULT_*`, `GENERATED`, ...) are not outcomes.

**Deadline and stop.** `deadline_at = started_at + max_wall_s` is written at the first start of a session and a restart after a
crash keeps it; it is checked at every look (a running child, a pause, a quota wait, a wait for answers). When it passes, and on
a `stop` request, the current child gets SIGINT (`os.kill` of its pid only, while the `(pid, start_ticks, boot_id)` saved in `current` at the
launch or the adoption all match `/proc`, the boot of the machine and the owner of a held lease; an unknown or different
identity gets no signal, neither here nor through the supervisor library), the controller waits `[orch.supervisor] grace_s` for it to end `INTERRUPTED` (resumable with
`orch conduct resume --run R`); a child that does not end is stopped by the supervisor library (`stop_conductor`: SIGINT,
SIGTERM, SIGKILL to the identified pid; then `reap` of its role groups). Only when no conductor of the run is alive does the
session stop with `AUTOPILOT_MAX_WALL` or `AUTOPILOT_STOPPED`; a child that cannot be stopped stays `current` and the session
stops with `AUTOPILOT_CHECKOUT_LOST` (exit 1). A start after the deadline of an unfinished session stops at once. A session that
stopped begins anew at the next `start` (new deadline and counters; the waiting runs and the history stay).

**Stop codes.** Each stop is written to `autopilot.json` (`stop`), sent as the event `orch.autopilot.stopped` (`plan`, `code`,
`runs`, `items_closed`, `message`) and printed as `CODE: message` on stderr. `AUTOPILOT_BUSY` and an unreadable `autopilot.json`
(`AUTOPILOT_STATE_INVALID`, the file is kept as evidence) leave the file alone. These are not stops or beacons of a run:

| Code | Exit | Meaning |
| --- | --- | --- |
| `AUTOPILOT_NO_WORK` | 0 | the plan has no work left, or a run took no piece |
| `AUTOPILOT_DRAINED` | 0 | `drain`: the current run ended and none was started |
| `AUTOPILOT_STOPPED` | 0 | `stop`: the current run was interrupted (resumable) |
| `AUTOPILOT_MAX_RUNS` | 0 | `max_runs` runs were started |
| `AUTOPILOT_MAX_WALL` | 0 | the deadline passed; the current run was interrupted (resumable) |
| `AUTOPILOT_NOT_ALLOWED` | 1 | the machine does not allow the autopilot (`allowed`) |
| `AUTOPILOT_DISABLED` | 1 | the project does not enable it (`enabled`) |
| `AUTOPILOT_BUSY` | 1 | another controller holds `autopilot.lock` |
| `AUTOPILOT_NOT_READY` | 1 | the next step is not a ready lane (`NEXT_<KIND>`, `READINESS_<STATUS>`, `READINESS_UNSUPPORTED`) |
| `AUTOPILOT_OWNER_NEEDED` | 1 | an answer with changes in the tree, protected files to place, group review findings, three waiting runs |
| `AUTOPILOT_BUDGET` | 1 | a run stopped on a token limit |
| `AUTOPILOT_QUOTA` | 1 | a provider quota resets later than `quota_wait_max_s` (or when nobody knows) |
| `AUTOPILOT_REPEATED_BLOCKER` | 1 | the same piece blocked by the same code twice in a row |
| `AUTOPILOT_NO_PROGRESS` | 1 | `max_no_progress_runs` runs in a row closed no piece |
| `AUTOPILOT_DECISIONS_EXCEEDED` | 1 | `max_auto_decisions` questions were answered by the advisor or panel |
| `AUTOPILOT_RECOVERY_EXHAUSTED` | 1 | a run crashed, hung or failed once more than `max_recoveries` allows |
| `AUTOPILOT_CHECKOUT_LOST` | 1 | another conductor holds the run or the checkout, or a child could not be stopped by its identity (it stays `current`) |
| `AUTOPILOT_STATE_INVALID` | 1 | a record of the current run or `autopilot.json` cannot be read or breaks its schema (`current` and the records are kept) |
| `AUTOPILOT_RUN_STOPPED` | 1 | a run stopped with a code the autopilot does not handle (named in the message) |
| `AUTOPILOT_INTERRUPTED` | 1 | a run ended 130 without a stop request, or the controller itself was interrupted |

**Files.** In `<runs root>`: `autopilot.json` (records/v1 `autopilot-state`: plan, controller identity, `started_at`,
`deadline_at`, `mode`, `limits`, `counters` (`runs`, `items_closed`, `no_progress_streak`, `auto_decisions`, `recoveries`,
`quota_waits`), `recoveries` per run, `current`, `quota_wait`, `waiting_runs`, the last 50 runs in `history` (one entry per run),
`last_blockers`, `stop`), `autopilot.request.json` (records/v1 `autopilot-request`: `action`, `at`, `by`), `autopilot.lock`,
`autopilot-launch.lock`, `autopilot-options.json` and the logs and acknowledgements of the children in `detached/`.

## A piece that rewrites the orchestrator: `--frozen`

A piece that refactors `orch` changes the code of the process that conducts it. `run --frozen` (and `resume --frozen`) takes a snapshot of
the committed state (`git archive HEAD`) of the orchestrator checkout the command was started from (`packages/orch`, `aicore`, `planner`
and `bridges`) under `~/.cache/skm-frozen-runs/run-<time>-<pid>`, starts the same command from it with `--project` naming the project, and
removes the snapshot when the command ends. The install roots (`SKM_ORCH_ROOT`, `AICORE_ROOT`, `PLANNER_ROOT`, `PLANNER_PLAN_PY`) point
into the snapshot, `PYTHONPATH` is dropped, and the check commands of the pieces do not inherit roots outside the project, so they test the
project's own code. The snapshot freezes only the code of the conductor: the options and instructions of the run are its
own records (`options.json`, `instructions.json`) either way, and the work source stays live (the work-source plugin is the
one the configuration registers, and every claim, brief and register asks the plan as it is now). `resume --frozen` takes a
new snapshot of the orchestrator from the current commit: that is how a mechanism fix reaches a run stopped on purpose. Outside a checkout that holds the sources the flag is `FROZEN_UNAVAILABLE`.

## Work outside a plan: `run --input FILE`

`run --input FILE` conducts one piece of work without a plan: `FILE` is an `exec/v1` execution-input (`orch.py input adhoc`,
with `--provenance` for support work, or written by hand) served by the built-in file source
(`orch.worksource_file.FileWorkSource`, the same `work-source/v1` contract as the plugin). `--input` excludes `--plan`,
`--items`, `--ready` and `--max-items`; the scenario is `--scenario`, else `default_profile`, and `--options` layers on top.
`--input FILE --adopt` accepts only a writable `review_followup` input with an explicit `scope.write_set`
(`ADOPT_INPUT_REFUSED` otherwise). Existing changes must all belong to that write set (`WORKTREE_DIRTY` otherwise).
For a plan run `--scenario S` is passed to every claim (`orch source claim --scenario S`) and wins over the scenario the plan resolves for
the piece (`orchestration` of the item, phase, plan, overlays); the claim answer names it `scenario_source: invocation:--scenario`, and
an unknown scenario blocks the claim (`SCENARIO_UNKNOWN`) before the piece starts. Without the flag the plan's scenario applies.
`run.json` records `source = {kind: file, path, commit}`, the piece's reference is the `input_id`, and `resume` reads the same file
(a file that changed since the claim is `INPUT_CHANGED`: start a new run).

An explicit required `reads` entry may name a legacy Markdown document in a directory without `plan.json`, including
through an existing project `plans` symlink. The scout and executor read that named file read-only; they do not mutate
the plan. Planner `get` serves native JSON plans and cannot read such a legacy Markdown programme. Native plan source
JSON and generated views retain their API-only access rule; `context_refs` use the caller's permitted read API.

After an environment block, keep the same input and run and use `resume --run R --retry INPUT_ID`. The built-in file
source holds no lifecycle status that needs a separate reopen call. The retry archives the blocked report, streams and
prompts under `attempts/<n>/`, repeats brief/prepare/scout and the blocked round, and reads the current canonical role
text. Registration permits the same attempt's `blocked` receipt to become `done`. Do not invent `plan_support` or
`review_followup` provenance, replace the input, or edit run state to reopen file-source work.

- Artifacts (stage-report, review verdict, check evidence, the registration receipt `register.json`) live in
  `.swissknifeman/orch-artifacts/<run>/<input_id>/`, never in `plans/`: local records, not committed.
- The changes stay in the tree: `commit` is a no-op unless `--commit`; then it commits the changed paths
  with the message `adhoc(<input_id>): <first line of the goal>` and nothing else.
- Provenance `plan_support` and `phase_support` also add a note to the plan's journal: after the registration the CLI asks the
  configured work source for the optional op `note` (`{collection, text, refs}`; the bridge of the plan engine writes it into the journal of the plan). A source without `note`, a refusal, or a plan without a phase (`refs` empty) is the
  `WORK_SOURCE_NO_NOTE` beacon; the work is registered anyway.

## The project

The project is `--project DIR`, else `SKM_PROJECT_ROOT`, else the nearest folder above the working directory that holds `.git`
or `.swissknifeman` (`aicore.state.resolve_project`; the home directory does not count through `.swissknifeman`). Without one
the commands stop with `PROJECT_CONTEXT_REQUIRED` and the hint `--project DIR`; a project that is not a git repository is
`PROJECT_NOT_GIT` for the conductor. `orch.py` takes the same global `--project`, and its run cycle (`source …`) needs a
project. A named project (`--project`, `SKM_PROJECT_ROOT`) that is not a folder is `PROJECT_CONTEXT_REQUIRED`, never replaced
by a search. The conductor tells every `orch.py` it starts the project (`--project`) and how it found it
(`--project-resolution`), so the run cycle cannot land in another repository. The roles always start in the project folder,
wherever the conductor was started. `run.json` records
`project_resolution` (`flag`, `environment`, `marker` or `git`) and `working_directory`.

## Digests of a run

`run.json` holds `config_digest`, the tagged digest of the effective `[orch]` and `[aicore.providers]` (`orch.settings.config_digest`),
and `config_layers`, `[{layer, file, present}]` of the layers behind it. Each piece of work has `options_digest`: the digest of its
merged run options, written as `digest` in `<item>/options.json`. The events carry them: `orch.run.started` has `config_digest` and
`project_resolution`, the `orch.run.stage.finished` events of the conductor have `options_digest` (event-data/v1, optional fields).
The same configuration and options give the same digests; a changed override gives another one.
`run.json` also holds `catalog_digests` `{launch, models, capabilities}`: the digests of the effective launch catalog
(with the `[orch.launch]` overlays), the model catalog and the capability records the run started with, computed as the
dry run of a launch plan computes them (`orch.bindings.catalog_digests`); `conduct status --json` shows them. A resume
runs on the catalogs of now and names those that changed with one info `CATALOG_CHANGED` (no stop; `--frozen` keeps the
options and instructions of the run, not its catalogs); a run recorded before the field resumes as before. This records
provenance; it is not full reproducibility (the environment of the roles is not recorded).

## Recovery after a crash

Before work starts, `state.json` saves a `started` step with `started_at`, `role`, `route`,
`base_head` (null outside git), and the claim's `attempt_id` as `attempt`. For `checks.N`,
`dirty_before` is the sorted list of porcelain paths (at most 500); other steps store null.
Successful work replaces it with the existing `done` result shape. A `Stop` saves only
`status: stopped`, `code`, and `ended`; resume repeats that step normally. Result readers
use only `done` records, so an unfinished step never counts as success.

Resume takes ownership, stops orphaned role groups, applies any `--retry` requests, then
reconciles `started` steps before the loop starts. Closed items (`done`, `done_with_deviations`,
`blocked`, or `abandoned`) discard their `started` and `stopped` records without repeating work;
their `done` results stay intact. A retry still requires a blocked item and removes its unfinished
steps before reconciliation. The rule uses the key's prefix before the first dot:

| Step | Recovery (L10) |
| --- | --- |
| `brief`, `prepare` | repeat |
| `scout`, `research.N`, `review.N`, `triage.N`, `advice.N` | repeat the read-only role without an interruption correction |
| `executor.N` | repeat with an interruption note naming `base_head` and up to 200 sorted dirty paths; keep partial changes and the retry count |
| `checks.N` | repeat; compare the current porcelain paths with `dirty_before`, and emit `CHECK_CHANGED_TREE` if they differ; a run that changed the tree is repeated once on it (`checks/<n>-rerun`, `CHECKS_MUTATED` when that changes it again); a command check whose green evidence of this run is there for the same candidate (HEAD and dirty digest), command, directory and fingerprint is not run again (`checks.reuse`) |
| `research-save.N` | repeat the idempotent save for that research number |
| `close`, `register` | recover a successful registration receipt of this attempt; otherwise repeat the idempotent call |
| `commit` | recover a successful commit receipt of this attempt only when its workspace part is complete; otherwise repeat commit |
| `checkpoint`, `fix-commit.N` | the stage commits of a split run (see Split commits): recover the receipt `commit-<stage>.json`; without one, the newest commit that carries this attempt's `Plan-Run`, `Plan-Attempt` and `Plan-Stage` trailers closes the step (the stage is never committed twice, I4); otherwise repeat the commit |
| any other key | stop with `STAGE_RECOVERY_UNKNOWN`; settle the item, or use `--retry` if it is blocked |

Each decision emits `info` with `reason_code: STAGE_INTERRUPTED`, the item and stage,
and message `repeated`, `repeated with interruption note`, `repeated after tree change`,
or `no recovery rule`. The executor's note is appended once to that step's correction
and cleared after its result is done. Recovery never resets, stashes, or rolls back the
tree. Old state files without started records keep their previous resume behaviour.

Closing receipts live in `journal.run_dir(item.orch_run, project=project)/receipts/`, the work-source run,
not the conductor's item folder. `register.json` closes `register` (or a model registrar's `close`) only for
`recorded` or `no-op` with a matching attempt. `register` keeps `{outcome, gate}`; recovered `close` keeps
`{by: closer, answer: ...}`, as required by the subsequent registration step. `ATTEMPT_CONFLICT` on a repeat
stops with `REGISTER_REFUSED` and leaves the step unfinished.
An ad-hoc item retried after `blocked` may register a new outcome under the same attempt; a different outcome
after `done` remains `ATTEMPT_CONFLICT`.
Malformed fields used by the recovered result also require a repeat; recovery checks them against the live
work-source response contract before recording `done`.

Before a closing source call, `register-request.json` or `commit-request.json` (`commit-<stage>-request.json` for a stage of a split run) durably records `attempt_id`,
the request parameters and their canonical JSON SHA-256 digest. After the call, the request also records the
SHA-256 of the unmodified response before the receipt is published. Recovery requires both digests and the
request's run, reference and attempt to match, including responses with an explicit `attempt`. The request's
mtime must be at least the step's `started_at` and the saved state's publication time. The latter conservatively
fences retries within the same second; a later state save can require an idempotent repeat. Thus a crash before
the new source request is written cannot reuse a prior blocked-registration receipt. A new request also clears
the old response digest. Commit responses may include the optional
work-source/v1 `attempt` field.

`commit.json` closes only for `committed` or `no-op` and this attempt. For a plan in the workspace,
`workspace_commit.status` must be `committed`, `no-op`, `skipped-legacy`, or `skipped-no-git`.
`nothing`, `failed`, `locked`, or missing workspace completion repeat commit; a live response with an incomplete
workspace part stops with `COMMIT_REFUSED` for resume. Repeating after the source commit completes the workspace
part without a second source commit. The durable commit request retains the source SHA for this attempt across
repeats. If the repeated answer names only a workspace commit, the step still returns the source SHA for
handoffs and group review. Without a known source SHA, `sha` is null and `message` names the workspace commit.
The result remains `{outcome, sha[, message]}`. Git history is never proof
that a step completed.

Each closing recovery emits `info` reason `STAGE_INTERRUPTED` with exactly one of `closed from receipt`,
`repeated: receipt missing`, `repeated: receipt refused`, `repeated: receipt of another attempt`, or
`repeated: workspace part incomplete`. These info reasons are not Stops or Beacons. Leases, receipts and
reconciliation provide local durability on one host; they do not provide Engine Port workflow replay,
durable timers, signals, compensation, multi-day execution or recovery across machines.

## The cycle of one piece of work

Every step has a key and is recorded in `state.json` before it starts and once it closes; the work source is reached only through
`orch.py source …` and the roles only through the launch catalog.

| Step | Who | What |
| --- | --- | --- |
| claim | work source | `source claim` with a submission of this run. `--batch` (default) takes every piece of `--items A B C` in progress at the start (each piece is started under its own run, one after another, and a dependency that is in progress counts as met: `source claim --batch`, for the planner `start --in-progress-deps`) and the first prompt of the shared session lists them; `--no-batch` claims one at a time; The claim names the executor of `--options` (its provider, model or the model of its class, and its effort; the configured default executor without one), so a route of the work that pins another provider needs no copy in the plan's `orchestration`. `--ready` asks the source for its next ready lane (`lane` of the claim answer) and runs that lane as a batch too, or one piece at a time with `--no-batch`. In a batch a stop gives no piece back on its own: all stay in progress and `resume` goes on (`release` frees one by hand; `--no-batch` gives back a piece nobody worked on, as before). A piece whose executor round began counts as worked on, however the round ended |
| `brief` | work source | `source brief`; the execution-input is read from the artifact store; the base revision is recorded |
| `prepare` | orch | writes `launch-plan.json` for the scenario. The conductor omits stages it skips; public `source prepare` binds the pack as stored |
| `scout` | context-scout (economy) | when the pack has a scout or condense stage; the result is a cached context map; its optional closing ```` ```json write-set ```` block (`scout-write-set`: `paths`, `tests`) is taken out of the map into the executor's "Expected paths" section, a missing or invalid block is ignored with a `RESULT_HEALED` beacon, and the hint never widens `scope.write_set`. The cache key ignores `provenance`, `digest`, the `input_id` digest suffix and `lessons[].ts` (a timestamp, not scope, an instruction or a dependency). A change of goal, scope, reads, route, role text or a selected skill misses |
| `research.N`, `research-save.N` | researcher, work source | with `orch.research.policy = required` (every piece) or `conditional`, the default (a piece whose input says `research.need = required`); `off` never (see [Research](research.md)): the researcher (`implementation`, read-only, network allowed) asks the allowed sources of `[orch.research.sources]` with the one command `python3 …/orch.py research query` and returns a closed `research-result` (`query`, `claims` each with `sources`, `contradictions`, `unknowns`, `sources_used`; a statement without a source belongs to `unknowns`); `research-save.N` then has the work source keep it (`source research`: a plan keeps `research/<item>-<n>.json` and declares it as an input of the item, a file input keeps `research-<n>.json` in its artifacts) and, when the source cannot, the conductor keeps it in the artifacts of the piece and prints `RESEARCH_NOT_SAVED`; no source configured stops the run with `RESEARCH_NO_SOURCES` before any work |
| `executor.N` | executor | the execution-input, the context map, the run rules, the repository rules of an isolated role and, for a correction, its package; returns a closed `stage-report`; the conductor then reads the changed paths from git |
| `checks.N` | deterministic | every `acceptance`/`impact` command check of the cadences asked for, with a check-evidence file per check; the item checks run cheapest first (the red ones of the round before ahead, then by their time in earlier rounds), `checks.parallel` at a time, and with `checks.fail_fast` none starts after a red one (`skipped`, `skip_reason` `fail_fast`); the `phase` checks run only when every item check is green (else `skipped`, `skip_reason` `phase_after_red`); a green check with the same candidate is reused (`reused`, no new run) |
| `review.N` | reviewer (default `grok/grok-4.7/high`) | read-only, the diff against the base and the check results; returns `review-findings` |
| `triage.N` | triager | reproduces every finding; returns `triage-result` (confirmed with a correction package, or rejected with a reason) |
| `advice.N`, `triage.N-a` | advisor (`frontier`), triager | with `orch.advisor.enabled`: one opinion on a problem the work cannot solve alone, returned as `advice` (see [The advisor](#the-advisor-p104)); `triage.N-a` is the triage of review round N repeated with the advice, which then stands for the round |
| `close` | registrar (economy) | only when a layer of the options names the registrar in `stages`: a model runs the one `source register` command the conductor built (the launch catalog allows it exactly `python3 *orch.py source register *`) and answers with its output; it never sees the task |
| `register` | work source | `source register` with the report, the status and the evidence; a repeat is a no-op, so after a closer it only confirms the record, and when the closer failed it records the result and `close` says `conductor` and why |
| `commit` | work source | `source commit` with the changed paths and the artifact folder, when the pack's `git_action` is `commit` |

Red checks get `limits.check_fixes` corrections; confirmed findings `limits.corrections` corrections within
`limits.review_rounds` rounds (2 rounds and 1 correction by default, as in the `full` pack). `check_fixes` and
`corrections` are **targets**: past one, a further round runs while the last correction made progress (the set of red
checks changed or fewer failures show; the set of confirmed finding keys changed), up to `limits.ceiling_factor` times
the target (2 by default). Every round past a target prints a `LIMIT_OVER` beacon and leaves a plan note.
`review_rounds` is a **wall** (D24): a review is the safety net of finished work, not a loop. The findings of the last
round are corrected once without another review (`review.final_correction`, default true), the acceptance checks of
that correction still run, and the piece carries `review_debt` with a `REVIEW_DEBT` beacon that the observer report
lists for the look after the plan. A final correction that changes no product file leaves the findings open as plan notes (`review_debt.corrected: false`) instead of calling them corrected; a spent run-wide budget (`review_rounds_batch`, `findings_batch`, `corrections_batch`) still wins over the wall. A correction that changed nothing, or a ceiling, registers the piece `blocked` with
an escalation (`CHECKS_RED`, `REVIEW_LIMIT` when `final_correction` is false). A finding that
did not reproduce is never a reason for a correction; a confirmed review finding corrected together with red checks is
sent to the executor once, in that one round.

The reviewer of a piece comes from, strongest first: an explicit `reviewer` of the run (a layer that sets it: the
configuration `[orch.conductor] reviewer`, a work-source layer such as the plan's `orchestration.options.reviewer`,
`--options`); else the `review_route` of the execution-input (the plan item's `review.reviewer`), which completes the
default reviewer when it is partial (only a class or an effort keeps the default provider; another provider or a class
lets the model catalog pick the model); else the default `grok/grok-4.7/high`. The shipped default is no explicit choice:
`run --dry-run` shows its source as `default`. `route explain` and `review-verdict.json` (`reviewer_source`) name
`plan:review.reviewer` when the plan chose. `review_rounds_max` of the input lowers `limits.review_rounds` of the piece
(never raises it; `options.json` names the source `plan:review.rounds_max`) and is a wall: no round goes past it on
progress. `review_mode: requested` does not turn on a review the run policy does not have: the policy decides, and the
piece gets one info `REVIEW_REQUESTED_POLICY_OFF` instead of silence. A group review (`review.strategy` groups/single)
runs on the reviewer of the run when one is set; else on the `review_route` the pieces of the group share, and when they
differ on the one of the strongest class (`CLASS_RANK`), announced by `GROUP_REVIEW_ROUTE_CONFLICT` with every piece's route.

Review rounds are tiered by severity (`review.correct_min_severity`, default `Major`; `review.pre_final`, default
`true`). Round 1 looks for everything. Only confirmed findings of that severity or higher go to a correction; the
others are not corrected: they travel as `note` issues ("deferred minor finding…")
in the registered report, so the cleanup of the phase can fix them together. After a correction the next round is a
pre-final audit (when `review.pre_final` is on): the reviewer is told to report findings of that severity or higher
only. A round with no confirmed finding at the floor ends the review.

The executor sees only its prompt: the execution-input, the context map, `rules` and the correction package. It never
sees the plan or the plan's command line. It runs the tests of what it changed; the conductor runs the acceptance
checks outside the executor's sandbox. With the default `checks.executor_runs_checks: false` the prompt names each check by id
and expectation but carries no command (`withheld`), tells the executor not to start containers or call docker, and says that
a proof its sandbox cannot give is an `open_issues` entry of kind `pending`, not a `blocked` escalation. With `checks.self_check` the prompt adds a *Ready to hand over* section: narrow tests in the repository's test files while working, a negative example for every new rule, and each self-check command once on the final tree before the report; a correction asks for them again. A completion report that does not list every self-check command in `self_check`, or lists a red one without a deviation naming the failure, goes back to the executor once per piece before any acceptance check (`RESULT_INCOMPLETE`, admission saved in `self_check_returned` before the round, so a resume replays it); the second report reaches the checks as it is. The acceptance checks stay the conductor's; under SKM_CHECK_RUN `affected-tests.py` keeps to its own receipts (`conductor.json`, reused across runs; tier all: those of the run), so a green written by a self-check is never acceptance evidence (accident prevention: an open-access role can write the git directory). With `true` the
executor gets the commands and runs them itself. A gap that needs the owner is `blocked` with one `escalation` issue per
missing thing; `done_with_deviations` needs a `deviation` issue. `done_pending_checks` is for work that is complete while
acceptance checks could not run in the executor's environment (a container, the docker socket, `.git`, the network): it needs a
`pending` issue naming them. It is not an escalation and never a registered status: the checks stage runs the checks as after
any `done`, red ones are corrected or block the piece as usual, and when they are green the piece is registered `done` with
the evidence of the checks and one `note` issue instead of the `pending` ones. When the conductor ran no check at all
(every one skipped by `checks.cadence` or `checks.kinds`) nothing proves the work, and the piece is blocked with `CHECKS_NOT_RUN`.
A `deviation` issue carries `class` (`write_set`, `spec_mismatch`, `test_env`, `docs`, `dependency`, `environment`,
`other`), `impact` and `outcome` (`accepted`, `follow_up`, `owner_decision`); `severity`, `auto_fixable` and `evidence`
are optional and `next` stays free text. Healing fills a missing `class` with `other`, `outcome` with `accepted` and
`impact` with "not stated by the executor" (said in the note issue); the registration bridge writes the fields to the
`data` of the work source's journal event.

**What changed is read from git.** After every executor round the conductor lists the dirty paths of the tree, minus
what the work source wrote when it claimed, the artifact folder, the plan folder of the input and the conductor
reports. The union over the rounds is the `changed_paths` of the registered report and the paths of the commit (a
correction round lists only its own paths; the conductor does not lose the first round's). Paths that
`scope.write_set` does not own are, with `scope.outside: deviation` (default), listed to the reviewer, recorded as a
`deviation` (`class: write_set`, `outcome: accepted`, `evidence`: the paths; the paths the scout expected are named in the text) and committed with the piece; with `block` the piece is blocked right after the executor
(`OUTSIDE_WRITE_SET`).

**The write set is a fence by module, and runtime artifacts are no product.** Right after an executor round, in this order:
(1) *runtime artifacts*: the new **untracked** files under `scope.runtime_paths` (default `.swissknifeman/orch-artifacts/**`,
`.swissknifeman/orch/**`, `**/tests/evidence/**`; logs and evidence of a run) are moved (`os.replace`) to
`<artifacts of the piece>/stray/<original path>`, said as `RUNTIME_ARTIFACT_RELOCATED` and as a `note` issue, kept in
`state.relocated`, and never counted in `changed_paths` or the commit; the artifact folder of the piece, the plan folder and
the conductor reports are not touched. A **tracked** file under them that the round changed is history and cannot be moved:
the piece is blocked with `OUTSIDE_RUNTIME_ARTIFACT` (restore it from git). (2) *Modules*: the module of a path is
`packages/<id>`, `bridges/<id>` or `hub` (`scripts/`, `configs/`, the rest of the repository root); the modules of the piece
are those its `write_set` patterns name up to the first `*`, `?` or `[` (`packages/orch/**` names `packages/orch`; a module
id that is itself a pattern, `packages/*/x`, names every module of the root; a pattern that starts with a glob names the hub).
`CHANGELOG.md` and `docs/**` are allowed to every piece and make no module of it, and neither does a granted `extra_paths`
directory. A path outside the write set that belongs to another module is a deviation of the piece that raises its review
risk (`scope.outside_module: deviation`, default: a piece that legitimately grows, such as a closing piece repairing the
regressions of its phase in other modules, goes on); `block` stops the piece with `OUTSIDE_MODULE` instead, and a layer of the
work source may set it; `scope.outside: block` still stops with the stricter `OUTSIDE_WRITE_SET`). **Checks** that change the tree: the checks run again once on the changed tree
(`checks/<n>-rerun/`, the evidence files are overwritten, so the evidence proves the candidate that is committed); a second
change is `CHECKS_MUTATED`. The product files they changed (`state.checks_changed`) belong to the candidate and are committed like the
executor's, under the same module rule (`OUTSIDE_MODULE`); their ownership is recorded (and merged with the earlier record)
before the rerun starts, so a failed rerun or a retry that finds the formatter idempotent loses none of it. A runtime
artifact (`scope.runtime_paths`) is no product and no mutation: an untracked one is moved to `<artifacts>/stray/` right
after each pass (`state.relocated["checks.<n>"]`, `RUNTIME_ARTIFACT_RELOCATED`), so a log rewritten on every run neither
triggers the rerun nor `CHECKS_MUTATED` and the tree stays clean; a tracked one stops with `OUTSIDE_RUNTIME_ARTIFACT`.
The commit lists the records of the piece's artifact folder file by file (tracked or not ignored); the `stray/` subfolder is
never committed, also when the source names a tracked artifacts folder.

**A result outside its contract** goes through three steps: healing by rule (`heal.py`: one honest reading of a form
mismatch, such as a string exit, a differently spelled status or a GREEN verdict with a Major finding; every mend is
said in a `RESULT_HEALED` line and, for a stage-report, a `note` issue); a repair by the `report-fixer` role (an economy
model that rewrites only the result block from the role's own answer, `limits.repairs` times, default 1;
`RESULT_REPAIRED`); and only then a repeat of the whole role within `limits.retries` per step. A triage that rejects a
Blocker or Major finding without a reproduction that ran is outside the contract.

**A rejection of a Blocker or Major finding stands only when the conductor reran it** (`stages/triage.py`,
`checks.run_reproduction`). The command of the rejection is model text, so it is run read-only
(`ro-run.py --protect <project>`, Landlock; stdin `/dev/null`, ceiling `limits.triage_repro_timeout_s`, default 600 s,
log `<piece folder>/triage/<round>/<finding>.log`), and only after a line with a marker of this very call, printed inside the
guard before the command starts, is in the log. A trivial command (a standalone `true`, `:`, `exit 0`, `echo …`,
`printf …`; `is_trivial_reproduction`) is not run: the finding is confirmed again (`TRIAGE_REPRO_TRIVIAL`). A command with
an unquoted shell operator (`;` `&&` `|` `>`), a substitution or a second line (`echo checking; python3 repro.py`) is not
trivial and goes to the guarded rerun; an operator in quotes or escaped is plain text (`echo '|'`, `printf '%s' '>'` stay
trivial). The line is read as Bash reads it: `#` starts a comment only at the start of a word, so `echo checking#phase;
python3 repro.py` is compound, while `echo ok # note` and `echo '#'` stay trivial. Another exit than the one the triager reported confirms it again
(`TRIAGE_REPRO_MISMATCH`). When the guard cannot be had (Landlock missing or too old, the project in a writable root of
`ro-run.py`, a failed start) or the rerun times out, the rejection cannot be proven and the finding is confirmed again
whatever the exit (`TRIAGE_REPRO_UNVERIFIED`, fail closed). The restored entry carries the command, the observed exit and
`the conductor reran the rejection: <why>`, and the finding goes to the correction as any confirmed one. The result of the step
keeps `verified: [{finding, outcome: kept|restored, reason}]`. Confirmed and Minor findings are not rerun.

Both the heal and the repair keep the meaning of the result or move it toward caution (`domain/semantics.py`). Statuses
rank `done` > `done_with_deviations` > `done_pending_checks` > `blocked`, verdicts `GREEN` > `ATTENTION` > `RED`; neither
step raises one, drops an issue, finding, question or check row, lowers a severity, changes an escalation or a blocker
into another kind, or sets a deviation outcome to `accepted`. So the heal makes a `done_with_deviations` without a
deviation carry a `follow_up` deviation, a `done_pending_checks` without a pending issue carry one (the conductor's
checks then decide: green closes it, none run blocks it with `CHECKS_NOT_RUN`), and an escalation in a report that is not
blocked makes the report `blocked`; a deviation without an outcome is a `follow_up`; a verdict `ATTENTION` or `RED`
without findings is not healed into `GREEN` but goes to the repair and, failing that, to a repeat of the reviewer. The
repair is compared with the heal of the role's own block. A finding is matched by its content, not by its id or severity
(its normalized place and failure scenario; findings with the same content are compared one by one), so a severity moved
from one finding to another at the same place is drift. A deviation is matched by its text, impact and class together (blanks and case ignored): a
deviation accepted that was not accepted before is drift even when the total of accepted deviations stays, also for
deviations of the same (or blank) text that differ in impact or class, and a reworded one counts as new. A deviation with
none of the three is matched only by its place among such ones, so an unclear identity never authorizes an acceptance. A block that raises the status or the verdict, lowers a severity, loses a finding, question, escalation,
pending issue or check row, or turns a confirmed finding of a triage into a rejected one is refused with
`REPAIR_SEMANTIC_DRIFT`; the next repair, then a repeat of the role, follows, and a role that never gives a faithful
block ends in `ROLE_OUTPUT_INVALID`. An answer with no block that parses has nothing to compare: the fixer's block is
taken and the step records `repaired_from_text`.

### Stops

The conductor stops only on:

| Code | When |
| --- | --- |
| `DETACH_FAILED` | the detached child exited without acknowledging startup, or no matching acknowledgement arrived within 20 seconds; inspect the named log and status before retrying |
| `AUTOPILOT_LAUNCH_CANCELLED` | a child of the autopilot found at its startup fence that the launch intent of `autopilot.json` no longer names its run and launch id (the controller cancelled or replaced it), or that `autopilot-launch.lock` stayed busy for 30 s; it took no lock or lease, created no run, claimed and started nothing, and acknowledged `refused` (exit 1). Nothing to do: the autopilot already went on |
| `RUN_BUSY`, `WORKTREE_BUSY` | another conductor owns the run or checkout; wait for it or stop it before retrying |
| `QUESTIONS_LOCKED` | the item's questions lock could not be acquired within 10 seconds |
| `CONDUCTOR_CRASHED` | an unexpected exception in the conductor loop; exit 1, stopped state and `run.end`; the redacted traceback is written to `<run>/crash.txt` when that write succeeds. If the artifact cannot be written, the stop still names `CONDUCTOR_CRASHED` and says `crash.txt unavailable` (it does not claim the file exists); fix the cause, then resume |
| `STAGE_RECOVERY_UNKNOWN` | a started step has no recovery rule; settle the item or retry it |
| `REVIEW_LIMIT` | a batch limit refused a round while a confirmed Blocker finding is open | the finding ids and the limit |
| `DEPENDENCY_BLOCKED` | with `on_blocked: report` the run went on after a blocked piece, and a later piece of the run depends on it (`depends_on` of its claim): it is not started, stays in progress and the run ends here after the others; `resume --retry` the blocked piece, then `resume` |
| `DISK_LOW` | less than `limits.disk_min_gb` (default 5) GB free under the project or the temporary directory when the run starts or resumes, or before the checks of a round; the run stops (resumable): free the space, then `resume` |
| `RUN_TIMEOUT` | the active time of the run passed `limits.run_timeout_s` (default 0: off); the current role is cancelled; raise the limit, then resume |
| `TOKEN_BUDGET` | accounted fresh tokens reached `tokens_hard_max` of the piece or `run_tokens_hard_max` of the run, or the step reached the run policy's `budgets.stage_tokens_max`; checked before **every** model call (a repeat, a repair, a fallback route, a group review), so no new call starts; done steps stay saved; resume with `--raise-limit KEY=N` (`stage_tokens_max` is raised in the policy) |
| `TOKEN_BUDGET_UNMETERED` | a model attempt reported no usage while `tokens_hard_max` or `run_tokens_hard_max` is in force and `limits.unmetered` is `stop` (the default): unknown usage is not zero, so no further call starts; set `limits.unmetered` to `charge` in the `--options` file of the run (or the configuration) and resume: each attempt without usage then costs `limits.unmetered_charge_tokens` |
| `BRIEF_TOO_LARGE` | the execution-input of the piece (the embedded context pack and the files it reads included) is larger than `budgets.brief_max_bytes` of the run policy (the `full` pack: 1048576); checked once the options are resolved, before the first role, and again when the input is rebuilt; split the item or raise the budget in the policy |
| `ITEM_BLOCKED` | a piece is blocked and `on_blocked` is `stop` (or it left changes in the tree); a piece that waits for the answer to a question ends as `WAITING_DECISION` instead |
| `WAITING_DECISION` | a piece is blocked on a blocking question that waits for an answer (`state.items[<item>].waiting = {question_ids, since}`); not a failure: the run ends with outcome `waiting`, status `waiting` and exit code **4**, and holds no process (D11). Under `on_blocked: report` the other pieces go on first, and the run ends with `waiting` when some piece still waits and no other stop happened. `conduct status --json` lists `waiting: [{item, question_ids, since}]`; answer with `orch conduct answer`, then `orch conduct continue --run RUN` |
| `QUESTIONS_OPEN` | `continue` found a piece that waits with a blocking question that is not answered yet; exit 1, nothing is started; the message lists `item:question`; `--partial` continues the pieces that are ready |
| `NOT_WAITING` | `continue` was given a piece that does not wait for an answer in this run, or the run has none; exit 1 |
| `QUESTION_ANSWERED_NOT_RETRIED` | a resume skips a blocked piece with an answer awaiting consumption and no piece starts in this pass; exit 1; use `orch conduct resume --run RUN --retry ITEM` |
| `OUTSIDE_MODULE` | the executor (an escalation of the blocked piece, `ITEM_BLOCKED`) or the checks (the run stops) changed files of another module than the write set names, `CHANGELOG.md`, `docs/**` and the granted `extra_paths` aside; only under `scope.outside_module: block` (the default `deviation` reports them as a deviation); add the paths to the item's `task_files`, or set them aside and retry |
| `OUTSIDE_RUNTIME_ARTIFACT` | the executor (blocked piece) or the checks (the run stops) changed a **tracked** file under `scope.runtime_paths` (`.swissknifeman/orch-artifacts/**`, `tests/evidence/**`, …): runtime artifacts are history, not product; restore the file from git |
| `CORRECTION_SCOPE_GREW` | a correction round of review findings run by the bounded-implementer (`review.correction_route`) changed paths beyond the paths of its findings, the tests of the write set, `CHANGELOG.md` and the documentation; the piece is blocked (`ITEM_BLOCKED`) with the escalation `CORRECTION_SCOPE_GREW: <paths>`; the owner decides whether the paths belong to the piece, or runs the correction on the executor route (on that route the same growth is a deviation, not a stop) |
| `CHECKS_MUTATED` | the checks changed the tree again when they ran a second time on the tree their first run had changed: they are not idempotent (resumable); make the check change nothing on a tree it has already changed |
| `GENERATE_FAILED` | `[orch.conductor] generate` or `generate_check` exited non-zero (or ran past 600 s) before the checks of a round: the generated files would not match their sources (`checks/<n>/generate.log`, `generate-check.log`) | fix the sources or the generator, then `resume` |
| `GROUP_REVIEW_BLOCKER` | the group review of a batch found a **Blocker**; the run stops (resumable) and a resume stops again at once until the group is settled: run the follow-up (`orch conduct run --input <run folder>/group-review-<n>.followup.json --commit`), then `orch conduct settle --run <R> --group <n> --followup-run <F> --reason …` (see "The review strategy of a batch") |
| `GROUP_REVIEW_FAILED` | the group review failed (the role failed or its reply has malformed `review-findings` JSON) and a piece of the group has `review_mode: requested`, which no other review covers; a resume repeats the review once (two attempts in all); a group without a requested piece only gets the beacon |
| `GROUP_UNKNOWN`, `GROUP_FOLLOWUP_MISMATCH`, `GROUP_FOLLOWUP_NOT_DONE` | refusals of `settle --group`, exit 1, the state of the run is not changed: the run has no such blocked group; the follow-up run did not run `group-review-<n>.followup.json` of this run (or does not exist); it is not finished with its one piece done and committed |
| `ROUTE_UNDERSHOOT` | the executor route is below the class or effort the work requires |
| `CURRENT_INPUT_RECEIPT_UNSUPPORTED` | a stage sets `require_current_input_receipt: true` and no binding implements a verified pre-dispatch current-request input receipt: refused in preparation and preflight before any role is spawned (see *Current request input receipts*) |
| `PROTECT_UNAVAILABLE` | a read-only Claude role cannot protect the checkout (ro-run missing or Landlock ABI < 3); stops before the provider starts, with no writable fallback |
| `SANDBOX_UNAVAILABLE` | `instructions.sandbox` is `require` and a Claude Code role with Bash is on the route, or a Codex route carries `--sandbox`, and the sandbox cannot start (`orch.py doctor`, `orch.sandbox`); the run stops before any work |
| `ISOLATION_UNAVAILABLE` | `instructions.isolation` is `require` and a required role of `isolate_roles` would start without the full isolation of its provider's profile (see Isolation profiles): a flag the CLI does not list, a surface not confirmed off for this CLI version (codex before a live probe, grok always), or an init event of an earlier role of the provider that showed what the profile keeps out (`ISOLATION_DRIFT`), or a route whose command is not a provider CLI the conductor can probe (a wrapper), or a Claude Code CLI that does not list `--setting-sources` and `--settings` (the project permissions would reach the role: `<role>/claude-code: the project permissions reach the role …`). Checked in the preflight before any work, and again when the command line of every role process is built (the roles of a piece, the report-fixer, the group reviewer and the review strategist). `ISOLATION_UNAVAILABLE: <role>/<provider>: <guarantee> isolation (<missing flags or surfaces>); set instructions.isolation = prefer in a trusted layer or remove the role from isolate_roles` |
| `ISOLATION_PROFILES_INVALID` | `configs/isolation-profiles.json` cannot be read, is outside conductor/v1 `isolation-profiles` or declares a guarantee its surfaces contradict: `ISOLATION_PROFILES_INVALID: <path>: <first schema problem>`, before any role |
| `AUTHORITY_RECORD_CONFLICT` | a launch would record another authority than the `agents/<id>/authority/a<attempt>.json` already written for that attempt of the agent run (a record is never rewritten); the process does not start: `<path> holds the authority <digest> of attempt <n>; the launch would record <digest>: an authority record is never rewritten` |
| `AUTHORITY_RESUME_MISMATCH` | an attempt that continues a session would run the `resume_argv` of its launch entry, and that command has another authority than the route's own command (another guard, grant, sandbox mode, permission mode or setting sources): the process would get what no record and no session fingerprint names. Nothing is written and no process starts: `<role>/<provider>: the resume command of the launch catalog has another authority than its command (<keys>); …make resume_argv grant what argv grants` |
| `PROVIDER_UNAVAILABLE`, `TRANSPORT_UNSUPPORTED`, `LAUNCH_UNKNOWN` | a role cannot start: checked for every required role before any work of a piece (an optional scout or report-fixer is skipped instead); a route with `transport: acp` stops with `TRANSPORT_UNSUPPORTED`. Wrapped commands check the provider after `--` as well as the launcher |
| `LAUNCH_REFUSED` | the role/provider pair is explicitly refused in the launch catalog; the message is `<role>/<provider>: <reason>`. Required roles stop before work; optional scout/report-fixer roles are skipped |
| `ROLE_FAILED`, `ROLE_OUTPUT_EMPTY`, `ROLE_OUTPUT_INVALID` | a role kept failing after healing, repair and `limits.retries` |
| `PROVIDER_AUTH`, `PROVIDER_AUTHZ` | the provider refused the credentials or the operation (class `authentication`, `authorization`): never repeated, log in or fix the access, then resume |
| `PROVIDER_QUOTA` | the usage limit is exhausted (class `quota`, `rate_limit`) and the reset is further than `limits.provider_wait_max_s` or unknown, with no admissible `fallback_routes` entry; or the provider of a role is gated on this machine (see Capacity gates). The message names the reset time (UTC) and says `resume after` it |
| `PROVIDER_REFUSED` | the provider refused the request (class `invalid_request`, `content_policy`): a repeat would be refused again |
| `PROVIDER_CONTEXT` | the request does not fit the context window (class `context_limit`); a signal to replan or split the item; the prompt is not rebuilt automatically |
| `MODEL_UNAVAILABLE` | the model is not available to the account (class `model_unavailable`), repeated within `limits.retries` first |
| `TIMEOUT` | a role was silent for `stage_idle_timeout_s` (default 5400: a hang, not a long run), or it ran past its wall: `stage_timeout_s` when set, else `limits.role_timeout_s` of its role (the executor and the bounded-implementer have none by default; see the limits table); then the retry rule of the step applies |
| `WORKTREE_DIRTY` | changes outside the conductor reports before new work (`run --adopt` takes over changes inside the write set of the first piece; `[orch.conductor] foreign_untracked = "keep"` lets untracked files of someone else stay: they are fingerprinted in `state.foreign`, announced as `FOREIGN_KEPT`, and never counted as a piece's work while their content stays the same) |
| `CLAIM_BLOCKED`, `BRIEF_REFUSED`, `PREPARE_REFUSED`, `REGISTER_REFUSED`, `COMMIT_REFUSED`, `WORK_SOURCE_*` | the work source refused or is unavailable |
| `BRIEF_INVALID` | the brief the work source stored is not an exec/v1 execution-input (schema and semantics, as `orch.py validate execution-input` and the file source check it): `<ref>: the brief <input_id> is outside exec/v1 execution-input: <pointer> <code>: <message>` for the first three errors. Nothing of the piece ran and `input.json` is not written; fix the source of the brief and resume. A re-asked brief during a piece that does not match keeps the earlier input (`INPUT_REFRESH_FAILED`) |
| `REGISTER_REPORT_INVALID` | the report the conductor built for the registration (`register-report.json`: the stage-report without `status`, `questions`, `review_recommendation`, `self_check`) is outside work-source/v1 `register-report` or its rules in code (unique `checks_run` ids, no blank text): a defect of the conductor, found before anything is registered; the first three problems are named. `register-report.json` is not written |
| `OPTIONS_INVALID`, `POLICY_UNKNOWN`, `MODEL_CATALOG_UNAVAILABLE` | the run options, the pack or the model catalog are unusable |
| `POLICY_STAGE_UNSUPPORTED` | a required stage of the run policy (`required` and `on_unavailable: refuse`) names a role the conductor does not run (`bounded-implementer` in `frontend-bounded`). The run stops before any role of the piece. `run --dry-run` lists the same reason under `unavailable`. Resume after choosing a scenario the conductor runs (`full`, `solo`, `scout-solo`, `review-only`), or run the plan natively |
| `OPTIONS_UNTRUSTED` | a layer of the work source (plan, phase, item, overlay, input file) loosens the isolation set below it: `instructions.sandbox`, `instructions.isolation`, `sandbox_domains`, `isolate_roles`, `scope.fence`, `scope.outside`, `scope.outside_module`, `scope.runtime_paths` or `scope.extra_paths` (see "Isolation floor") |
| `OPTIONS_UNSAFE_PATH` | an `extra_paths` entry (`--allow-path`) is the root, a system folder, HOME or an ancestor of it, the project or an ancestor, a secrets folder under HOME, or lies in `.git` (after `~` and symlinks are resolved) |
| `STATE_CORRUPT` | a JSON file of the run folder is not JSON; it names the file |
| `RUN_INVALID`, `STATE_INVALID` | `run.json` or `state.json` does not match its records/v1 schema (see *Run records*) when the run is loaded or saved: `CODE: <path>: <JSON pointer>: <message>` for the first three problems, then `settle or release the items of this run, or start a new run`. A file is never rewritten by a read; a state that would not match is not saved |
| `QUESTIONS_INVALID` | `questions.json` of a piece is not JSON or does not match records/v1 `questions`: the run stops, `orch conduct answer` writes nothing and exits 1, `orch conduct questions` lists the other pieces and exits 1. The file is left as it is, so an answer in it is not lost |
| `RECORD_INVALID` | another run record (`options.json`, `routes.json`, `risk.json` of a piece, `review-strategy.json`, an agent's `request.json`, `result.json`, `usage.json` or `process.json`, the machine's `provider-gates.json`) does not match its records/v1 schema; an agent's `authority/a<n>.json` that a launch finds already written is not JSON, is outside conductor/v1 `authority-envelope` or holds a digest that is not the digest of its content (the file is left as it is and no process starts); same message shape (`provider-gates.json`: `remove the file to reset the gates`). A lease record that does not match only makes its owner `unknown` in a busy message |
| `STUBS_INVALID` | a stub file cannot be used (a symlink, not a regular file, over 32 KiB, not UTF-8, a bad header or mode); the run stops before any role starts and names the file and the `STUB_*` code |

With `on_blocked = "report"` a blocked piece that changed nothing is registered, its records are committed and the
run goes on; a blocked piece with changes stops the run, because its partial work would leak into the next piece.

### Beacons: long and costly runs are reported, not cut

The informational limits report long or costly work through `info` lines with a stable `reason_code`;
`orch conduct status` shows the latest one of the running step. Explicit hard limits are listed under Stops:

| Code | When | What it says |
| --- | --- | --- |
| `PROGRESS_LINE_INVALID` | a progress line the conductor was about to write breaks the `conductor/v1` `progress-line` contract (an unknown field, a bad time or run id, an unknown event); never stops the run, and under `SKM_CONTRACTS_STRICT=1` (the test runners) it is a `ValueError` instead | `<event>: <first problem>`; the whole broken line is in `progress.invalid.jsonl` beside `progress.jsonl`; the observer report counts it in `discarded_lines` |
| `RUN_ORPHANED` | status/runs find a journal still running and a free lease for a run marked `lease: true` | the conductor no longer owns the run; resume stops unfinished role groups before continuing |
| `QUESTION_ANSWERED_NOT_RETRIED` | a resume skips a blocked piece with a saved answer (open with a resolution, or legacy answered); other work may still proceed | `answers of ITEM wait: orch conduct resume --run RUN --retry ITEM`; also a Stop when no piece starts |
| `STAGE_SLOW` | every `limits.stage_warn_s` (default 2700) of one role run | how long it runs, its last command and the processes of its session (a test run, a build) |
| `STAGE_IDLE` | every `limits.stage_idle_warn_s` (default 600) without output and without CPU of the process tree | the same; `no child process` means the model call itself is silent |
| `STALL_SUSPECTED` | a role runs the same tool command `limits.stall_repeat_n` times in a row (default 5; once per command), or its stream keeps growing `limits.stall_window_s` (default 1800) without a tool step (again every window); 0 switches each off; nothing is stopped | `same command N times: <command>` or `stream grew without a tool step for N s`, then what the role runs now |
| `CHECK_IDLE` | every `limits.check_idle_warn_s` (default 600; 0 off) while a check writes no output and its process tree spends no CPU; nothing is stopped (`check_idle_timeout_s` stops) | the check id and its processes |
| `HEARTBEAT_NOT_WRITTEN` | `heartbeat.json` could not be written (once per run; the run goes on without it) | the error |
| `CHECK_SLOW` | every `limits.check_warn_s` (default 900) of one check; the time a check spends stopped (`SIGSTOP`, state `T`) is not counted, for the beacon and for `check_timeout_s` | the check id and its processes, each with its age, `ps` state and CPU share (`S` at 0 % is asleep, for example on a stdin nobody writes; `R` or a share of the CPU is at work) |
| `DISK_LOW` | a check runs and the free space went under `limits.disk_min_gb` (every `check_warn_s`; the check is not cut) | the file system and the free space |
| `RUN_SLOW` | every `limits.run_warn_s` (default 7200; 0 off) of the **active** time of the run (segments of its processes: a resume a day later does not count the day) | active time, closed and left pieces, the current step; one plan note per threshold; never stops the run |
| `BUDGET_OVER` | once, when the fresh tokens of a piece pass `limits.tokens_max` | the tokens used |
| `BUDGET_OVER` (`block …`) | a class of the blocks of a role prompt is past its `limits.prompt_*_tokens` (see Prompt manifest) | `block <kind> <origin> <tokens>`: the heaviest block of the class; the prompt is not changed |
| `LIMIT_OVER` | a round past a target of `limits.*` | the target, the ceiling and why it goes on |
| `REVIEW_DEBT` | the last review round the wall allows had confirmed findings; they were corrected without a further review | the round and the findings; `review_debt` in the piece state; the observer lists it for the look after the plan |
| `RESULT_INCOMPLETE` | a completion report without the self-check (`checks.self_check`) goes back to the executor once, before the checks, when a missing command is red: a command an acceptance check of the piece runs (from the project root, perhaps with more arguments) is left to that check, the conductor runs the others itself (`self-check/<round>/` of the piece), and a deviation that names a command accounts for it | the red commands; the prompt carries their tails |
| `SELF_CHECK_COVERED` | a completion report without the self-check whose missing commands the acceptance checks run or the conductor ran green itself: no executor round | the commands, who runs them |
| `CONCURRENT_RUN` | at run start or resume, another run of the project holds its lease | the live runs and their pids; parallel runs slow each other's checks, nothing is stopped |
| `SANDBOX_STUBS_REMOVED` | at run start or resume, with no other run of the project live, an empty read-only placeholder older than an hour sits at a path the Claude Code sandbox protects (`.claude/settings*.json`, `hooks`, `commands`, ..., `.mcp.json`), left by a killed sandboxed command | the removed paths; untracked placeholders only, a real or tracked file is never touched |
| `ANSWER_SCHEMA_IGNORED` | `resume --retry` hands over an answer whose question's `answer_schema` is outside the closed profile of the validator (a keyword such as `format`, or a `$ref` outside the schema), so the answer was not checked | the question and why; `answer_schema_ignored` in its entry; `orch conduct answer` says the same on stderr. An answer an applicable `answer_schema` rejects is `ANSWER_INVALID` and is not written |
| `LIMIT_OVER` (`batch: …`) | a round past `limits.review_rounds_batch`, `corrections_batch` or `findings_batch` (whole run, default 0 = none; same target and ceiling rule, counted from the state of every piece) | the target and why it goes on; when the ceiling refuses more rounds, an open **Blocker** stops the run with `REVIEW_LIMIT`, other confirmed findings become plan notes (no correction) |
| `RESULT_HEALED`, `RESULT_REPAIRED`, `REPAIR_FAILED` | a role result was mended | what was mended |
| `REPAIR_SEMANTIC_DRIFT` | the report-fixer's block changed the meaning of the role's own block (a raised status or verdict, a lowered severity, a lost finding, question, escalation or check row) and was refused | `kept the role's answer: <violations>`; the next repair or a repeat of the role follows |
| `TRIAGE_REPRO_TRIVIAL` | the triager rejected a Blocker or Major finding with a reproduction command that proves nothing (`true`, `:`, `exit 0`, `echo …`, `printf …`); the finding is confirmed again | `<finding>: the command … proves nothing` |
| `TRIAGE_REPRO_MISMATCH` | the conductor reran the reproduction of such a rejection read-only and observed another exit than the one reported; the finding is confirmed again | `<finding>: reported exit <a>, the conductor observed <b>` |
| `TRIAGE_REPRO_UNVERIFIED` | the rerun could not be made read-only (Landlock missing or too old, `ro-run.py` refused or failed before the command started, the project lies in a writable root) or ran past `limits.triage_repro_timeout_s`; the finding is confirmed again whatever the exit (fail closed) | `<finding>: the rerun was not made read-only (<unavailable\|timeout>; log <path>)` |
| `REVIEW_MODE_NONE_SKIPPED` | `review.strategy` named a mode and the plan gives some pieces `review_mode: none`; no group reads them | the pieces left out |
| `GROUP_REVIEW_PENDING` | the run ends with a group (`review.strategy` `groups`/`single`) that has done pieces and no review: it stopped before the group ended; a run that went through all its pieces reviews the done pieces of a group whose others are blocked instead | the group, its done pieces, the pieces the review waits for and the resume that ends them; the observer lists it under incomplete group reviews |
| `GROUP_REVIEW_RESOLVED` | `settle --group` accepted the follow-up run of a group with a Blocker; the next resume goes on | group, follow-up run, its commit and the reason |
| `INPUT_REBUILT` | the plan changed during the piece | the input of the next executor round |
| `PROVIDER_WAIT` | a role failed at the provider and waits before its repeat: a usage limit that resets within `limits.provider_wait_max_s`, or a transient failure after the provider CLI had repeated the request itself (`api_retry`) | the failure class, the wait in seconds and the UTC time it ends; the wait looks at the cancel every second |
| `ROUTE_FALLBACK` | a role moved to a `fallback_routes` entry (its provider failed beyond the wait, or was gated) | role, old route → new route, the class and the reason codes (`WAIT_TOO_LONG`, `RETRY_AFTER_UNKNOWN`, `CAPACITY_GATED`) |
| `ROUTE_UPGRADED` | the reviewer route went up to the `suggested_model_class` of an executor `review_recommendation` (above the class of its route, admitted: startable here, not gated) | role, old route → new route, `<class> -> <class>`; a suggestion at or below the route, or a higher route that is not admitted, gives no beacon |
| `SESSION_ROUTE_CHANGED` | a piece resumes the shared executor session under another model or effort than the one that built it (the session continues, the provider cache of the old model is lost) | the old and the new route |
| `CAPACITY_GATED` | the provider of a role is gated when the routes of a piece are chosen | the gate (until, class, who set it) |
| `SESSION_NOT_PERSISTABLE` | the transcript folder of a Claude executor is unknown (no unique long-name prefix match) | `<item>: the transcript folder of <project> is not known; the executor runs without a resumable session`; never grants the whole `~/.claude/projects` |
| `RESULT_ENV_DENIAL` | failed tool results match an environment refusal | one info beacon per agent step: `<role> <step>: <kind>×<n>[, …]`; categories and counts only in agent `result.json` `env_denials`, observer `refusals_by_source.by_kind` and `.by_role`; permission denials retain their separate beacon |
| `RESULT_SILENT_DENIAL` | a Claude role had tool calls refused without a prompt (`--permission-prompts none`) | the tools and how many calls (`Bash×2, WebFetch`), never their input; for the executor and the bounded-implementer the report also gets a `note` issue "tools denied without a prompt: …" with the way out (widen `allowedTools` in the launch catalog, or change the plan) |
| `WRITE_PROTECTED_PATH` | before the scout, the write set of the piece names paths the provider of the executor refuses to write in a session without prompts (`policies/protected_writes.py`; for `claude-code`, measured on 2.1.309: `pyrightconfig.json`, `.mcp.json`, `.env`, `.envrc`, `.npmrc`, `.pre-commit-config.yaml`, `.gitmodules`, `.claude.json`, shell rc files and everything under `.claude/`, `.vscode/`, `.idea/`, `.husky/`, `.devcontainer/`, `.git/`, at any depth); a path under `[orch.conductor] generated_paths` is not one when `generate` is set | the paths; the executor prompt gets a `Protected paths` rule: the content goes to `<artifacts of the piece>/protected/<path>`, the round ends `blocked` with an escalation `WRITE_PROTECTED_PATH: <path> -> <staged path>`, the owner places the file and retries the piece (`resume --retry`); a file the tree already holds as needed is left alone |
| `GATE_NOT_WRITTEN` | an exhausted quota could not be recorded as a gate (the run goes on) | why |
| `ROLE_LINGERED` | the final `result` of a role was out and its process was still alive `RESULT_GRACE_S` (30 s) later, typically a provider CLI waiting for a background task the model started (a monitor loop that never ends) | the answer is complete; the process group was stopped and the role counts as exited 0 |
| `STUBS_CHANGED` | on `resume`, the stub files say something else than the snapshot of the run | the run keeps its snapshot; a new run reads the new text |
| `SKILL_PATH_INVALID` | a skill file or its selection sidecar fails path, size, UTF-8, schema or auto-digest checks | role, skill name/id and exclusion reason; the skill is left out whole and listed in the prompt manifest |
| `RULES_PATH_INVALID` | a repository rule carrier fails containment, size or UTF-8 checks | role, carrier and reason; its rules are skipped |
| `CHECK_CHANGED_TREE` | the checks of a round changed files of the project (their evidence and logs aside); the first change only: the checks run once more on the changed tree (a second change is the stop `CHECKS_MUTATED`) | the paths; the checks run again, and the evidence of that run proves the candidate |
| `GENERATED` | `[orch.conductor] generate` changed generated files before the checks of a round (the executor changed their sources; the write-set paths under `generated_paths` got a `Generated paths` rule instead of `Protected paths`) | the paths; they belong to the piece like the changes of a check, a file of another module among them is no `OUTSIDE_MODULE` stop |
| `RUNTIME_ARTIFACT_RELOCATED` | an executor round left new untracked files under `scope.runtime_paths` (logs, evidence); they were moved to `<artifacts of the piece>/stray/` and are not committed | the paths and where each went (the report gets a `note` issue) |
| `QUESTION_OWNER_ONLY` | a blocking question has kind `approval` or `credential`, in any questions mode | question id and kind; it stays open for the owner even with a default or under `deny` |
| `ADVICE_HELD` | advice needs the owner, meets an effective gate or falls below the confidence threshold; also a recommendation outside a question's options | source `advisor` (needs_owner, model category or invalid option), `code` (security/public-api/scope-expansion with paths), or `confidence` (actual and minimum); all applicable gate reasons are named |
| `ISOLATION_PARTIAL` | `instructions.isolation` is `prefer` and an isolated role's guarantee is not full: the provider CLI does not list a flag of its profile (asked with the help command of the profile, `codex exec --help` for Codex), a surface is not confirmed off (codex before a live probe of its version, grok), the command of the route is not a provider CLI it can probe (a wrapper), an earlier role drifted; or `instructions.sandbox` is `prefer` and the provider sandbox cannot start. Once per run, provider and reason (the keys said are `state.isolation_noted`; a resume does not repeat them) | `<cli> does not list <flags>; roles are isolated by the environment only`, `<role>/<provider>: partial isolation (<surfaces>)`, or the sandbox line; the commands of Claude Code roles run under the filesystem guard only |
| `ISOLATION_DRIFT` | the first init event of the stream of an isolated role (claude-code, grok `system/init`) lists names in a field its profile keeps empty (`observe.empty`: claude-code `mcp_servers`, `plugins`; grok `mcp_servers`, `skills`) | `<role>/<provider> loaded <field> [<names>] although isolated`; the call goes on, the names are kept in `result.json` `isolation.observed`, and the provider is lowered for the run (`state.isolation_noted` `<provider>:ISOLATION_DRIFT`): under `require` its next role stops with `ISOLATION_UNAVAILABLE` |
| `AUTHORITY_CHANGED` | a launch of a role of a piece records another authority envelope than the last launch of the same role of the piece (`state.items[ref].authority`): a fallback to another provider or guard, another access, a sandbox that stopped or started, a drift | `<item> <role>: authority <old 12 hex> -> <new 12 hex> (<changed keys>)`; the keys are named while the conductor holds the earlier envelope in memory (else `keys not known …`; the files are `agents/<id>/authority/a<n>.json`). The executor session of the piece starts fresh (`SESSION_FRESH fingerprint_changed:authority_digest`) |
| `POLICY_STAGE_SKIPPED` | a stage of the run policy names a role the conductor does not run, and the stage is not a refusing required stage (once per run). The conductor's preparation binds a copy without that stage, rewriting a dependency on it, so a missing manifest does not become `ROLE_UNKNOWN`. Public `source prepare` and `orch prepare` of the original policy still check every stage | the scenario and the stage; the run continues |

A person who runs the conductor sees them on stderr; an observer agent reads them from the journal and decides whether
the run is healthy (a long test run is) or needs a look. The executor and the bounded-implementer have no wall by default
(`stage_timeout_s` sets one for every role); the auxiliary roles have `limits.role_timeout_s` and a check has
`check_timeout_s` (7200). Silence stops work too: a role whose stream has not grown for `stage_idle_timeout_s` (5400) or a
check whose log has not grown for `check_idle_timeout_s` (3600) is hung, unless the CPU of its process tree grew meanwhile (see
Heartbeat and health); 0 turns either off.

Role walls apply to text transport too: `stage_timeout_s` wins, then `role_timeout_s[role]` (including explicit 0).
Only a text role without a configured role wall falls back to the catalog timeout; text transport has no idle wall.
A normal resume after TIMEOUT recomputes its route from the saved options and continues physical attempt numbering
after the persisted failures. It does not refill `retries_by_stage`, `retries_used` or token budgets, and previous
attempt streams and receipt keys are not reused. The owner-directed resumed attempt may run; a further failure
still uses the existing automatic-retry budget.

### Provider availability

`aicore.providers.available.<provider>.enabled = false` (machine, `--config` file or flags; the project layer cannot set it,
`CONFIG_LAYER_FORBIDDEN`) switches a provider off for routing, whatever `providers.selection` rolled out into the project. A route
on it is `PROVIDER_DISABLED: aicore.providers.available.<id>.enabled = false (<layer>)`: `run --dry-run` lists it under
`unavailable`, route choice moves the role to the first admissible `fallback_routes` entry (`ROUTE_FALLBACK`), and without one
the preflight stops the run with `PROVIDER_UNAVAILABLE` before any work (an optional scout or report-fixer is skipped). A role
is routable when the provider is enabled, its CLI is found, the transport and sandbox work and no capacity gate is open.

### Route explain

`orch.py route explain --role R [--plan P --item I | --run RUN --item I] [--scenario S] [--json]` shows why a role runs where it does, without
starting anything: the `candidates` (the `stages` of the options, the reviewer selector, `[orch.conductor]` or the launch
catalog, and the `fallback_routes` of the role) each with `available` and the `problem` that rules it out
(`PROVIDER_DISABLED`, `TRANSPORT_UNSUPPORTED`, `SANDBOX_UNAVAILABLE`, `PROVIDER_UNAVAILABLE`, `PROVIDER_QUOTA`), the `selected`
route with the layer each of `provider`, `model_class`, `effort` and `model` came from (and `moved` when route choice took a
fallback), the `stop` when no route can start, the `aicore.providers.available` value and layer of each provider
involved, and the `gates` in force. Without `--plan` and `--item` the options are those of the configuration, the
scenario and the pack; with them they are the recorded options of the newest conductor run of that item
(`ITEM_UNKNOWN` when there is none), including the minimum class and effort the work required. A candidate or the selected
route that a run would refuse before any work (the minimum of the work, `instructions.sandbox = require`) is reported with its
code, and `stop` names it.

`--run RUN --item I` selects exactly that run; an unknown run or item never falls back to the newest run.
The additive `used` object comes only from its `routes.json`, whitelisted to `provider`, `model`, `effort`, `class`
(`null` when no route was recorded). `available_now` holds the current candidate's whitelisted `route`, `available`
and `stop`; current configuration and gates can change it without changing history. Existing `selected` and
`candidates` still describe availability now. Without `--run`, `--plan`/`--item` retains the newest-run lookup.

### Capacity gates

A provider whose account quota is known to be exhausted is not started again before its reset. `conductor/gates.py` keeps
the machine file `<state>/orch/provider-gates.json` (`provider-gates/v1`, one entry per provider: `until` UTC, `class`,
`code`, `set_by`, `set_at`): a usage limit belongs to the account, so every conductor of the machine shares it. An entry
whose `until` is in the future forbids the provider; an expired entry is ignored and dropped by the next write; of two writes
the later `until` wins. A write is a read-modify-write under `flock` on `provider-gates.lock` beside the file and an atomic
replace, so two conductors never lose each other's entry and a reader sees a whole file. `orch conduct gates [--json]` lists
the gates in force; `gates --clear [PROVIDER]` removes one or all (so does deleting the file); it needs no project. The
file is the records/v1 kind `provider-gates`: a missing file, a symlink or a file that is not regular is no gates, but a
regular file that is not JSON (`STATE_CORRUPT`) or not `provider-gates/v1` (`RECORD_INVALID`, with the JSON pointer)
stops the run that reads it and makes `orch conduct gates` exit 1; remove the file to reset the gates.

### Provider failures

A role that fails at the provider (it exits with an error, or its stream ends in one) is not told that its answer was rejected;
`ROLE_OUTPUT_INVALID` keeps the old text. The process adapters (`process.py`) read the failure signals of the stream and
`aicore.provider.errors` classifies them into an `error/v1` record (class, scope, `retry_after_s`, evidence); `_role` then asks
`retry.decide` once, with the class, whether the role writes (`tools.filesystem` of its manifest) and whether the tree changed since
the step began, `limits.retries` and `limits.provider_wait_max_s`, `on_error` (over the conductor default `unknown` → `retry`) and
the `fallback_routes` of the role:

| Decision | What the conductor does |
| --- | --- |
| `retry` | repeats the role with its original prompt; when the provider CLI had already repeated the request (`api_retries`) and the class is transient (`provider_internal`, `transport`, `rate_limit`), only after a pause (the reset time, else full jitter `min(300, 30·2^(attempt−1))·random()`): one owner repeats a request, the conductor only bounds the time |
| `retry_after` | a `PROVIDER_WAIT` beacon, the wait (cancel is looked at every second), then the repeat |
| `fallback_route` | takes the route retry.decide names after the admission: not below the class or effort the work requires, startable here (command, transport, provider sandbox) and not gated; then a `ROUTE_FALLBACK` beacon, `routes.json` is rewritten and the next calls of the role use the new route; a route that fails the admission is a stop with the reason |
| `reconcile` | a writing role that left changes in the tree continues: the repeat prompt is the original one plus `# The previous attempt failed and left changes` (base commit, `git status --short`, `git diff --stat HEAD`, the checks closed so far). The changes are never discarded; a reconcile counts against `limits.retries` too |
| `replan` | `PROVIDER_CONTEXT` |
| `stop` | the code of the class (see Stops); the repeats of one step are bounded by `limits.retries` |

An exhausted account quota with a known reset is also written as a capacity gate when it is seen, so the next piece and the
next run do not start the provider again; a wait that is longer than `limits.provider_wait_max_s`, or a quota whose reset
is unknown, goes to a fallback route or stops (`WAIT_TOO_LONG`, `RETRY_AFTER_UNKNOWN`). A quota that is still refused after the reset the provider named (`retry_after_s` 0) counts as unknown: no repeat at once, no gate, and the stop message gives the provider's own reset time as already past, not "resume after now". The role's step result records
`error` (error/v1), `api_retries` and `decisions`.

The reviewer has a fallback by default (`fallback_routes`): a review is too dear to lose when grok cannot start (no CLI), is
gated (its quota is exhausted) or fails and the policy says `fallback_route` (`on_error`). A route that cannot start, or is
gated, is replaced when the routes of a piece are chosen (`ROUTE_FALLBACK`, `CAPACITY_GATED`); a role that fails at the provider moves
by the decision of `retry.decide`. The claim tells the work source where its actor comes from: `--actor-source options` with the `--actor-field`s the executor stage of `--options` names (provider, model, effort; a provider alone keeps the plan's model, as the stage merge does) and `--actor-class` for a class named without a model (the source resolves its model on the provider of the merged actor), else `default`. An explicit executor of the run wins over the executor a plan pins, as it does at execution; the source answers a replaced plan value as `actor_override`, which the run prints as info `ACTOR_OVERRIDE` and keeps in `state.claims` and the `run.json` of the source run (a repeated claim of a closed piece, as a group review makes, keeps the record). `run --dry-run` shows what a run would do (`claim_actor`: the actor a real run hands to `source claim --actor`, with a warning when it is not the routed executor, since the source refuses a piece whose route pins another one; `batch`: whether the pieces are one batch, the default for several; `ready`: whether `--ready` picks them): `fallback_routes`, the `gates` in force, the
`reviewer` selector with the layer that set it, and `route_notes` (a route replaced at selection and why).

A fallback route is admitted by the same rules as a route at the start: not below the class or effort the work requires,
startable here (command, transport, provider sandbox, `instructions.sandbox: require` for a Claude Code role with Bash) and not
gated. A route taken is remembered in the state of the piece, so a resumed run starts on it, not on the route that failed.
A role is checked against the gates again when it starts: when an earlier role of the piece exhausted its provider, it moves to
a fallback route, or waits when the gate ends within `limits.provider_wait_max_s`, or stops with `PROVIDER_QUOTA` before the call.

When the provider of a role is gated as the routes of a piece are chosen, the role moves to the first admissible
`fallback_routes` entry (`CAPACITY_GATED`, `ROUTE_FALLBACK`); without one the piece stops with `PROVIDER_QUOTA` before any
work (an optional context scout is skipped instead, when its stage allows it).

### Deviations fixed inside the piece

A finished executor round that reports a `deviation` issue with `auto_fixable: true` gets one correction round before the
checks, when all of this holds: every path of its `evidence` (`path:line`; a check id `V1` is not a path, and at least one
path is needed) lies inside `scope.write_set`; the input has acceptance checks; the class is not `spec_mismatch` and the
outcome is not `owner_decision`; and the `corrections` budget (`_allowance`, shared with the review corrections: the fix
is one correction) allows one more. The round is an executor round (`executor.<n+1>`) whose prompt has the section
`# Fix this deviation` (text, impact, evidence); the acceptance checks run on its result like on any candidate. The
beacons are `DEVIATION_AUTOFIX` (the round starts) and `DEVIATION_AUTOFIX_SKIPPED` (the budget is spent: the deviation
stays as reported). When the piece ends green the deviation is registered with `outcome: accepted`, `next: fixed in correction N`
and a plan note "deviation fixed in correction N: …"; when the executor reports it again, or the piece is blocked, it is
registered as the executor reported it. That the change is safe (no public interface, no product decision, no security
boundary) is the declaration of the role (`roles/executor.md`): the conductor checks only the write set and the checks.

### Dynamic review (risk score)

A pack without review (`solo`, `scout-solo`) still gets one for a risky piece. After the executor and check rounds the
engine collects facts (`risk.py` is a pure function, no model is asked): the changed paths (git), the paths outside
the write set, the changed lines, a red check in the first round, a deviation (reported or auto-fixed) and
`review_recommendation.recommended` of the executor. `risk.score(facts, config)` adds the weights of the features
that hold, at most 100:

| Feature | Holds when | Weight |
| --- | --- | --- |
| `public_cli` | a path matches `patterns.public_cli` (`bin/**`, `**/cli.py`, `packages/*/scripts/*.py`) | 25 |
| `schema` | `patterns.schema` (`**/schemas/**`, `**/migrations/**`) | 25 |
| `security` | `patterns.security` (`**/auth/**`, `**/security/**`, `**/permissions*`, `**/*secret*`, and the code that confines the roles: `**/sandbox*`, `**/ro-run*`, `**/launch-catalog.json`, `**/roles/*.json`, `**/run-policies/**`, `**/hooks/**`, `.github/workflows/**`, `**/install.sh`) | 30, critical |
| `shared` | `patterns.shared` (`packages/aicore/**`) | 15 |
| `diff_size` | more than `diff_lines` (400) changed lines | 10 |
| `red_first` | an acceptance check was red in the first round | 10 |
| `deviation` | a deviation | 10 |
| `outside_write_set` | paths outside the write set | 15 |
| `executor_recommended` | the executor recommended a review | 30 |

`[orch.conductor.risk]` (`weights.<feature>`, `patterns.<feature>`, `diff_lines`, `critical`) changes them in any config
layer; a weight of 0 turns a feature off. A feature named in `critical` (default `["security"]`) adds the review on its
own, whatever the score: a lone sandbox change weighs 30, below the threshold, and must still be read by a reviewer;
`critical = []` leaves only the threshold. Score and features (with their evidence) go to `<run>/<item>/risk.json` and
`state.risk`; a resume reads them again. At `review.dynamic_threshold` (default 60) `state.dynamic_review` is set, the
`reviewer` and the triage role are resolved on the spot (availability, gate, preflight, `routes.json`), the beacon
`REVIEW_ADDED` and a plan note name the score and the features, and the usual review → triage → correction cycle runs
within the limits. Below the threshold nothing changes. `review.dynamic: false` (give the reason in `rules`) or
`limits.review_rounds: 0` never adds a review; a pack with a review is not scored.

### Questions of the executor (D11)

The executor asks in `stage-report.questions[]` (`id`, `revision` ≥ 1, `kind` `clarification|decision|approval|credential`,
`text`, `options[{id,label}]?`, `answer_schema?`, `default?`, `blocking`, `assumed?`, `risk?`; `blocking: false` needs
`assumed`). A question is a decision tied to a saved continuation, never a waiting process (headless roles have no
stdin). `default` (a proposal), `assumed` (what the executor went on with) and a timeout are three different things:
nothing is ever answered on a timeout.

- `blocking: false`: an `assumption` issue "question Q: text — assumed: V" goes into the registered report; the work goes on.
- `blocking: true` needs a `blocked` report (an `escalation` issue; a report that says otherwise is repaired or repeated).
  `[orch.conductor] questions` decides (default `queue`):
  `queue`: the piece is `blocked` with the escalation `QUESTION: <id> <text>` and waits (`state.items[<item>].waiting`):
  the run stops with `WAITING_DECISION` (exit 4), see [Waiting for a decision](#waiting-for-a-decision);
  `deny`: blocked at once with `QUESTION_DENIED: <id> <text>`, nobody is expected to answer;
  `defaults`: a question with a `default` is answered by it **once**, by `policy`, and the round is asked again as
  `executor.<n>-q<k>`; a question without one, or one the executor asks again, is queued;
  `advisor`: the advisor role reads the question ([The advisor](#the-advisor-p104)); advice that needs no owner answers it
  with `resolution.by = advisor`, any other advice is queued with the question.
- `approval` and `credential` questions always stay open for the owner in all four modes
  (`QUESTION_OWNER_ONLY`); neither a default nor advisor advice answers them, and `deny` does not close them.
- The question is saved in `state.questions[<item>]` and in `<run>/<item>/questions.json` with its binding
  `{run, item, step, input_digest, input_part_digest}` (the full input digest and `contracts.required_digest` of its
  substantive part), its `status` (`open`, `answered`, `applied`,
  `assumed`, `denied`, `stale`) and, once answered, `resolution {value, by, at}`. Beacons: `QUESTION_QUEUED`,
  `QUESTION_DENIED`, `QUESTION_DEFAULT`, `QUESTION_ANSWERED`, `QUESTION_OPEN` (retry without an answer), `QUESTION_STALE`.
  Every automatic resolution adds `authority {mode, gate, code_categories, confidence}`: mode `defaults` or `advisor`,
  the effective gate and code categories at the decision, and the advisor's confidence (`null` for defaults).
- `orch conduct answer` writes only the resolution into `questions.json`, under `questions.lock` of the item (both in
  the item folder of the run); `QUESTION_UNKNOWN` (`<item> has no questions in run <id>`, refused before anything is
  written, so a mistyped `--item` leaves no folder), `QUESTION_NOT_OPEN`, `ANSWER_INVALID` (a decision takes one of its
  options, a clarification may take `--text`); it never touches the run.
  `orch conduct questions [--run R] [--json]` lists the open ones with their age; one older than `limits.question_warn_s`
  (default 1800, 0 off) is `OVERDUE`, in the observer report too.
- `resume --run R --retry ITEM` merges the answers into the state. New bindings compare `input_part_digest` over
  `goal`, `scope`, `acceptance`, `constraints`, `decisions`, `route`, `result_contract` and `escalation`. Changes to
  provenance, lessons or other context, including the source's blocked registration, preserve the answer.
  Legacy records without that field still compare the full `input_digest`. A changed substantive part produces
  `QUESTION_STALE`: the answer is kept as `stale_resolution`, the question gets
  `revision + 1` and the executor, which is not told that answer, asks it again. The executor of every later round gets the
  section `# Answers` (question, answer, who answered).
- **Decisions (P7.6).** An answer is not lost with its run. After the piece is registered (never earlier: a decision with
  `applies_to` the piece changes `input.decisions`, which is part of `input_part_digest`, and would make an answer that
  still waits stale), the conductor records every `applied` question of kind `decision` or `clarification` whose
  `resolution.by` is a person, `advisor` or `panel` (not `policy`, not an earlier decision), and every advice it applied on
  its own to red checks or a rejected finding (`state.items[<item>].advice_applied`), as an accepted decision of the work
  source: `orch.py source decision --run R --ref ITEM --file decisions/<question id>.json` (work-source/v1 operation
  `decision`; the plan source adds a `D#` with `applies_to` the piece, `answered_by` `owner|agent` and an `origin`; the file
  source appends to `decisions.json` of the artifact folder). The request is kept in `<run>/<item>/decisions/`, its receipt
  in `receipts/decision-<question id>.json`; a repeat for the same `question_key` and piece is a no-op. A blocked piece records nothing
  (its questions may still wait); approval and credential answers are never recorded. A source that has no such operation, or
  refuses it, is the info `DECISION_NOT_RECORDED` (the request stays in the run): the piece and the run do not change.
  `question_key` is `qk-` and the first 16 hex characters of `question_digest`, the SHA-256 of the canonical JSON
  (`sort_keys`, `(",", ":")`, `ensure_ascii = False`) of `{item, kind, text, options, answer_schema}`: the text with its
  whitespace collapsed (case and digits stay), the **full** definition of each option (by id, not only the id) and the
  answer schema. Another number, option text or schema is another question.
- **Reuse.** A later run of the piece finds the accepted decision in `input.decisions` (the planner bridge passes
  `question_key` and `question_digest` from its `origin`). Before a blocking question of kind `decision` or `clarification` is
  queued, a decision with the same `question_key` **and** `question_digest` whose value this question can take (the id of
  one of its options, alone or before `: label`, or a text that passes `answer_schema`) answers it: `resolution.by =
  decision:<D#>`, `QUESTION_REUSED`, and the round is asked again as `executor.<n>-q<k>` with `# Answers`, without a
  stop. A decision that names the question but does not fit it is `QUESTION_REUSE_REFUSED` (`reason: key` the digest
  matches another key, `digest` the key matches but the meaning is not proven, `value` the value is no answer of this
  question) and the question goes the ordinary way. `approval` and `credential` are never reused. A reused answer that the
  executor asks again goes to a person, like a default.

### Waiting for a decision

A blocking question never keeps a process, and a run that waits is not a failed run. When a piece is blocked on questions
that are `open` (a question of the executor under `queue`, `advisor` or `defaults` without a default, an `esc-<n>`
question, an advice question `orch-advice-<n>`), its state gets `waiting = {question_ids, since}` (records/v1 state) and:

- `on_blocked: stop` (the default): the run stops with `WAITING_DECISION`, `run.end` outcome `waiting`, `state.status`
  `waiting`, exit code 4.
- `on_blocked: report`: the independent pieces go on; at the end, when some piece still waits and nothing else stopped the
  run, the outcome is `waiting` and the exit code 4 (a stop such as `DEPENDENCY_BLOCKED` keeps its own code 1).
- `conduct status --json` has `status: "waiting"` and `waiting: [{item, question_ids, since}]`; `conduct runs` shows
  `waiting`; `prune` leaves a waiting run alone.
- A denied question (`questions = deny`, `QUESTION_DENIED`) and any block without a question stay `ITEM_BLOCKED`, exit 1.

`orch conduct continue --run R [--item I …] [--partial]` goes on with the waiting pieces: for each one it checks that every
blocking question is answered (`orch conduct answer`; status `open` with a resolution, `answered` or `applied`), then does
what `resume --retry` of those pieces does. A piece with an unanswered blocking question starts nothing and the command
stops with `QUESTIONS_OPEN` (exit 1, the list `item:question`); with `--partial` only the ready pieces continue and the
others stay waiting (the run then ends `waiting` again). `NOT_WAITING` for a piece that does not wait.
`orch conduct answer … --continue` is `answer` followed by `continue --item ITEM` in one process. The source must have
reopened the piece, as for `resume --retry`.

**Classes of an escalation.** An `escalation` issue of a blocked report may name `escalation_class` (stage-report):
`decision` without a question in the report becomes the blocking question `esc-<n>` (kind `decision`, the text of the
escalation, no options) and takes the normal question flow, every gate of it included (`human_gate`, only the owner answers
approval and credential, the advisor and `defaults` follow their rules); `environment`, `pre_existing_red`, `scope` and
`authority` never become questions and never reach the advisor: the escalation text takes the code `ENVIRONMENT_BLOCKED`
(with the hint to run `orch.py doctor`, check the sandbox settings and grant a path with `--allow-path`),
`PRE_EXISTING_RED`, `SCOPE_EXPANSION` or `AUTHORITY_REQUIRED`, which is the `code` of `orch.work.blocked` and the reason of
`item.end`. A `CODE:` the executor wrote itself stays. The class is the conductor's routing and is not part of the report
registered with the source. The role text (`roles/executor.md`, section Autonomy) tells the executor when to use which.

### The advisor (P10.4)

The role `advisor` (`roles/advisor.md|json`; class `frontier`; filesystem read, shell read-only, network allowed, no write
authority; launch entry `claude-code` with `--tools Bash,Read,Grep,Glob` and the one allowed command
`python3 *orch.py research query *`) gives one opinion on one problem. It is on by default (`[orch.advisor] enabled = true`, with `[orch.conductor] questions = "advisor"`); `enabled = false` or `questions = "queue"` sends every blocking question to the owner's queue. The human gate below still holds security, destructive, public-api and scope-expansion advice for the owner.
With `enabled = true` the conductor asks it, deterministically and at most `max_rounds` times per piece (default 2, all
triggers together; past it the problem goes on as it would without an advisor):

| Trigger | The problem (`problem_ref`) | Applied advice |
|---|---|---|
| a blocking question, with `[orch.conductor] questions = "advisor"` | `question:<id>@<revision>` | the question is answered with `resolution.by = advisor` (the id of the recommended option; free text of its option when the question has none) and the executor round is asked again with `# Answers` |
| red acceptance checks once the `check_fixes` allowance is spent (before `CHECKS_RED`) | `checks:<round>` | one more correction round whose package carries the advice (`# Advice`) |
| a Blocker or Major finding the triager rejected | `findings:<review round>` | `triage.<n>-a`: the findings are triaged again with the advice |

The advisor reads the problem and the local evidence (the report of the executor, the red checks or the findings and the
triage, the diff against the head, cut at 40 000 characters) and may ask the sources of `[orch.research.sources]`. It answers a
closed `advice` (`schemas/conductor/v1/advice.schema.json`): `problem_ref`, `options[{id, text, pros, cons}]`,
`recommendation` (an option id), `confidence` (`low|medium|high`), `sources`, `needs_owner` and the optional `category`
(`security|destructive|public-api|scope-expansion|other`). A question with options keeps its option ids; a recommendation
that is not one of them is held. The advice is kept as `advice-<n>.json` in the artifacts of the piece, and its agent run in
`agents/<id>/` has `causation` = the `problem_ref`.

The human gate: `[orch.advisor] human_gate` (default `security`, `destructive`, `public-api`, `scope-expansion`)
can be set only by defaults, the machine or the caller (invocation and flags). A project or environment attempt is
`CONFIG_LAYER_FORBIDDEN`; projects can add categories through `human_gate_extra`. Extra gates accumulate from every
layer's history: neither `[]` nor `_unset` removes a lower layer's category. `min_confidence` defaults to `medium`;
the strictest value across all layers wins (`high` > `medium` > `low`), including defaults and values before `_unset`.

Advice is held if `needs_owner: true`, its model category belongs to the effective gate, a category computed by code
belongs to the gate, or its confidence is below the effective minimum. Code examines changed paths **and** the write set
using `conductor.risk.patterns`: `security` for `security` patterns, `public-api` for `public_cli` or `schema` patterns,
and `scope-expansion` for changes outside the write set. For code categories, builtin patterns and patterns established
by trusted machine, invocation or flag history form a retained floor; effective project/environment patterns may add
matches. Empty arrays, replacement arrays and leaf/parent `_unset` cannot erase that floor. Heuristic risk scoring
still uses the effective configurable patterns, weights and critical features; the retained floor applies only to
code categories and their owner hold. Existing human-gate, confidence, needs-owner and scope-expansion gates still apply.
Risk weights do not disable these gates. A model's `other`
category cannot hide a security path. `ADVICE_HELD` names the source (`advisor`, `code` with matching paths, or
`confidence` with actual and required levels). It is handled as `queue`: the piece is
`blocked` with `QUESTION: <id> <text>` and the advice (file, recommendation, confidence, why the owner decides); the
question is saved with the advice (`advice` in `questions.json`). A held question of the executor is that question; for red
checks and a rejected finding it is a new question `orch-advice-<n>` (kind `decision`, the options of the advice). `orch conduct
answer` and `resume --run R --retry ITEM` then apply the owner's choice the same way: the correction round or the repeated
triage carries the option the owner chose (`by owner`), and the closed rounds, checks and the advice are not repeated. An
approval or a credential question is the owner's by its kind and is not asked of the advisor; the policy answers a question
only once. A failed advisor (`ADVISOR_FAILED`), a spent `max_rounds` (`ADVISOR_LIMIT`) or `questions = advisor` without
`enabled` (`ADVISOR_DISABLED`) leave the problem as it would be without one. Beacons: `QUESTION_ADVISED`. The advice the
conductor applied is recorded as a decision of the work source after register ([Questions](#questions-of-the-executor-d11)).

**The panel (D10).** `[orch.advisor] panel = ["grok/frontier/high", "claude-code/frontier/high", ...]` (2 or 3 routes
`PROVIDER[/MODEL_CLASS[/EFFORT]]`; fewer is off) replaces one opinion with the votes of independent advisors when
`panel_on` fires: `low_confidence` (default: the single advice of a problem has confidence `low`) or `always` (the panel
advises first). The panel is **one** round of `max_rounds` and at most `len(panel) + 1` calls (the member calls and one critic;
the single advice that started a `low_confidence` panel is not counted), every call a step admitted by the token budget like
any other (`advice-p<i>.<n>`, `advice-critic.<n>`).

1. Each member gets the same prompt as a single advisor, on its own route, and never sees another answer.
2. The conductor compares the recommended option ids: **agreement** (all equal) is applied; a **majority** (more than half)
   gets one round of critique by the first member of the minority, who reads the anonymised positions (the block `Panel
   options`) and must cite evidence in `sources`: when the critic recommends the option of the majority the majority stands,
   otherwise (another option, no evidence, or a critic that failed) the owner decides; a **split** (two members who differ,
   three different answers) is the owner's, with no critique.
3. The result is one closed advice: the strictest category, the lowest confidence, the union of the sources and any
   `needs_owner` among the members that stand behind the choice (all members for a split), the options of those first and the
   rest after them, so the owner sees every way. It goes through the same gates as one advice (`human_gate`,
   `min_confidence`, categories computed from the changed paths): a panel never lowers a gate.
4. A member that cannot start (`codex` has no advisor launch entry; a missing CLI; a gated provider) is skipped with the info
   `ADVISOR_PANEL_FAILED`; with fewer than two answers the single advisor decides (`ADVISOR_PANEL_FAILED` names how many
   answered). A spent `max_rounds` queues the next problem; it does not start another panel.

The record is `advice-<n>-panel.json` (`schemas/conductor/v1/advice-panel.schema.json`: `members[]` with route, file and
advice, `synthesis {kind, chosen, advice, critic?}`, `trigger?`); `ADVISOR_PANEL` (info) says the kind. A question the panel
answers has `resolution.by = panel` and `authority.mode = panel`, and its decision in the plan has `origin.kind = panel`.
For a question with options the members vote by option id (the question fixes the ids). For checks, findings and a question
without options each member names its own ways, so the same id may mean different things: members (and the critic) agree
only on the same id with the same text (whitespace and case aside); anything else is a different recommendation. A panel
record that fails its schema is not written: `ADVISOR_PANEL_FAILED` says why and the single advisor decides.

### Resume

`orch conduct continue --run RUN` is the one command for pieces that wait for an answer ([Waiting for a decision](#waiting-for-a-decision)).
Without `--retry`, a blocked piece's saved answer stays pending. The conductor emits
`QUESTION_ANSWERED_NOT_RETRIED` with the retry command; if no piece starts during that pass it stops with the same
code and exit 1. If other work starts, the message is only a beacon. `orch conduct answer` leaves the question
`open` with a `resolution` on disk; resume with retry merges and consumes it (`answered` records are also recognized).

`resume --run RUN --retry ITEM` also takes back a piece that stopped as `blocked` (after the source has reopened it, for example the planner's `reopen`; a piece held on advice for the owner, whose question `advice-<n>` is answered, needs no executor round that reported `blocked`): the input is built again from the amended plan, and the steps from the executor round that reported `blocked` on, and the closing steps, are repeated; the earlier rounds and the work in the tree are kept (`RETRY_NOT_BLOCKED` when the piece is not blocked). `resume --run RUN` runs the same loop again. Without a retry, a plan amended while a piece runs reaches its next executor round anyway: the brief is asked again before every correction round and replaces the input when its digest changed (`INPUT_REBUILT`).

For one stopped, unfinished executor in a one-piece run, an explicit fresh continuation is available:

```sh
orch conduct resume --run RUN --retry ITEM --fresh-context --options FILE --model-launch-ceiling TOTAL
```

`FILE` contains the full recorded effective options. Rules may change; supported retry/check limits and scope may
only tighten. The executor must use `session.executor = per-item`, with no fallback routes. The candidate and pinned
route stay fixed. `TOTAL` counts every historical and future physical launch admission, including reservations before
a process starts, and cannot increase an earlier continuation ceiling (`MODEL_LAUNCH_CEILING`). Missing or changed
historical request/authority evidence refuses continuation. Preparation archives the old brief, options and stopped
attempt, rebuilds the input and retains token usage, retry counters and all previous attempts. Ordinary resume keeps
its existing behavior.

`run --adopt` starts the first piece on a tree that already holds an earlier attempt of it (all changed paths inside its
write set, else `WORKTREE_DIRTY`): the executor is told to check and finish that work, not to start over. The artifact
folder of the piece (`artifacts/<item>/…`: evidence, review verdict of the earlier attempt) and the plan folder are
always allowed: they are not counted as the role's changes and are not listed to the executor.

A piece that stops before any executor round (`WORKTREE_DIRTY` at adopt, a refused route, a failed brief or prepare) gives
its claim back to the work source (`CLAIM_RELEASED`; the source's `release` op), so a new `run` can claim it again without
`ITEM_OWNED`. A source without `release`, or a refusal, prints `CLAIM_KEPT`; then, or when a run died before it could
release, `release --run RUN --item REF [--item REF2 …] [--reason TEXT]` does it by hand (`RELEASE_WORK_BEGAN` when an executor round ran:
`settle` or `resume --retry` the piece instead); `release --run RUN --all` gives back every piece of the run that nobody worked on and that is not
closed (a batch that stopped before any work: all of its pieces are in progress), names the pieces it kept, and prints `RELEASED_ALL`. `resume --run RUN` of a stopped run needs none of this: it claims
its own piece again.
`settle --run RUN --item REF --outcome … --reason …` sets the outcome of a piece by hand after it was finished or given up
outside the conductor (for example committed with the work source's own command); the journal keeps the reason. A closed step returns its recorded result and prints `stage.skip`; a
piece that closed (done or blocked) is not claimed again; a piece that stopped half-way continues on its own working
tree. The configuration of the run is read again, so a fixed provider or a corrected `[orch.conductor.argv]` takes
effect.

## Bounded corrections: fix-brief/v1

Every review correction, including a correction combined with red checks, is rendered from a
validated `fix-brief/v1` at `<item run directory>/fix-briefs/executor.<n>.json`. The correction
block's prompt manifest names that file as its origin. `review.fix_brief` (`fix_brief`) merges by key and defaults
to `max_findings: 12`, `max_chars: 24000` (rendered characters). Findings sort by Blocker, Major,
Minor, Nit, then high, medium, low confidence, then id. Blockers always reach the executor, even
above either cap: the informational `FIX_BRIEF_OVER` message reports actual and configured counts.
An insufficient non-Blocker character budget for the required framing and deferred reference is refused.

Problem, fix, observed output and reproduction command fields are bounded to 1200, 800, 600 and
400 characters respectively, keeping head and tail with `… [clipped N chars; full: <ref>#<id>]`.
The `clipped` array names those fields; a delivered finding is never removed or cut as a whole.
The brief carries stable finding keys, scope constraints, check ids and a deferred summary with
counts by severity and a link to the full review verdict. Undelivered confirmed findings persist
as `state.items[ref].deferred_findings` references to validated review/triage steps and enter the
next correction even if the next reviewer reports no new findings. At the correction wall they
remain deferred in the receipt and become an explicit plan note with the artifact reference.
They are never silently counted as corrected. Keys recognize exact repeated findings, including
line drift; they are not semantic deduplication of reworded defects.

No reviewer stream, full check log or session transcript enters a correction brief. Each failed
check's tail is bounded to forty lines and 4000 characters including an omitted-count marker and
the full log path (`checks/<round>/<V#>.log`); failure-header samples are bounded separately to
4000 characters. Read the referenced full log when diagnosing all independent failures.

### The route of a correction

`review.correction_route` (`executor`, the default, or `bounded-implementer`) names the role that runs the correction rounds of
confirmed review findings. With `bounded-implementer` a correction without a Blocker finding runs on the route of the
`bounded-implementer` role (launch catalog economy/medium unless a stage says otherwise; its own session, never the executor's);
a correction with a Blocker finding always runs on the executor. The step stays `executor.<n>`; its agent, route and prompt are
the role's. The bounded route is used only when it starts here and meets the minimum of the work: the claim's `route.correction`
(`{class, effort, provider?, model?}` of the plan item, carried by the answer of `claim`), else the whole ordinary minimum
(the claim's `route` completed by the execution input's `route.minimum`, so the provider and model the plan pins count) —
without `route.correction` nothing is relaxed. The same minimum admits every later route of the role: a fallback route taken
after a quota or provider failure that is below it, or off a pin, is refused and never runs (the stop is the provider's). Otherwise the correction stays with the executor and an info beacon
`CORRECTION_ROUTE_REFUSED` says why (class or effort below the minimum, a pinned provider or model, a command that cannot start).
The group review follow-ups (`review_followup`) always run on the executor.

`CORRECTION_SCOPE_GREW`: after a review correction round, the paths the round changed (the tree before the round is kept in
`state.correction_baselines["files-<n>"]`, so a resume compares with the same tree) minus the paths of the findings of its
fix-brief, the test files inside the write set (`*/tests/*`, `test_*.py`), `CHANGELOG.md` and the documentation (`docs/**`,
`packages/*/docs/**`) are the growth. On the executor route the growth is an info beacon `CORRECTION_SCOPE_GREW` and an accepted
`other` deviation of the report (evidence: the paths), which the next review round reads with the diff; on the bounded-implementer
route the piece is blocked (stop `CORRECTION_SCOPE_GREW`, see *Stops*). The check is repeated before each review round and
before the piece finishes for every closed correction round, so a conductor that stopped between the saved round and its check
still blocks (or reports the deviation) after a resume. A report with the deviation registers as `done_with_deviations`.

The class of a route that names a model is the class the model catalog gives that model
(`aicore.provider.models.admitted_class`: entry id or alias, then patterns; retired entries are skipped; the highest class of the
roles wins), when it is lower than the label of the stage or of the launch entry: `{model: haiku, model_class: implementation}`
is an economy route and is below an implementation piece (`ROUTE_UNDERSHOOT`). A label never raises a class. A model the catalog does
not know keeps the label and is said once per role (`ROUTE_MODEL_UNKNOWN`, info). The planner keeps its own copy of the algorithm
(`command-routing.json`); a bridge test holds the two together.

## Interactive review-only runner

`orch input adhoc --review BASE..WORKTREE --plan P --item I` builds a read-only execution-input.
`orch conduct run --input FILE --options REVIEWER_OPTIONS` runs only `review.1` and `triage.1`,
then registers through the file source. It does not run scout, researcher, executor, advisor,
corrections or commit (even with `--commit`). A dirty worktree is the subject
of review, not adopted executor work. Named heads such as `BASE..HEAD` bind the revision's blobs
and diff; `WORKTREE` binds `git diff --name-only BASE` plus untracked paths.

The existing receipt is written with subject `P.I` when both identities are supplied, otherwise
the execution input id. The default findings-shape procedure gets engine evidence from the
validated review and triage documents. Acceptance commands run before registration with Linux Landlock
protecting the checkout, an isolated writable `TMPDIR`, and the configured check and idle timeouts.
The guard starts Python with `-I -S` (isolated and without site initialization) and uses seccomp to deny metadata changes, including
chmod, timestamps and extended attributes. Because seccomp cannot filter by path, those operations
are also unavailable in scratch space; ordinary scratch file creation and writes remain available.
The guard permits `ioctl(FIOCLEX)` for closing descriptors on exec (needed by Python script startup);
other ioctl requests remain denied.
This metadata guard currently supports Linux x86-64; on other platforms or if it cannot be installed,
the run stops with `METADATA_GUARD_UNAVAILABLE` without executing the command. Native syscall numbers
335–423 and numbers beyond the audited table (469) are denied until audited. A named revision
requires a clean checkout at that revision. Stdout ends
with one compact JSON line validated as `review-summary/v1`: `run`, `receipt`, `verdict`, `open`, and findings with only `key`, `id`,
`severity`, `location`. Raw streams stay at `<run>/<input>/streams/review.1.jsonl`. An interactive
session reads only that JSON and the receipt, then supplies `--review-receipt` to finish. Review
intent expressed by the owner is first recorded in the plan (D13); the canonical intent table and
runner commands live in planner's plan-run, reviewer-selection and intent-routing documents.

## The environment of a check

A check command tests the project, so it does not inherit the install roots of the orchestrator the conductor runs from:
`AICORE_ROOT`, `SKM_ORCH_ROOT`, `PLANNER_ROOT` and `PLANNER_PLAN_PY` are removed from its environment when they lead outside the
project (a frozen or installed copy of the orchestrator would otherwise be tested instead of the project's own code, as a
piece that adds a module to the foundation found out). Roots inside the project stay.

The run names itself to the check: `SKM_CHECK_RUN` (the run id), `SKM_CHECK_ITEM` (the piece reference) and `SKM_CHECK_ROUND`
(the number of the round), so a test runner can keep a result only inside one run. `SKM_TEST_JOBS` is the jobs budget the
check may use: the budget of the owner (its own `SKM_TEST_JOBS`, else the CPUs) divided by the checks that run together
(`checks.parallel`, never more of them than the budget), never more than the owner gave; `jobs.txt` in the folder of the round's logs
reports the requested budget, how many checks run together and the share of each. The orchestrator names no script of a
project: whatever the check runs reads these variables.

A green check is kept for the next round of the same run only when its evidence file carries a fingerprint of everything it
read: the candidate, the check as written and its directory, the environment (values are hashed, never stored), the programs
(path, size, time) and the data files (content: fixtures, configuration) that its command line (quoted names with spaces
included) or an environment value names and the candidate does not carry, that is files outside the project and git-ignored
files inside it. The shell expansions of the line are followed as bash would expand them in the directory of the check with
the environment of the check: unquoted globs (`*`, `?`, `[...]`, `**`, also in the value of `NAME=...`/`--option=...`, in a
quoted script such as `bash -c '...'` and through a variable that holds one), brace lists and ranges (`{a,b}`, `{1..3}`); every
file they match is an input, so a file that is added, removed or changed misses. When the inputs cannot be established they are
an unknown input and nothing is reused (a miss, never a guess): an existing folder that the line names or that a glob reaches,
wherever it lies (the project root `.`, a tracked, untracked or git-ignored folder of the project, a partner root or a folder
below it, any other folder outside the project; a literal argument, a path in a quoted script, an entry of a `a:b` list, a
variable the line uses, including a `*_ROOT` one), because its listing and the files below it, git-ignored ones included, are
not fingerprinted (`grep -r x data`, `find .`, `ls dir`); a glob or brace word with an unset variable, a path or an argument
built by a command (`$(...)`, backticks), more matches than the limit, a range that cannot be read, a line with unbalanced
quotes or brackets, a name built from an unset variable or a file that cannot be read. The same holds for the forms the shell
does not expand itself: a `case` whose branch pattern spells a path, a glob or a variable; a `PATH`-like `a:b` list of
patterns; a quoted pattern that holds a glob character with an existing folder in front of it (`'/dir/*.txt'`, also a `:` list
of them); and any quoted glob in a line that runs `find`, `fd` or `fdfind` (`-name '*.txt'`). Only the folders of the
evidence and the logs of the checks (output) are exempt. What stays reusable: the working directory itself (implicit
context), a folder that only the environment holds (`HOME`, `TMPDIR`, a variable the line does not use) and a partner root
that only the environment points to (not named by the line), whose state (HEAD and dirty digest) is fingerprinted, and the
files the line names (a literal file, a glob that matches files), whose content is fingerprinted when it is outside the
candidate. The fingerprint covers what the line or the environment names; what a program reads without the line naming it is
opaque to it. The fingerprint also holds the Python of the conductor and the state of the partner roots outside the
project. A damaged evidence file, another run, another candidate or any difference in the fingerprint runs the check again, as
does a check that changed files of the project or the files it reads outside it while it ran, an input that cannot be read, and
every check that starts after an earlier check of the round changed the tree or committed (the candidate, HEAD included, was
taken at the start of the round). A reused row keeps `reused_from` (the evidence it stands for)
and `original_seconds`; the evidence file is not rewritten. When a prior evidence file does not prove the check, the row
carries `reuse_miss`: the component that differs (`candidate.head`, `candidate.dirty_digest`, `command`, `cwd`,
`fingerprint=<short hash>`, `inputs-unknown`, `run`, `subject`), never an environment value. A first run, with no
evidence file, has no `reuse_miss`, whether its inputs are known or not. The folder of the evidence and the logs of the checks is not part of
the candidate.

A correction is built from the latest red acceptance. Both the full executor prompt and the resumed delta say that
this correction is the only current assignment and that earlier correction instructions are historical. The goal, the
scope, the authority and the acceptance contract stay in force. The focus includes a bounded sample of failure headers and
child logs the sampled check log names (`full output:`, `child log:`); the full log path stays the authority. Checks that
were red earlier and green later are listed as historical, not as work. A completion report that changes no product
file and no execution input does not start acceptance again (`CORRECTION_INEFFECTIVE`, not fixed), unless the report
carries evidence of an environment fix (`class` `environment` or `test_env`) or a confirmed nondeterministic failure
(the issue says nondeterministic and names evidence). That proof is accepted once for the same red command checks.
The pre-executor baseline and the exceptional no-diff admission are saved before execution and acceptance respectively, so resume preserves them. Journal-only input changes do not count as a correction.
Conductor runtime paths are not a product change. An unknown git state is not treated as a no-diff.

## One review for a batch: `scripts/batch-review.py`

The conductor reviews piece by piece (`review.*`); a batch is better read once, together: `batch-review.py RUN` takes the
commits of the run from its `state.json`, keeps their production diff (`--include`, default `.`, the whole project,
without tests, docs, fixtures, goldens and plans; `--exclude` adds more), asks one reviewer (the launch catalog route:
`--provider grok --model grok-4.7 --effort medium`; `high` costs three times the time and found one more Major in the one batch measured) for correctness and safety defects with a concrete failing scenario, and
writes the reply to `<run folder>/batch-review.md`, the raw reply to `streams/batch-review.jsonl` and the measures (route,
pieces, commits, prompt bytes, seconds, exit code) to `batch-review.json`, and prints `BATCH_REVIEW: … in N s` on stderr. The time of a review is the reasoning of the reviewer (its output
tokens, about 30-60 per second), not its reading: `--effort` and `--max-tools N` (default 12, in the prompt) shorten it; `--dry-run` shows the pieces, the prompt size and the command. A finding of Major and above is fixed in a separate
commit after the batch.

## The review strategy of a batch

A batch of several pieces is reviewed in the way chosen **before the first piece runs** (`review.strategy`, default `auto`):

| `mode` | Review |
|---|---|
| `each` | every piece on its own, as the run policy and the risk score say (`review.*`, dynamic) |
| `groups` | one review per group of neighbouring pieces, after the last piece of the group |
| `single` | one review of the whole batch after its last piece |
| `none` | no review |

With `auto` the rules decide (`review.strategist: rules`, the default; the strategist is a model call only when `review.strategist: model` names it, one small call on the economy route of the
triager that sees every piece (title, goal, write set, route) and the choice the rules would make, and answers a mode, the groups
(in order, at most four pieces each) and the reviewer's effort). An answer that is not a partition of the batch in order or a
failed call falls back to the rules (`policies/review_strategy.py`), which `rules` uses on its own: neighbours that work on the
same folders are read together, a piece on the foundation or a `frontier` piece is read alone, security wording raises the
effort to `high`. Naming a mode in `review.strategy` skips the strategist. The plan is kept in `state.review_strategy` and
`review-strategy.json` of the run (a resume keeps it) and announced as `REVIEW_STRATEGY` with the effort the group review
will run at (an effort named by `reviewer` wins over the plan's).

In `groups`, `single` and `none` a piece has no review of its own. After the last piece of a group the conductor reads the
commits of the group once (`review_batch`: including tests, docs and fixtures, as in `batch-review.py`), with the reviewer of the run
(`reviewer`, grok by default) at the effort of the plan, and keeps the reply in `group-review-<n>.md` of the run folder
(`state.group_reviews`).
The reserved reviewer of a last piece with `review.mode: none|self` does not override the group's requested review routes;
an explicit configuration or invocation reviewer still wins.
The reply must be one closed `json review-findings` block, with the same schema as a per-item
reviewer: verdict, findings (id, severity, confidence, location, failure_scenario, basis, optional
reported reproduction), questions and residual_risk. The conductor heals form only and validates
the schema and verdict consistency. Markdown findings and invalid JSON are `format: malformed`,
announced as `GROUP_REVIEW_FAILED`, never a clean review. Counts come from the validated JSON;
so is a group without a commit. Blocker and Major findings are corrected in a commit of their own: the conductor writes
`group-review-<n>.followup.json` (an execution-input with `provenance: review_followup`, the files the findings name as scope,
a goal rendered from `group-review-<n>.fix-brief.json` with problem, reported reproduction and correction guidance,
and as acceptance the command checks of the reviewed pieces, once each — `cd DIR && CMD` for a check with its own `cwd`, the
`cadence: phase` checks left out — so the correction is tested like the pieces were) and the beacon names the command, `orch conduct run --input <that file> --commit` (the executor corrects them, the conductor
checks and commits; native correction inside the run is not built, because the pieces of the group are already registered and
committed in the work source).

When the findings exceed one brief, `provenance.fix_briefs` carries an ordered backlog of further bounded
fix-brief artifacts, each pinned by its canonical digest. The initial goal stays bounded. The follow-up conductor
assigns the backlog to later executor rounds, records their numbers in `state.items[ref].followup_corrections`
before execution, and checks each round. These assignments share the normal piece and batch correction allowance.
Resume replays the same assignments without spending the allowance twice. If the allowance runs out, the follow-up
is blocked with `REVIEW_LIMIT`; its notes and report list every unassigned finding's id, key and artifact reference
as unresolved debt. Such a follow-up cannot satisfy `settle --group`.

A group review with a **Blocker** does not end in `finished`: the run stops with `GROUP_REVIEW_BLOCKER` (resumable;
`state.group_reviews[n].blocking`), and a resume stops again with the same code until the group is settled. The stop names the way
out: run the follow-up (`orch conduct run --input <run folder>/group-review-<n>.followup.json --commit`; the file is written by
hand at that path when the findings named no file to build one from), then
`orch conduct settle --run <R> --group <n> --followup-run <F> --reason <text>` under the lease of run R. The follow-up run F is
read without a lease and is accepted only when it ran exactly that file of this run (`source.kind: file` and the same path), is
`finished`, its one piece is `done` or `done_with_deviations`, and it committed (`GROUP_UNKNOWN`, `GROUP_FOLLOWUP_MISMATCH`,
`GROUP_FOLLOWUP_NOT_DONE` otherwise, exit 1, nothing changed). `state.group_reviews[n].resolved` then holds
`{followup_run, commit, reason, at}`, the beacon `GROUP_REVIEW_RESOLVED` is printed and the next resume goes on; no run writes into the state
of another. Major findings are not a stop: the follow-up is announced as above.

A group review that fails (the role failed, or the reply has malformed `review-findings` JSON) while a piece of the group has
`review_mode: requested` stops the run with `GROUP_REVIEW_FAILED` (those pieces have no review of their own); a resume repeats the review once
(`state.group_reviews[n].attempts`, at most 2); after the second failure the stop stays: a resume raises `GROUP_REVIEW_FAILED` again
without a third reviewer call and is no waiver, and only a review that reads (a repeated review below the cap) ends it. Without a requested piece it stays a
beacon. An empty production diff or a group without a commit is not repeated and not a stop.

A forced `review.strategy` (`groups`, `single`, `each`) takes no piece whose plan gives it `review_mode: none`: it is in no group,
and `REVIEW_MODE_NONE_SKIPPED` names it.

## Run options

`schemas/conductor/v1/run-options.schema.json`, closed:

| Key | Meaning |
| --- | --- |
| `stages` | `[{role, provider?, model_class?, model?, effort?, require_current_input_receipt?}]`, roles `context-scout`, `executor`, `bounded-implementer`, `reviewer`, `triager`, `registrar` (naming it turns the closing stage on). `require_current_input_receipt: true` requires current-request input evidence before dependent tool dispatch; see Current request input receipts. |
| `reviewer` | `PROVIDER/MODEL[/CONTEXT][/EFFORT]` |
| `rules` | short rules for the executor |
| `skills` | `[{role, names}]`; `names: ["auto"]` asks the skills bridge (`[orch.conductor] skills_bridge`, a command run as a process with `--select --role R --provider P --project DIR --paths <write set files>`) for the skills of the role from the write set of the piece: the answer (`skills[].name`, `path`, `reason`) is kept in the state of the piece, an isolated role gets the text of the `SKILL.md` at the path the bridge names, beacon `SKILLS_SELECTED`; no bridge stops the piece `SKILLS_BRIDGE_UNAVAILABLE`, a failing one `SKILLS_SELECT_FAILED`; `auto` is not listed with other names |
| `instructions` | `isolate_roles` (default every role; a listed role starts without the project instructions and customizations of its provider, as far as the isolation profile of the provider goes, see Isolation profiles: for Claude Code `--safe-mode --strict-mcp-config` plus no `CLAUDE.md`/project memory, which cuts the start-up context from ≈16 K to ≈6 K tokens and drops the plugins, MCP servers, user skills and hooks, guarantee full; for Codex its own `CODEX_HOME` and `HOME` under the run folder with `--ignore-user-config -c project_doc_max_bytes=0`, guarantee partial until a live probe confirms it; grok has no switch, guarantee partial); `isolation` (`off` \| `prefer` default \| `require`: what an isolated role needs of its profile; `require` stops with `ISOLATION_UNAVAILABLE` before any work when the guarantee is not full, `prefer` says `ISOLATION_PARTIAL` once per run, provider and reason, `off` adds nothing; a work-source layer may only tighten it); `module_rules` (default `["module-folders", "module-boundaries", "engineering-invariants"]`: the instruction sections, by the last part of their `## <scope>.<name>` heading, that a role still gets from the CLAUDE.md or AGENTS.md of the root and of every folder on the way to a write-set path, as a short Repository rules block). An isolated role gets the text of its `skills` in the prompt, because its provider loads none by name; `sandbox` (`off` \| `prefer` default \| `require`: the provider sandbox for shell commands, see Sandboxes) and `sandbox_domains` (default `[]`: the domains a sandboxed Claude Code role may reach); `file_tools_rule` (default `true`: a `## File tools` run-rules block in the executor prompt that says to read and change files with Read/Grep/Edit/Write and not with Bash `cat`/`sed`/heredocs, added only when the route offers Read and Edit; measured before the rule: P10.2 81 Bash calls and 1 Edit, a heredoc edit 55–120 s of model time) |
| `session` | `executor`: `shared` (default), `handoff` or `per-item`; `max_idle_s` (default 0 = never): a session unused for longer is not resumed, the next attempt starts fresh (`idle_expired`). `handoff`: each piece of the run starts a fresh Claude Code session and its correction rounds resume it; the prompt of every piece carries the `## Run batch` block that names all pieces and, for each piece already done, a bounded `### Handoff of` (commit, summary, open issues, changed paths from its `register-report.json`) — a later piece does not re-read the transcript of the earlier ones on every turn (measured: a shared session carried 229K→372K tokens of context into the second piece, 18.5M cache-read tokens for one step). Each piece keeps its own slot in `executor_sessions` of the run state (see *Session slots*). `shared`: the executor of every piece of the run, and of every correction round of a piece, resumes the Claude Code session of the previous executor (`claude -p --resume`), so the later pieces start with what the earlier ones learned, and the prompt of the first one carries a `run_rules` block `## Run batch` that names all pieces; the later ones are told that the session is resumed. Checks, review, register and commit stay per piece. `per-item`: a fresh session per executor step. `--batch` / `--no-batch` of `run` set it (`handoff` / `per-item`), and `--no-batch` also claims the pieces one at a time (layer `invocation:--batch`, above `--options`). Shared executors run without `--no-session-persistence` (the launch catalog sets it; a session that is not saved cannot be resumed), so their sessions stay in the provider's own store. A session that failed is forgotten and a fresh one starts. The session id, the task digest and the answers it has seen are kept in the slot of the piece (see *Session slots* and *Resumed sessions*). A provider resumes when its capability record says `resume` is `supported` or `adapted` (not by its name): Claude Code with `--resume`; a Codex executor its thread and a Grok executor its conversation through the `resume_argv` of the launch catalog entry (`codex -a never exec resume <thread> --json -c sandbox_mode="…" --model … -`, `grok … --resume <id>`). |
| `scope` | `outside`: `deviation` (default) or `block`, for paths changed outside `scope.write_set`; `fence`: `project` (default: the executor may change any file of the project, `scope.write_set` is the expected change and a path outside it is reported by the executor as a `deviation`, not a block; the filesystem guard still confines it to the project) or `plan` (the write set is a fence: a path outside it makes the executor stop with `blocked`); `extra_paths`: directories outside the project the executor may also change (absolute or `~/…`; named in its prompt and granted to every writing role: `--rw` on its `ro-run.py` guard, for Claude Code also `--add-dir` and, under the provider sandbox, `sandbox.filesystem.allowWrite`, for Codex `--add-dir`); `outside_module`: `deviation` (default) or `block`, for paths of another module than the write set names (`OUTSIDE_MODULE` under `block`); `runtime_paths`: patterns of runtime artifacts that are set aside, never committed (see "The write set is a fence by module"). `--fence` and `--allow-path DIR` (repeatable) set them for one run. `outside: block` with `fence: project` stops the piece at the first path outside the plan. |
| `checks` | `parallel` (1–8, default 2: command checks run together, sharing the jobs budget `SKM_TEST_JOBS`), `fail_fast` (default false: every item check runs, so one round collects every independent failure; true: after a red command check no other check starts, the ones running end and the rest are `skipped` with `skip_reason` `fail_fast`; `phase` checks run only when every item check is green, else `skipped` with `phase_after_red`; the item checks run cheapest first by their time in earlier rounds), `reuse` (default true: a command check with green evidence of this run for the same candidate, command, directory and fingerprint is not run again; its row is `reused`), `overlap_review` (default false: the checks of a round run while the review of that candidate reads it; red checks drop that review and it is repeated), `kinds` (default `["acceptance","impact"]`), `cadence` (default `["item","phase"]`; `["item"]` leaves out the `cadence: phase` checks, the full pass that the planner bridge gives to the item closing a phase), `red_first` (default true: in a correction round the previously red checks run first, and the others only when those are green; false runs the checks in plan order in every round, with no red-first staging; whether the later checks start after a red one is decided by `fail_fast` alone, independently of `red_first`), `executor_runs_checks` (default false: the executor runs only the tests of the code it changed), `self_check` (default empty: a list of the project's cheap commands, e.g. the tests of the touched units and their dependents and lint, that an executor with `executor_runs_checks: false` runs once on its final tree before it reports and lists in `self_check` of its stage-report; the claim proves nothing, the conductor still runs every acceptance check) |
| `review` | `correct_min_severity` (`Blocker`/`Major`/`Minor`/`Nit`, default `Major`), `pre_final` (default `true`), `audit_scope` (`corrected` default: the round after a correction reads only the corrected findings and the diff of the paths changed since the previous review, see *Review of round 2 and later*; `full`: the whole diff every round), `final_correction` (default `true`: when no further round is allowed the findings are corrected without another review, noted in the plan and as `review_debt` of the piece with a `REVIEW_DEBT` beacon, instead of `REVIEW_LIMIT`; `review_rounds` is a wall, `ceiling_factor` does not extend it), `dynamic` (default `true`: a piece whose pack has no review gets one when its risk score reaches the threshold, see Dynamic review), `dynamic_threshold` (0–100, default 60); `strategy` (`auto` default, `each`, `groups`, `single`, `none`: how a batch is reviewed, see *The review strategy of a batch*), `strategist` (`rules` default, `model`: who chooses it) and `correction_route` (`executor` default, or `bounded-implementer`: the role that runs the corrections of review findings without a Blocker, see *The route of a correction*) |
| `limits` | targets `review_rounds` (0–5), `corrections` (0–3), `check_fixes` (0–3) and their `ceiling_factor` (1–5, default 2); `retries` (0–5, per step); `repairs` (0–3, default 1); `provider_wait_max_s` (default 900: the longest wait for a provider limit to reset); hard token limits `tokens_hard_max` (of the piece) and `run_tokens_hard_max` (of the run), 0 off (see Hard token limits and resume), with `unmetered` (`stop` default, or `charge`) and `unmetered_charge_tokens` (50000) for an attempt that reports no usage while one is in force; beacons `tokens_max`, `stage_warn_s` (2700), `stage_idle_warn_s` (600), `check_warn_s` (900), `check_idle_warn_s` (600), and the stall beacons `stall_repeat_n` (5: one `STALL_SUSPECTED` after this many identical tool commands in a row) and `stall_window_s` (1800: a stream that grows this long without a tool step), 0 switching each off; wall-clock ceilings: `role_timeout_s` (a map role → seconds for every transport: `context-scout` 900, `triager` 1800, `report-fixer` 600, `registrar` 600, `reviewer` 1800, `advisor` 1800, `researcher` 2700; the `executor` and the `bounded-implementer` have none; a layer names only the walls it changes, 0 removes one; the group review uses the `reviewer` wall), `stage_timeout_s` (0, off; when set it replaces the wall of every role), `check_timeout_s` (7200, 0 off); silence ceilings: `stage_idle_timeout_s` (5400), `check_idle_timeout_s` (3600). Disk: `disk_min_gb` (5, 0 off: a run or the checks of a round do not start with less free space under the project and the temporary directory, `DISK_LOW`), `triage_repro_timeout_s` (600, 0 none: the ceiling in seconds on the read-only rerun of the reproduction of a rejected Blocker or Major finding; past it the finding is confirmed again, `TRIAGE_REPRO_UNVERIFIED`). Run-wide: `run_warn_s` (7200: a beacon when a run is longer) and `run_timeout_s` (0, off: a ceiling for the whole run); batch targets `review_rounds_batch`, `corrections_batch`, `findings_batch` (0, off: the totals of all pieces of a run); `question_warn_s` (1800: a beacon for a question waiting that long); `skill_tokens_max` (5000: the budget of the skills of one role); prompt blocks `prompt_core_tokens` (12000), `prompt_supporting_tokens` (30000) and `prompt_retrieval_tokens` (50000). |
| `on_error` | `{<failure class>: {action, max?}}`, the form of the run-policy `on_error` (`action`: `stop`, `retry`, `retry_after`, `fallback_route`, `replan`, `reconcile`); layers merge by class; the conductor default is `unknown` → `retry` (see Provider failures) |
| `fallback_routes` | `[{role, provider, model_class, effort?}]`: the routes a role may move to when its provider cannot serve it; default: the reviewer (grok) moves to `claude-code`, class `frontier`, effort `high`. A layer replaces the list, so a layer that names routes drops the default for roles it does not name; `[]` switches every route, the default included, off |
| `commit` | `mode`: `final-only` (default: one commit after the registration) or `implementation-and-fixes` (see Split commits) |
| `on_blocked` | `stop` or `report` |

### Current request input receipts

`stages[].require_current_input_receipt: true` is an explicit requirement in both `exec/v1` run-policy stages and
`conductor/v1` run-options. It is omitted by default. A work-source layer may add the requirement but cannot disable one
already set by a lower layer. Existing runs without it keep their current behavior.

The optional capability-record field `current_input_receipt` describes pre-dispatch acquisition separately from
`usage`, which describes completed accounting. A missing field means unknown. Native Grok records unknown; its
`usage: supported` and terminal streaming fixture do not prove a current input receipt. No current binding implements
a verified acquisition at the native tool-dispatch boundary. Even a manually declared `supported` record cannot create it.

Preparation and conductor preflight refuse a required receipt with `CURRENT_INPUT_RECEIPT_UNSUPPORTED` before any role
is spawned; dry-run reports the same unavailable requirement. The reason includes binding/provider and record
support/source/evidence. This is missing telemetry capability, not a sandbox permission or login diagnosis.

This boundary provides an **early unsupported result**, not a live receipt implementation or a capacity pass. A future
provider/transport integration must expose an immutable current API request receipt atomically before dependent tools:
actual input with explicit cache semantics (or a documented strict upper bound), request/session/model/build/effort/config
correlation, and mandatory delivery/trim/compaction evidence. The consumer owns its reserve policy. The native CLI
dispatches its own tools; parsing captured stdout after completion cannot provide this ordering guarantee.

Offline socket-barrier regressions call the actual preflight helper while terminal completion is blocked, with empty
live usage, then after terminal usage and a delayed summary. They prove continued refusal and zero role spawns for a
required capability. They do not prove positive receipt acquisition. Supporting a real provider additionally requires
causal positive admission and wrong/stale request, identity/config, partial publication, delivery/trim/compaction and
reserve-boundary negatives through that actual acquisition path. Completed replay is not a substitute.

`limits.question_warn_s` (default 1800; 0 off) marks a question that waits too long for an answer (see Questions of the executor).
`limits.skill_tokens_max` (default 5000; 0 off) is the largest text of one skill that an isolated role gets in its prompt (see Skill checks).
`limits.prompt_core_tokens` (12000), `limits.prompt_supporting_tokens` (30000) and `limits.prompt_retrieval_tokens` (50000) are the
measures of the classes of prompt blocks (see Prompt manifest); 0 switches the beacon off. They only measure: nothing is cut.

Layers merge from the general to the specific: defaults → `[orch.conductor]` → the run-policy pack (the routes of its
model stages, `review.triage`, `max_rounds`, `max_corrections`, `retries_budget`) → the layers of the work source (the
plan, the phase, the item) → `--options FILE`. A value of a more specific layer wins; `rules` append without repeats;
`limits` merge by key; `skills` replace the list of each named role; `stages` merge by role, and a layer that names a
model or a model class replaces both. Every source layer is validated (`OPTIONS_INVALID` names the layer); the numeric
bounds are `minimum`/`maximum` of the schema itself, so the schema is the one statement of them.
`<run>/<item>/options.json` records the merged options and, per key, the layer that set it.

**Isolation floor.** A layer of the work source is text a model may have written (an overlay document, an input file),
so it may tighten the isolation of a run but never loosen it: `instructions.sandbox` only moves along
`off < prefer < require`, `scope.fence` along `project < plan`, `scope.outside` and `scope.outside_module` along `deviation < block`;
`instructions.sandbox_domains` and `scope.extra_paths` may only repeat or shrink what the layers below allow;
`instructions.isolate_roles` and `scope.runtime_paths` may only grow. A layer that loosens one of them stops the run with `OPTIONS_UNTRUSTED` (the
key, the value and the layer below that set it). Only the configuration, the run-policy pack and the invocation
(`--options`, `--allow-path`, `--fence`) may loosen them; trust is a mark the conductor sets on its own invocation layers,
never the `source` label a layer carries. Limits, review and checks keys stay free for the plan (it raises
`check_timeout_s` or picks a scenario without review legitimately). Every `extra_paths` entry is resolved (`~`,
symlinks) and refused with `OPTIONS_UNSAFE_PATH` when it is the root, a system folder, HOME or an ancestor, the project
or an ancestor, a secrets folder under HOME (`.ssh`, `.gnupg`, `.aws`, …) or inside `.git`; the canonical path is the one
the filesystem guard gets and `options.json` records.

The work source hands the layers over in its claim answer (`options`). The planner bridge reads them from
`orchestration.options` of the plan, the phase and the item, and from orchestration overlay documents (see the
bridge README) for plan engines that do not know the field yet.

### Hard token limits and resume

`limits.tokens_hard_max` limits accounted fresh input and output tokens of one piece;
`limits.run_tokens_hard_max` limits their total across the whole run, including the strategist and group reviews.
Both are integers ≥ 0, default 0 (unlimited). `tokens_max` remains an informational `BUDGET_OVER` target;
when both it and `tokens_hard_max` are positive, `tokens_max` must not exceed the hard limit (`OPTIONS_INVALID`).

The run cap accepts only machine/project configuration, invocation `--config` and the run's `--options`.
A work-source layer (plan, phase, item or input) that names it, including 0, gets `OPTIONS_INVALID`:
`run_tokens_hard_max is a run limit; set it in the configuration or --options`.
`run.json.limits_run.run_tokens_hard_max` freezes `{value, source, file?}` at start, so later configuration or options
edits cannot replace the run cap. Cache reads do not count toward either limit.

Admission checks run before **every** model call: each model step, each attempt of a role (a repeat after a failure or
a rejected answer, a fallback route, a wait for a provider reset), each report-fixer repair, the strategist and the
group reviewer; and after saving each done step. At `used >= limit` the run stops with `TOKEN_BUDGET`, the piece is
stopped, and done steps stay saved; it is not registered as blocked. Once the boundary of accounted usage is reached, no
new model call starts. One call can still cross the limit: admission never interrupts a running one. The run policy's `budgets.stage_tokens_max` (> 0) is that check on the known fresh tokens of one logical step
(the piece and the step key): every attempt, repair and fallback of that step, kept across an interrupt and a resume,
and separate when two steps overlap (each with its own amount and step label). A new step key starts at zero. Replaying
a receipt replaces that attempt and does not count it twice. The shipped value 0 does not apply. A run saved before this
record resumes a step from the receipts or agent usage that name it, or from zero when they do not. It stops with
`TOKEN_BUDGET` naming the step. Deterministic steps (checks, register, commit) are not model calls and are not checked.

Missing usage (`usage_incomplete`) is not zero. While a hard limit is in force, `limits.unmetered` says what an attempt
without usage does: `stop` (default) stops the piece with `TOKEN_BUDGET_UNMETERED` at the next admission (after the
attempt that reported none); `charge` charges `limits.unmetered_charge_tokens` (default 50000) per attempt as fresh input
tokens of the piece, the run and the step, counted apart in `tokens.charged`, once per attempt even when its receipt is
read again. Under `stop` the unknown usage is kept at run scope (`state.usage_unmetered`: the pieces whose attempt reported
none and that no charge accounted for): with `run_tokens_hard_max` in force it stops every later admission of the run,
whatever piece the attempt belonged to; a piece limit alone consults the piece only. The `BUDGET_UNMETERED` beacon stays. With both hard limits 0 nothing is stopped or charged: the beacon is
all. `unmetered` is not a `--raise-limit` key; to continue a piece stopped with `TOKEN_BUDGET_UNMETERED`, set it to
`charge` in the `--options` file of the run (a resume reads the file again) or in `[orch.conductor.limits]`, then
`resume`. Attempts that already ran under `stop` are not charged afterwards.

```bash
orch conduct resume --run RUN --raise-limit tokens_hard_max=500000
orch conduct resume --run RUN --raise-limit tokens_hard_max=800000 --raise-limit run_tokens_hard_max=2000000
orch conduct resume --run RUN --raise-limit tokens_hard_max=0
```

`--raise-limit KEY=N` is repeatable and accepts only these two keys. N must exceed the effective value;
0 explicitly removes the limit. Raises overlay the options for this run; they do not rewrite the piece's
`options.json` or repeat its done executor. `state.limit_raises[]` records `{key, from, to, at, by: invocation}`, and a
raise of `tokens_hard_max` also names its `item` (the stopped piece) and holds for that piece only, while
`run_tokens_hard_max` is run-wide (an older record without `item` holds for every piece, as it did);
each raise emits `info` reason `LIMIT_RAISED`. Without a raise, a still-exhausted run immediately stops again
before a model call. No `--retry` is needed. `BUDGET_EXHAUSTED` remains a retry code, and a provider context-limit
failure remains `PROVIDER_CONTEXT`, a signal to replan.

## Visibility

Every event is one progress line (`conductor/v1` `progress-line`): `run.start|resume|end`, `item.start|end`,
`stage.start|end|skip`, `info`. stderr gets a readable line by default (time, item, step, role and route, what
happened, verdict, duration, tokens, stop code), the JSON line with `--json-lines`, nothing with `--quiet`. The journal
`progress.jsonl` always gets the JSON line. A line that breaks the `progress-line` contract is not written as it is: the
whole line goes to `progress.invalid.jsonl` beside the journal and the journal gets the `info` line `PROGRESS_LINE_INVALID`
(`<event>: <first problem>`); the run goes on. The readers (`status`, `timeline`, `follow`, the observer) keep only the
lines that fit the contract and the observer report counts the others in `discarded_lines`. Every role is told to print the same kind of line
(`[orch] <item> <step> <what>`, no time: a role cannot know it; the time of a line is the receive stamp in the `<step>.jsonl.times` file next to the stream) into its own stream. `orch conduct status` summarises the journal: run status,
the step running now, the last step and outcome of each piece, the tokens and the agent runs of the current piece
(`status --json` has them as `agents: [{agent_run_id, role, step, status, tokens}]`). A blocked piece shows the code of
its first escalation after its outcome and the escalation text on an `escalation:` line (the `item.end` line of the
journal carries them as `reason_code` and `message`; `escalation` in `status --json`).

### Agent runs

Every start of a model role (executor, reviewer, scout, triager, registrar, and the report-fixer that mends a result) is an agent
run with the id `agent-<run suffix>-<n>` (`n` from `state.agents`, kept across a resume) and the folder
`<run>/<item>/agents/<agent_run_id>/`: `request.json` (`role`, `route`, `step`, `attempt`, `prompt` and `causation`, `started_at`;
`parent_agent_run_id` for the report-fixer, which names the role it mended), `result.json` (`exit`, `error` — an `error/v1`
document when the failure was classified, else the code of the stop —, `decisions` of `retry.decide`, `duration_s`, `stream`,
`lingered`; written however the run ends) and `usage.json` (`input`, `cached`, `output` of all its attempts and
`usage_complete`, the report-fixer apart from the role it mended). The prompts and the streams stay in `prompts/` and `streams/`; the folder points at them. A
folder without `result.json` is a role still running or one that died with the process.

Every process an agent run starts (each attempt and fallback of a role, each repair of the report-fixer, a group reviewer
or the review strategist) has its authority recorded first: `authority/a<attempt>.json` (conductor/v1 `authority-envelope`,
see *Sandboxes*), computed for the route of that attempt, checked, written crash-safely right before the process starts and
never rewritten (another digest for the same attempt is `AUTHORITY_RECORD_CONFLICT`). A crash between the record and the
process leaves the record of a launch that did not happen, never a launch without one; a resume starts a new agent run and
leaves the old files as they are. `result.json` lists the launches as `authority` (`[{attempt, provider, digest}]`, absent
when no process started), the events `orch.agent.finished` and `orch.agent.failed` carry `authority_digests` (in the order of
the attempts); `orch.agent.started` and `request.json` carry none (the route of an attempt is chosen after the agent run
starts). The digest of the last launch of each role is `state.items[ref].authority[role]`. The `stage.end` lines and the
`STAGE_SLOW`/`STAGE_IDLE` beacons carry the optional field `agent`; the observer report lists the tokens by agent run.

Usage is normalized by the provider's payload shape. With an integer `cached_input_tokens` (Codex),
`input = max(0, input_tokens - cached_input_tokens)` and `cached = cached_input_tokens`: Codex's input already includes
cache reads. Otherwise (Claude/Grok), `input = input_tokens + cache_creation_input_tokens` and
`cached = cache_read_input_tokens`. `output = output_tokens` in both forms; booleans, negative values and non-integers
are ignored. Fresh tokens are `input + output`; cache reads stay separate. Item and run totals use receipts keyed by
agent id and attempt stream (`state.items[ref].usage_by_agent`), so reading the same receipt again does not add tokens.

Native Codex `turn.completed` is a cumulative session counter. The parser keeps its last snapshot; each receipt's
`accounting.counter_id` and `cumulative` values form the durable watermark. Only the increase is charged, atomically
with the receipt and totals, across retries, restarts and shared-session items. Replays add nothing. A decreasing
counter or resumed legacy session without a watermark is unavailable; existing budgets are never refunded or reset.
The observer sums unique physical actor contributions rather than cumulative stage-end events. Legacy resumed Codex
aggregates without a counter basis are shown as unavailable; historical state is not rewritten.

Native AGY does not declare whether `input_tokens` includes `cache_read_tokens`. Nonzero or missing cache therefore
makes input unavailable, with original counters retained in `accounting.reported` and the raw stream. Known output
and cache counts remain separate. Explicit zero cache makes input inclusion irrelevant and can be measured. Unknown
input is never silently presented as measured zero: `usage_complete=false`, the existing unmetered-budget rule applies,
and the observer's `usage_unavailable` warning links the receipts. Token tables then contain known portions only.

Each attempt records `usage_complete`: `true` when its JSONL stream supplied terminal `result`/`turn.completed` usage
with nonzero fresh input or output, `false` when a running JSONL attempt has no terminal usage or reports 0/0, and
`null` for text transport (scout) or a process that never started. Partial assistant-message usage is still counted
after a timeout, cancellation or an exit without a result, but it does not make the attempt complete. An agent's
`usage.json` is `false` if any of its attempts was incomplete, otherwise `true` if measured and `null` if none was
metered. The first incomplete attempt sets `state.items[ref].usage_incomplete = true` and emits one `info` event with
reason code `BUDGET_UNMETERED`: `<ref>: a model attempt reported no usage; token limits cannot see it`.
This flag survives later measured attempts and resume. Text transport alone does not mark the item incomplete.

### Stubs: additional instructions of the roles

A person keeps additional instructions for a role in Markdown files, by machine and by project, without touching the
canonical role text (`roles/*.md`, digest-checked) or anything a role may do. `orch stubs publish [--scope project|machine]`
creates the empty files (never overwriting one): `<project>/.swissknifeman/stubs/` (the project layer; `projects/<code>/local/stubs/` of the workspace when the project marker names one; in the
swissknifeman checkout itself this is the place to publish them) or `~/.config/swissknifeman/stubs/` (the machine layer).
A target `orch.role.<role>` (context-scout, executor, reviewer, triager, researcher, advisor; not the registrar and the
report-fixer, whose one-command steps extra text would only blur) is fed by four slots, joined from the general to the
specific: `_all.md`, `orch/_all.md`, `orch/roles/_all.md`, `orch/roles/<role>.md`. In each slot the project file decides by
the mode of its header `<!-- skm-stub:v1 target=… mode=replace|append|disable -->`: an empty file (or comments only)
inherits the machine one, so the published empty files mask nothing; `replace` (default) takes the project text instead,
`append` after the machine text, `disable` drops the slot. Text is literal: no includes, no variables.

A run resolves every target once, when it starts: the text and the provenance of each part (layer, slot, path, sha256)
go to `<run>/instructions.json`, the digest to `run.json` (`instructions_digest`). Every prompt of the run and of its
resumes reads that snapshot; a resume whose files changed says `STUBS_CHANGED`. The block `stub` (budget class
`supporting`) stands after the role text and before the task, under a heading that says it cannot change tools, write
authority, scope, checks or the result contract; the real limits stay the launch catalog, the sandbox, the filesystem guard
and the result parser. A stub that cannot be used (symlink, not a regular file, writable by every user, over 32 KiB, over 64 KiB for one
target counted as its common parts with the largest provider and provider--family variant one route can take, text that looks like a secret, not UTF-8, unknown header field, mode or version, a header that names another target, text in a `disable` file) stops the
run with `STUBS_INVALID` before any role starts. `[orch.stubs]` (machine, invocation or flags only): `enabled` (true) and
`layers` (`["machine", "project"]`; leave `project` out on a machine that runs repositories it does not trust).
`orch stubs list` shows the effective stubs of every role and the files of its variants; `orch stubs show ROLE`
shows the common block and where each part comes from.

Provider and model-family variants are extra parts of the same target, supplied by the owner:
`orch/roles/<role>@<provider>.md` and `orch/roles/<role>@<provider>--<family>.md` in either allowed layer.
Provider and family names match `[a-z0-9][a-z0-9.-]*`; a family cannot contain `--`. For example:

```markdown
<!-- skm-stub:v1 target=orch.role.executor@codex--gpt-6-sol mode=append -->
Explain the targeted test results in the stage report.
```

The effective text joins the four common slots once, then the provider parts, then the provider--family parts.
Each variant slot has its own `replace`, `append` and `disable` resolution across machine and project layers.
`orch stubs show executor --provider codex --model gpt-6-sol` prints this effective block and the selected origins;
`--provider codex` alone includes only the common and provider parts. `publish` creates only the four common slots;
create variant files explicitly. Disabling stubs, excluding a layer and the file safety rules apply to variants too.

The actual route selects the variants. A model's family is its exact inventory id, else the first inventory entry
whose pattern fully matches the model, else the model name itself. When the snapshot has variant parts, the first resolution of each `provider/model`
is saved in `instructions.json.variant_resolution` and reused on resume even if the model catalog changes.
Variant parts keep their `variant` and literal `body` in the frozen snapshot; the target's `text` contains only
the common text. Resolved families sit outside the snapshot digest; without variant files the snapshot and its digest
retain their previous format. On provider fallback, including a gate discovered just before launch, the conductor
rebuilds the same `stub` block for the new route and rewrites the attempt's prompt and manifest before calling it.
The heading, block position and authority remain the same.

### Prompt manifest

`conduct prompt explain --step STEP` accepts only `^[a-z][a-z0-9-]*(\.[0-9]+(-q[0-9]+)?)?$`.
The resolved manifest must stay inside the item's directory (and the item inside the run); traversal and symlink
escapes return exit 1 with `PROMPT_PATH_INVALID`. This read-only command never starts a provider.

A prompt is built from blocks `Block(kind, origin, text)` (`conductor/prompts/`, `blocks.py`); `render(blocks)` joins their texts into
the prompt byte for byte (a separator belongs to the block it follows). Every model role step writes
`<item>/prompts/<step>.manifest.json` (`prompt-manifest/v1`) beside `<step>.md`: `step`, `role`, `route` (`provider`,
`model`, `effort`), `blocks` (`kind`, `origin`, `sha256`, `tokens` estimated by `aicore.content.budget`, `id` for a skill),
`excluded` (`id`, `reason`: the skills the checks of P9.2 left out, see Skill checks), `estimated_tokens` and `prompt_sha256` of the whole prompt.
The `tokens` of the blocks add up to `estimated_tokens` within one token per block. Kinds: `role_text`, `input`,
`repository_rules`, `skill`, `skill_names`, `context_map`, `expected_paths`, `verification`, `run_rules`, `answers`,
`correction`, `progress`, `result_contract`, `research` (the result of the research stage, see [Research](research.md)), the blocks of a delta prompt (`resumed`, `interrupted`, `changed`, see *Resumed sessions*), and for the roles that review, triage and close: `candidate`, `review_scope`,
`diff`, `findings`, `instruction`. `origin` is the role file, `input.json`, `questions.json`, `skill:<id>`,
`scout-cache:<rel>` or `conductor`.

The optional `budgets` of the manifest measures the prompt by class of blocks: `{core, task, supporting, retrieval}`, each
`{tokens, limit}` (the sum of the estimated tokens of its blocks against `limits.prompt_core_tokens`, `prompt_supporting_tokens` or
`prompt_retrieval_tokens`; 0 is no limit). **core**, the frame the conductor writes: `role_text`, `verification`, `result_contract`,
`answers`, `correction`, `progress`, `instruction`; **task**, the material of the piece, measured with no limit (its size is the
plan's and the change's, and nothing of it could be cut): `input`, `candidate`, `review_scope`, `diff`, `findings`;
**supporting**: `repository_rules`, `skill`, `skill_names`, `context_map`, `expected_paths`, `focus`, `run_rules`; **retrieval**:
`research`. A class past its limit is a beacon `BUDGET_OVER` with `message`
`block <kind> <origin> <tokens>` for its heaviest block. This is a measure and a beacon only: the prompt is never cut, and the limits are for tuning from the data
(observer: Prompt budgets).

### Resumed sessions

A correction round of an executor whose session goes on does not send the whole prompt (the role text, the execution-input,
the rules, the skills, the scout map: 56–115 KB) to a session that holds it already. `prompts.executor_resumed` builds the
**delta prompt** from the blocks `resumed` (`## Continuation`: the task, the rules and the result contract of the latest full prompt
still apply; earlier correction instructions in the session are historical, and the correction section of this message is the
only current focus), `answers` (only the answers the session has not seen: `answers` of its slot), `correction` (the red checks,
the confirmed findings, the deviation to fix), `interrupted` (the note of an interrupted round), `changed` (the paths the
earlier round changed), `progress` and `result_contract`. A round that asks nothing the session lacks (the first round of a
piece, a repeat of it) has no delta prompt and is sent in full.

The delta prompt goes only if all three conditions hold for the attempt: (1) its command line continues the session
(`--resume`, or the `resume_argv` of the route); (2) the session received the full prompt of this very piece
(`last_item` of the slot is the piece: in `shared` mode the first round of the next piece is sent in full into the
continued session); (3) the `task_digest` of the full prompt now equals `task_digest` of the slot, the digest of
the last full prompt the session received. `task_digest` is the sha256 of the canonical JSON `[kind, origin, text]` of the
blocks that carry the task and the instructions — every block but `correction`, `answers`, `interrupted`, `changed`,
`progress` (it names the round) and the `## Run batch` note (it describes the batch, not the task) — so a rebuilt input
(`INPUT_REBUILT`: write set, acceptance, rules), other skills, stubs, repository rules or scout map send the whole prompt.
Any other doubt does the same: the delta prompt is an optimisation, never the only copy of the task.

An attempt that continued a session and ended with an error or without a session (a lost transcript, a provider that
refused the id) forgets the session (its id, task digest and answers go with it; the next decision is `provider_error` or `no_session_id`) and emits the info `SESSION_RESUME_FAILED` (`item`,
`stage`, the route with its provider). The next attempt of the step starts a fresh session with the **whole** prompt and no
`--resume`. `prompts/<step>.md` always holds the full prompt of the step, `prompts/<step>.resumed.md` the delta one when it
was sent; the manifest of the step lists the blocks that were sent, with `resumed_session: true` for a delta prompt and the
`task_digest` of the full one (both optional fields of `prompt-manifest/v1`).

A Codex or Grok executor resumes with `resume_argv` of its entry in the launch catalog (`launch-catalog.json` 1.6.0):
`codex -a never exec resume {session} --json -c sandbox_mode="{write_sandbox}" --model … -c model_reasoning_effort=… -`.
`codex exec resume` has no `--sandbox`, so the mode of the first round (`danger-full-access` for `[orch.launch] access =
open`, `workspace-write` for `confined`) is passed as a `-c` override; the model and the effort are those of the first
round and `-a never` stays before `exec`. The thread id comes from `thread.started`. A route started from
`[orch.conductor.argv]` (a command line of the user) has no `resume_argv` and starts fresh.

### Session slots

The run keeps one executor session per piece in `executor_sessions` of `state.json` (`records/v1` `state`): the key is the
piece, or `*` for `session.executor = shared`. A slot holds the provider `session`, its `provider` and `route`, the
`fingerprint` it was built under with its `fingerprint_digest`, `created_at`, `last_used_at`, `rounds`, `last_item`
(the piece that used it last), and the `task_digest` and `answers` of *Resumed sessions*. A retry of an earlier piece
(`resume --retry W1` after W2 ran) therefore resumes the session of W1, not that of W2.

The **fingerprint** is the identity a session is built under: `provider`, `project` (real path), `worktree` (real path of
the git top level), `role`, `item`, `attempt_id` (of the claim), `instructions_digest` (canonical digest of
`<run>/instructions.json`, without what the run fills in itself), `authority_digest`, `isolation_home` and `base` (the
revision of the first brief of the piece, `session_base` of the piece state). `shared` leaves out `item`, `attempt_id` and `base`.
`authority_digest` is the digest of the authority envelope a launch of the executor on the route would record (computed
quietly by `sessions.identity_inputs`: nothing is said or created; see *Sandboxes*), `isolation_home` the home of an
isolated provider (`CODEX_HOME` of the run). A slot kept before the envelope existed has an empty `authority_digest`: its
next round starts fresh once (`fingerprint_changed:authority_digest`). The model and the effort are not part of it: a
change resumes and says `SESSION_ROUTE_CHANGED`.

Every executor attempt decides, once, whether to resume (`session_decision`), and says it in the journal. The info
`SESSION_RESUMED` (`item`, `stage`, the session and `reuse=` one of `correction`, `retry`, `question`, `next_piece`,
`followup`) or `SESSION_FRESH` (`item`, `stage`, `reason=`) is the same for the event `orch.agent.started`, whose
`data.session` is `{resumed, reason}`. The reason of a fresh session is one of:

| `reason` | the attempt starts fresh because |
| --- | --- |
| `per_item_mode` | `session.executor` is `per-item` (`--no-batch`) |
| `provider_unsupported` | the capability record of the provider has `resume` `unknown` or `unsupported`, or the route has no command that continues a session (a provider that resumes through `resume_argv` but runs a command line of the user from `[orch.conductor.argv]`) |
| `first_round` | the piece has no session yet |
| `provider_error` | the previous attempt on the session ended with an error |
| `no_session_id` | the previous attempt returned no session id |
| `fingerprint_changed:<field>` | `provider`, `project`, `worktree`, `attempt_id`, `instructions_digest`, `authority_digest`, `isolation_home` or `base` differs from the slot (the first one in this order). A change of the authority or of the instructions is never a resume: a session with broader rights must not continue silently (invariant I7) |
| `idle_expired` | `session.max_idle_s` is above 0 and the slot was used longer ago (the provider's prompt cache is gone: a resume would re-bill the whole history) |
| `followup_mismatch` | a group review follow-up whose `session_ref` does not match (below) |

A fresh session gets the whole prompt; in `handoff` mode (not the default) the `## Run batch` note names the pieces already done and carries their
handoff. The delta prompt goes exactly when the decision is a resume (with the conditions of *Resumed sessions*).
Resume uses the explicit session id of the slot; `--continue` and `--last` are never used.

**Older runs.** A state written before the slots has `executor_session`, `executor_session_route`,
`executor_session_item`, `executor_session_task_digest` and `executor_session_answers` (still valid, deprecated). `resume`
moves them into a slot without a fingerprint, removes them and says the info `SESSION_STATE_MIGRATED` once; the session
resumes as before and the next round gives its slot an identity; that round also drops the copy of the session filed
under the other key, so a run that changes `session.executor` or whose identity changed never resumes it unchecked.

**Group review follow-up.** The execution-input of a follow-up (`provenance.kind = review_followup`) carries
`session_ref` `{run, item, items, session?, provider?, fingerprint_digest?}`: where the group comes from (the run, its last
piece and every piece) and, when the last piece kept a resumable session, that session with the digest of its fingerprint
without `item`, `attempt_id` and `base` (a follow-up is another attempt and starts after the commits it corrects).
`review_plan.followup_input` writes it for the group review of a run, and `scripts/batch-review.py` writes
`batch-review.followup.json` beside `batch-review.md` for a Blocker or Major finding. The first executor round of the
follow-up resumes the session when the provider and the digest of its own fingerprint match (`SESSION_RESUMED
reuse=followup`). Every other start of the follow-up is fresh (`followup_mismatch`, a group that kept no session,
`per_item_mode`, `provider_unsupported`, …) and its prompt carries the handoff of every piece of the group, read as a
`state` record from the run `session_ref.run` and its registered reports (a damaged state is `STATE_INVALID` /
`STATE_CORRUPT`, not a silent gap).

**Observer.** `observer.json` has `sessions` `{resumed: {reuse: n}, fresh: {reason: n}}` from these info lines, and
`observer.md` a line `Executor sessions`.

### Review of round 2 and later

With `review.audit_scope: corrected` (default) the diff block of the reviewer in round N>1 is the diff against the base of
the paths changed since review N-1 only, headed "Diff against the base of the paths changed since review N-1 (the full
diff was reviewed in round 1; read other files as needed)", plus the files named by the `location` of the findings still to
be fixed: a later report that does not name an earlier confirmed finding is no proof that it was fixed, so every confirmed
finding of every earlier round (at any severity) stays in the scope list of the round (`F1 (review 1)`) and its file in the
diff. Each review stores the tree it started from in `state.items[ref].review_marks[N]` (`{path: sha256}` of the dirty tree
without the conductor reports, the artifact folder and the plan folder). Round 1, `audit_scope: full` and a run without
marks (made before they existed) get the whole diff, as before.

### Review receipts

Every completed per-item review writes `<artifacts>/review-receipt.json` (`review-receipt/v1`), validated before writing.
It binds the subject and optional attempt to the review base, candidate path fingerprints and digest, reviewer route,
policy, verdict, findings, open Blocker/Major counts, questions and residual risk. The snapshot is taken before the
reviewer starts. A later triage updates dispositions without replacing the reviewed candidate. `review-verdict.json`
keeps its published fields and round history, adding `base`, `candidate_digest` and each finding's `key`.

The conductor assigns `fk-` keys from the path (without line), lowercased basis and normalized failure scenario
(lowercase, digits removed, whitespace collapsed, first 160 characters). Rephrasing the same error can produce a new
key: this identifies exact repeats and references; it does not perform semantic deduplication. The closed
`review-findings/v1` payload stays unchanged; step results carry `finding_keys` beside it.

Fingerprints are `<mode> <git blob>` (`100644`, `100755`, `120000`), `absent`, or `other` for unsupported types.
Regular files use `git hash-object --no-filters`; symlinks hash their target bytes. Candidate digest is `sha256:` of
sorted `path\tfingerprint` lines joined with newline. `outside` records product paths already different from the
base beyond candidate paths, excluding the plan/artifact folders and `.swissknifeman/`.

A correction without another review (`final_correction` or combined red-check correction at the review limit)
retains the reviewed candidate, records `corrected_after.round/paths` and marks corrected findings. An unchanged
product does not become a correction. Registration forwards the receipt with `source register --review-receipt PATH`.
Blocked registration omits the automatic receipt, so a stale or previous-attempt review cannot prevent recording
the escalation. If a completed overlap review supplies no combined correction and a check-fix changes its candidate,
the conductor preserves that review's history and reviews the new candidate in the next available round. A spent
review limit records the piece blocked with `REVIEW_LIMIT` instead of forwarding a stale completion receipt.
The source decides whether it gates completion; planner's optional gate compares contents and permits only `fresh`
or `findings_only` (changes confined to current confirmed finding locations or `corrected_after.paths`). Historical
`corrected` findings grant no permission for edits after a later review.

### Review focus

The reviewer prompt gets a block `focus` (`origin` `stage-report`, `risk.json` or `stage-report+risk.json`; budget class
supporting) after `candidate` when there is something to say: the `review_recommendation.focus` lines of the executor
rounds (in order, without repeats) and the features of `risk.json` (`risk <feature> (+<weight>): <evidence>`; the score
exists only for a piece whose policy has no review, see Dynamic review). It lists what to look at first and says the
review is not narrowed; without a source there is no block, and the prompt is the one it was. The manifest of `review.N`
lists the block. `suggested_model_class` of the executor raises the class of the reviewer route (the highest class
suggested by any round) when it is above the class of the route and `_admit` takes the higher route of the same provider
(command, transport, sandbox, gate): the beacon `ROUTE_UPGRADED`, `routes.json` and `state.route_overrides.reviewer` (a
resume starts from it) change. A suggestion at or below the route changes nothing: the class is never lowered; a refused
upgrade is an `info` line once and the review goes on with its route.

### Skill checks

Skill names in run options match `^[a-z0-9][a-z0-9_:-]*(?:[./][a-z0-9][a-z0-9_:-]*)*$`:
`bucket:name` and `core/context-economy` are valid; traversal segments and absolute paths are refused as
`OPTIONS_INVALID`. Named files belong to the project's `.claude/skills` or `.agents/skills` root. Every resolved
component must stay inside that root, including the root itself; a symlink cannot grant a directory outside it.
An absent named file is still left to the provider as before. Auto files may be outside the project: the bridge's
path must be absolute, canonical, have no symlink components, and name `SKILL.md`. Orch does not locate the partner's
skill library. It compares SHA-256 of the exact file bytes with `skill_md_sha256` of the selected row; the separate
directory `digest` is not a file checksum. Old rows without `skill_md_sha256` are excluded (`digest_missing`).

Reads are strict UTF-8 and capped before opening: `SKILL.md` at 64 KiB, `selection.json` at 16 KiB, and rule carriers
(`CLAUDE.md`/`AGENTS.md`) at 256 KiB. A bounded descriptor read also catches a file growing after stat and refuses
symlink replacement. A present sidecar must validate against aicore `skill-selection/v1`; an absent sidecar retains
the default policy. A named sidecar belongs to the same skill root; an auto sidecar belongs to the selected skill's
directory. A rule carrier belongs to the project. Invalid carriers emit `RULES_PATH_INVALID` and contribute no rules.
Invalid skills emit `SKILL_PATH_INVALID`, with a manifest exclusion reason `outside` (also missing/unreadable or
nonregular auto files), `symlink`, `too_large`, `not_utf8`, `digest_missing`, `digest_mismatch` or `selection_invalid`.
These file checks run again on later reads, even when `skills_checked` already holds a verdict.

Before the prompt of a role is built, the skills of the role (`skills` of the run options, or what `["auto"]` chose) are
checked deterministically, from what each skill declares in the `selection.json` beside its `SKILL.md` and from the tools of
the route (`--tools` of its argv; a route that names no list is not judged by tools, `--tools ""` is a role with no tools).
Nothing in the text of a skill is read for meaning, and no text is cut (the old cut at 12000 characters is gone). A skill is
left out of the prompt, in this order of checks, as:

| Reason | When |
|---|---|
| `duplicated_by_role_contract` | `replaced_by` points at a role contract (a path under `roles/`) or a schema (under `schemas/` or `*.schema.json`); a script or a hook does not replace the text |
| `interactive_in_headless` | `requires_tools` has `AskUserQuestion`: every conductor role runs headless |
| `tool_missing` | a tool of `requires_tools` is not among the `--tools` of the route |
| `over_budget` | the text is above `max_tokens` of the sidecar or above `limits.skill_tokens_max` (only for an isolated role, which gets the text in its prompt; the size is estimated by `aicore.content.budget`) |
| `persona_duplicate` | a second skill of `kind: persona` |
| `exclusive_group` | more skills of one `exclusive_group` than the group allows (one; `php-architecture` two) |

Each policy exclusion is listed in `manifest.excluded` of the step (`id`, `reason`) and is a beacon `SKILL_EXCLUDED` with the detail
(for example the missing tool or the size). A skill left out is not named in the prompt either. If two kept skills are a pair
of `conflicts` (by id, by name, or by the folder of a `<bucket>/<folder>` entry), the role does not start: the piece stops
`PROMPT_CONFLICT` with the pair. The verdict is made once per piece and kept in the state (`skills_checked`). Contradictions
between the texts of skills ("must" against "never") are not detected: that cannot be done deterministically.

`limits.skill_tokens_max` defaults to 5000 (0 disables the token ceiling only in trusted configuration or invocation
options). A work-source layer may keep or lower an enabled ceiling, or enable one when the trusted value is 0;
disabling or raising it is `OPTIONS_UNTRUSTED`. Byte caps apply independently of the token ceiling.

`orch conduct prompt explain --item REF --step STEP [--run RUN] [--json]` prints the blocks of one step as a table (kind,
origin, tokens, the start of the digest) and what was left out; the default run is the latest. `MANIFEST_UNKNOWN` (exit 1)
means the step wrote none, `RUN_UNKNOWN` that there is no such run. The observer lists the five heaviest blocks by role.

### Split commits: `commit.mode`

`commit.mode` of the run options (`final-only` by default) chooses how the commits of a piece come about, when the run policy
commits (`git_action: commit`):

| Mode | Commits of a piece |
| --- | --- |
| `final-only` | one commit after the registration, as before: same message, same receipts (`receipts/commit.json`, `commit-request.json`) |
| `implementation-and-fixes` | the **checkpoint** (stage `implementation`, role `executor`) once the checks of the first round are green and before the first review; one **fix** commit (stage `correction.<n>`, role `fix`) per green correction of review round `n`; the **final** commit (stage `final`, role `executor`) of what is left: the records of the piece, the plan files and any path no stage took |

A stage commit takes the product paths of the piece that the tree still shows as changed (what the executor rounds and the
checks changed, without the runtime artifacts set aside, without the artifact folder and without anyone else's dirty
paths): the work source commits exactly those paths (the planner bridge asks its commit for `--paths-only`; a path
the task files of the item do not cover waits for the final commit). A stage that changed no product path commits nothing.
Each commit carries the trailers `Plan-Run` (the work-source run), `Plan-Attempt` and `Plan-Stage`; a fix commit also
`Plan-Review: <conductor run>/<item>/review.<n>` and `Plan-Findings: <finding keys>`. The checkpoint is not acceptance:
the review receipt and `finish` decide whether the piece is done. A split run never overlaps the review with the checks (`checks.overlap_review` is ignored): the first review starts after the checkpoint.

`state.items.<ref>.commits` lists `{stage, sha, parent}` of the stage commits. **The review of the piece starts from the
`parent` of its first commit**, not from HEAD (which would show an empty diff once the implementation is committed); the
audit of a later round also reads the paths of the fix commits. The group review and the handoff to a later piece read all
the commits of a piece: the diff is the range from the parent of the first to the last commit.

Receipts are kept per stage: `receipts/commit-<stage>.json` and `commit-<stage>-request.json` (`commit-implementation`,
`commit-correction.2`); the final commit keeps the names `commit.json` and `commit-request.json`. The steps are `checkpoint`
and `fix-commit.<n>`. If the conductor dies between the commit of a stage and its receipt, a resume finds the commit by its
`Plan-Run`/`Plan-Attempt`/`Plan-Stage` trailers in the newest commit and closes the step with it instead of committing again. This also holds for a stage whose source call died without an answer (the step is `stopped`, `COMMIT_REFUSED`), and a resume copies every closed stage step into `state.commits` before the loop starts. The final commit of a workspace plan is never closed by the trailer alone (its workspace part is repeated).

## Files: what is committed

| Path | Git | Content |
| --- | --- | --- |
| `.swissknifeman/state/orch/conductor/<run>/` (`projects/<code>/local/state/orch/conductor/<run>/` of the workspace when the project marker names one) | ignored | `run.json`, `state.json`, `progress.jsonl`; per piece `input.json`, `options.json`, `routes.json`, `prompts/` (`<step>.md`, `<step>.resumed.md` (the delta prompt, when it was sent) and `<step>.manifest.json`), `streams/` (raw role streams with token logs), `agents/<agent_run_id>/`, `reports/`, `checks/<n>/V#.log`, `register-report.json`; after a `resume --retry` `attempts/<n>/` holds the streams, reports, prompts and checks of the steps that retry repeated, and `state.json` the record `items.<ref>.attempts[]` (`n`, `retried_at`, per step `verdict`, `role`, `route`, `ended`, `report_status`, `files`); the observer report lists them under "Retried pieces" |
| `.swissknifeman/state/orch/conductor/cache/scout/` | ignored | context maps keyed by the content of the brief (without `provenance` and `digest`, which move with every write to the plan journal), the route, the role text, the names and texts of the selected skills and the stub; written whole (`durable_replace`), a hit only for a non-empty UTF-8 file |
| `.swissknifeman/state/orch/runs/<run>/` | ignored | the orch run journal of `source …` |
| artifact folder of the piece (`artifacts_dir` of the brief; the planner: `plans/<plan>/artifacts/<item>/`) | committed | `stage-report.json` (closed), `review-receipt.json` (last review, subject/attempt, content fingerprints and finding keys), `review-verdict.json` (selector, rounds, sessions, findings with the triage's reproductions, the stream path in state), `evidence/V#.json` (check-evidence) |
| `.swissknifeman/orch/reports/<run>/` | ignored | `observer.json`, `observer.md` (written when the run ends, after its last commit) |
| `.swissknifeman/orch-artifacts/<run>/<item>/` | ignored | local records: the artifact folder of a source without `artifacts_dir` (a workspace plan, the file source); never in a commit of the piece. The planner bridge copies the evidence of a workspace plan item into `<plan>/artifacts/<item>/<run>/evidence/` at register and the item refers to it there; files tracked before the folder was ignored stay in the index |
| the plan (JSON) | committed | through the work source's own commit (the final commit; with `commit.mode: implementation-and-fixes` the stage commits before it hold product files only) |

### Run records

The documents the conductor keeps in a run folder are closed by `schemas/records/v1` (`urn:swissknifeman:orch:records:<kind>:v1`,
`orch.conductor.records`): each is checked before it is written (`durable_replace`, `0600`) and after it is read, and
`orch.py validate <kind> FILE` checks one by hand. A new document carries `"$schema": "<its $id>"`; a document written
before records/v1 has no tag and is read as v0: the tag is added in memory and the document is checked (its file is not
rewritten, the next write under the lease writes v1), so runs started earlier resume. A tag of another kind or value is
`unknown or conflicting record tag`. `state` validation costs about 1 ms on the largest characterization state, so every
`RunStore.save` checks it. A step marked `done` is replayed by a resume, so it must carry the result its reader takes
(checks: one row `{id, green, …}` per check; executor: `report`; review: `findings`, a conductor/v1 `review-findings`
document; triage: `triage`, a conductor/v1 `triage-result` document; brief:
`input_path`; register: `outcome` and `gate`; commit: `outcome`; any other key: some `result`); a started or stopped
step carries none. `skills_auto` and `skills_checked` hold the choice of each role, kept once per piece.

| Kind | File | Written by | Error |
| --- | --- | --- | --- |
| `run` | `<run>/run.json` | `RunStore.create`, `RunStore.save_run` (the lane of a `--ready` batch) | `RUN_INVALID` |
| `state` | `<run>/state.json` | `RunStore.save`, `RunStore.next_agent`, under the lock of the run store | `STATE_INVALID` |
| `questions` | `<run>/<item>/questions.json` | the conductor and `orch conduct answer`, under `questions.lock` (taken before the run-store lock) | `QUESTIONS_INVALID` |
| `item-options` | `<run>/<item>/options.json` | the options of the piece: `scenario`, `options` (a run-options document of `conductor/v1`: `skills` as `[{role, names}]`, a layer that gives the same options again), `sources`, `digest`, `claim_route` | `RECORD_INVALID` |
| `item-routes` | `<run>/<item>/routes.json` | the route of each role, rewritten by a fallback, a retry or a reviewer upgrade | `RECORD_INVALID` |
| `lease` | `<run>/lease.json`, `<runs root>/checkouts/<sha16>.json` | the owner of the run lease or the checkout lock (`pid`, `host`, `started_at`, `command`, `start_ticks`, `boot_id`, `launcher`, `run`) | owner `unknown` |
| `heartbeat` | `<run>/heartbeat.json` | `Heartbeat.beat` of the conductor that owns the run (see Heartbeat and health); a write that fails is `HEARTBEAT_NOT_WRITTEN` | status: `unknown` / `HEARTBEAT_INVALID` |
| `supervisor-action` | `<run>/supervisor.jsonl` | one line per action of the supervisor (see *Supervisor*), appended and flushed | the pass fails (`RECORD_INVALID`) |
| `supervisor-snapshot` | `<run>/supervisor/snapshot-<UTC>.json` | `supervisor.snapshot`, before a signal to a hung conductor | `RECORD_INVALID` |
| `supervisor-state` | `<runs root>/supervisor-state.json` | the breaker of the supervisor, under `supervisor.lock` | `STATE_CORRUPT`, `RECORD_INVALID` (the pass stops) |
| `risk` | `<run>/<item>/risk.json` | `dynamic_review`: the risk score, its features and facts, the threshold and whether it added a review | `RECORD_INVALID` |
| `review-strategy` | `<run>/review-strategy.json` | `review_plan.decide`: mode, groups, reviewer effort, reason, source; a resume whose state lost the plan takes this file | `RECORD_INVALID` |
| `process` | `<run>/<item>/agents/<id>/process.json` | `process.run_role`: `pid`, `pgid`, `start_ticks`, `started_at`; read by cold recovery before any signal | `RECORD_INVALID` (the resume stops) |
| `agent-request` | `<run>/<item>/agents/<id>/request.json` | `agents.start` (see *Agent runs*) | `RECORD_INVALID` |
| `agent-result` | `<run>/<item>/agents/<id>/result.json` | one of two variants: `agents.finish` (`exit`, `decisions`, `duration_s`, `stream`, `lingered`, `error` when it failed, `isolation`, `authority` of its launches) or `agents.orphan` (only `error` `ORPHANED`); an empty or tag-only result is no result | `RECORD_INVALID` |
| `agent-usage` | `<run>/<item>/agents/<id>/usage.json` | `agents.finish`: `input`, `cached`, `output`, `usage_complete` | `RECORD_INVALID` |
| `review-verdict` | `<artifacts>/review-verdict.json` | `verdict_file`, tag `"schema": "orch-conductor-review-verdict/v1"` (read outside orch as published) | `RECORD_INVALID` |
| `provider-gates` | `<state>/orch/provider-gates.json` (machine) | `gates.set_gate`, `gates.clear` under `provider-gates.lock`, tag `"schema": "provider-gates/v1"` | `STATE_CORRUPT`, `RECORD_INVALID` |
| `observer-report` | `.swissknifeman/orch/reports/<run>/observer.json` | `observer.write_report`, tag `"schema": "orch-conductor-observer/v1"`; checked, then written with `records.write` (crash-safe, keys sorted); the optional `discarded_lines` counts the progress lines left out | `RECORD_INVALID` (nothing written) |
| `prompt-diff` | output of `orch conduct prompt diff --json` | `prompts.diff_manifests` and the command (`run`, `item`, `against`), tag `"schema": "prompt-diff/v1"` | `RECORD_INVALID` (exit 1) |
| `conformance-report` | rows of `orch conformance` | `conformance.run`: the rows are checked as `{"schema": "orch-conformance/v1", "rows": [...]}` (the tag of the catalogue); `--json` prints the rows alone, as before | `CONFORMANCE_INVALID` |

The five kinds that already published a short tag keep it as their carrier (`"schema": "<name>/v1"`, never `$schema`):
one without a tag is read as v0 with `schema` added, and `$schema` on them, another value or both carriers is
`unknown or conflicting record tag`. A record the conductor builds itself for output (observer report, prompt diff,
conformance rows, review verdict) that does not match ends with `... ; the conductor built a document outside its
contract; report this defect`. The agent records of a piece are written crash-safely (`durable_replace`, file and folder
`fsync`); `agents.read` and the cold recovery of stage usage (`budget.known_stage_usage`, for a run saved before
`stage_usage`) read them as checked records, so a damaged `usage.json` stops instead of counting as zero tokens;
`agents.read` skips a request it cannot open, and the observer report leaves out the agent runs of a piece
whose record does not match and names it on stderr.

Role streams never go into the artifact folder; a review verdict there is short and points at the stream in state.
The shared gitignore policy (`packages/aicore/configs/gitignore-policy.json`, entries `swissknifeman-state`,
`orch-conductor-reports` and `orch-artifacts`) states the same for every connected project, and `orch.py doctor` warns
when the runtime folder, the reports folder or the local artifact folder is not ignored (`orch.conductor-gitignore`,
`orch.conductor-reports`, `orch.conductor-artifacts`, `check-result/v1` with `--json`). `conduct prune` warns when the
local artifact folder of a run it removes holds evidence (`local_evidence`): the file source keeps it only there.

## Sandboxes

The tools of a role are confined by the provider's own sandbox, not by the conductor: Claude Code (Bash) and Codex use
bubblewrap in user and network namespaces, Claude also `socat`. It limits the **shell commands of a role and their
children**; the agent process is not limited (its model API stays reachable), and `scripts/ro-run.py` restricts only the
filesystem writes of the process. So `network` in a role manifest is intent: the dry-run says which roles it is enforced
for.

- `orch.py doctor` (`orch.sandbox`) probes it: `bwrap` and `socat` on PATH, and `bwrap --ro-bind / / --unshare-user
  --unshare-net --dev /dev --proc /proc true` (10 s, cached for the process; it changes nothing). On Ubuntu 24.04 and later
  `kernel.apparmor_restrict_unprivileged_userns = 1` stops it without an AppArmor profile for bwrap
  (`bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted`); the profile is a change of the machine, made by its owner.
- `instructions.sandbox`: for Claude writers at `access=confined`, `prefer` (default) adds the sandbox block
  (`enabled`, `allowUnsandboxedCommands: false`, `failIfUnavailable: true`) and the network allowlist from
  `sandbox_domains`. If unavailable, `prefer` reports the degradation and retains Landlock; `require` stops with
  `SANDBOX_UNAVAILABLE`; `off` adds no sandbox. Open writers and read-only Claude roles never get this block.
- **Read-only Claude roles.** Roles with `tools.filesystem: read` always use `ro-run --protect {cwd}` (Landlock ABI >= 3),
  independently of the provider sandbox. Reviewer and triager have working Bash (`acceptEdits`, `allowedTools Bash`)
  while the checkout stays read-only; an existing `vendor` directory is writable for test caches. A checkout under
  `/tmp` or `/var/tmp` uses `--no-default-rw --protect {cwd} --rw /dev --rw <agent TMPDIR>` and the optional vendor grant;
  other temporary directories stay read-only. Missing protection is `PROTECT_UNAVAILABLE` before launch, never a
  writable fallback. Network is open and reported as `NETWORK_UNENFORCED` when the manifest declares none.
- **Registrar.** Claude registrar is refused with `LAUNCH_REFUSED` in both access modes: its protect guard cannot write
  the plan workspace outside the checkout. A confined Codex registrar is refused for the same reason. Open Codex and
  the default `orch/conductor` registrar remain available.
- **Scratch and transcripts.** Every agent gets `<agent directory>/tmp` as `TMPDIR`, recorded in `write_roots` and granted
  with Landlock `--rw` / Claude `--add-dir` (and sandbox `allowWrite` when confined). Claude shared/handoff sessions get
  only their own transcript directory. For a project name longer than 200 characters, exactly one existing directory
  matching its 200-character prefix is required; otherwise `SESSION_NOT_PERSISTABLE` keeps `--no-session-persistence`
  and disables resume. Previews create no transcript directories. The session authority comparison excludes only the
  ephemeral agent TMPDIR grant; each recorded launch envelope still hashes its exact scratch path.
- **Setting sources.** An isolated Claude Code role (`instructions.isolate_roles`, isolation not `off`) starts with
  `--setting-sources user` (the catalog value `user,project` of the writers is replaced): the project's
  `.claude/settings*.json` no longer reach it, so their context-economy Read denies cannot become sandbox masks of
  `skills.json`, lock files or `node_modules`. The ask and deny rules of git push, reset --hard and clean those files carried
  come with the launch instead: the same `--settings` object holds `"permissions": {"deny": ORCH_PERMISSION_RULES}`
  (`Bash(git push*)`, `Bash(git reset --hard*)`, `Bash(git clean*)`, write forms of `git config --global` (reads `--get*`/`--list` remain available), `Bash(sudo *)`,
  `Bash(cat .env)`, `Bash(cat .env.*)`, `Read(.env)`, `Read(.env.*)`, `Read(**/*.pem)`, `Read(**/*.key)`, `Read(~/.ssh/**)`, `Read(~/.aws/**)`;
  `policies/authority.py`), never one without the other. A CLI that does not list both `--setting-sources` and
  `--settings` keeps the catalog argv (degraded `SETTING_SOURCES_UNSUPPORTED` in the envelope); under
  `instructions.isolation = require` that is `ISOLATION_UNAVAILABLE`. Deny rules of the user's own settings still apply
  (`read_masks: provider-settings` in the envelope of a sandboxed role). `strictAllowlist` with no domains also blocks the network of the project's own tests: put
  the domains they need into `sandbox_domains`.
- **Extra paths reach every writer.** `scope.extra_paths` (`--allow-path`) is granted to the `executor` and the
  `bounded-implementer` on every provider: a route under the Landlock guard gets `--rw P` (grok, and Claude Code when the
  sandbox does not apply); a Claude Code role also gets `--add-dir P` for its file tools (`--add-dir` takes several values, so
  the conductor puts a flag after the last one), and when the provider sandbox replaces the guard the sandbox block adds
  `"filesystem": {"allowWrite": [P…]}` (absolute or `~` paths; the provider merges it with the user's settings, and
  `allowUnsandboxedCommands: false`, `failIfUnavailable` and the network allowlist stay as they are); a Codex role gets `--add-dir P`
  right after `exec`. Every path passed `OPTIONS_UNSAFE_PATH` first; no role but a writer gets one, and without extra paths the
  command line does not change.
- **Access.** `[orch.launch] access` defaults to `open`. Claude writers use Landlock with checkout, extra-path,
  transcript and scratch grants, with no provider sandbox or OS read masks: network and Docker are open. Confined
  Claude writers use the provider sandbox described above. Open Codex writers use `danger-full-access`; confined ones
  use `workspace-write`, without network or Docker. Grok retains its Landlock filesystem guard in both modes, with
  network and Docker open; `--disable-web-search` disables web search for reviewer, triager, report-fixer and scout,
  but does not confine shell networking. Only Grok routes receive an explicit `--rw ~/.grok` grant.
  Project and environment layers may only tighten access; machine, invocation and flags may reopen it explicitly.
- A Codex route with `--sandbox read-only|workspace-write` is unavailable while the sandbox cannot start: `--dry-run` shows
  `available: false` and `SANDBOX_UNAVAILABLE: <reason>` in `unavailable`, a run stops with `SANDBOX_UNAVAILABLE`. Its argv is
  not rewritten.
- `orch conduct run --dry-run` also prints `sandbox: {available, reason}`, `network: {role: {declared, enforced, by}}` with `by` one
  of `claude-sandbox`, `codex-sandbox`, `claude-tools` (a Claude role without Bash has no command to confine) or `null`, and
  `warnings` for every role that declares `network: none` while nothing enforces it (the grok `reviewer`; every Claude role
  when the sandbox is off or cannot start), and `authority: {role: envelope}` (below). `routes[*].argv` stays the base route
  template; `isolation_args` holds the added provider arguments; the authority envelope names the effective guard
  and every writable root, including the grants inside its prefix. Matrix registrar rows describe the guard that causes their refusal; they do not admit
  an otherwise unavailable registrar route.

### The authority envelope

The authority of each launch is one document, conductor/v1 `authority-envelope`, computed by one pure function
(`policies/authority.compute`: it reads no provider file, creates nothing and starts no process; the probes are its
arguments): `role`, `provider`, `access`, `guard` (`landlock-rw`, `landlock-protect`, `claude-sandbox`, `codex-sandbox`,
`none`), `write_roots` (`{path, why}`: `.` the checkout, `./<rel>` under it, `~/…` under HOME, `/` unconfined; `why`
`checkout`, `guard`, `extra_paths`, `transcripts`, `tmpdir`, `unconfined`; a Landlock guard grants its default writable `/tmp`,
`/var/tmp` and `/dev` unless `--no-default-rw`, then its `--rw` folders), `read_masks`, `setting_sources`,
`permission_mode`, `permission_rules`, `network` (`declared`, `effective` none/allowlist/open, `enforced_by`,
`allowed_domains`), `docker` (open/blocked), `git` (`commit: work-source`; `push`/`reset_hard`/`clean` are `denied` only by
a command deny layer — the permission rules of orch — or for a role without a shell, else `unenforced`: a filesystem guard
filters no command, what it keeps out is `write_roots` and `dot_git_write`),
`isolation` (`profile`, `guarantee`, `args`, `env_keys` — names only —, `home_var`), `degraded` (`{code, detail}`) and
`digest` (`sha256:` of the canonical JSON without `digest`; the HOME of the machine is `~`, so the same authority on two
machines has one digest). The command line of the launch is built from it (`launch_plan.argv_from`); the `resume_argv` an
attempt runs to continue a session must have the same authority as the route's command (else `AUTHORITY_RESUME_MISMATCH`
before anything is written). It is written to `agents/<id>/authority/a<attempt>.json` before the process starts (see
*Agent runs*), the executor prompt gets an `authority` block from it (at most 12 lines: where to write — the extra paths and
the transcripts folder are named, not listed —, the network, Docker, what git forbids, what to do when a check needs what it
does not give; the Docker lines of the verification text follow `docker == open`), rebuilt with the stub for the route of
every attempt (a fallback to another provider gets the authority of its own launch), its digest enters the fingerprint of
the executor session, and `conduct run --dry-run` shows it per role.

`orch.py roles matrix [--markdown|--json]` prints the authority of every role and provider of the shipped launch catalog with
access open and confined, on a reference machine (the sandbox starts, the CLIs list the flags of their profiles, the default
options). A machine without the sandbox falls back to the Landlock guard for the Claude Code writers (the dry run shows
it). The table below is generated by it; a test keeps them equal:

Antigravity (`agy`) support is experimental and fail-closed by default. The independent [2026-11-01 audit](antigravity-audit.md) records earlier live failures and reproducible boundary canaries. Native binding preparation and conductor admission refuse AGY unless the owner explicitly opts in to the executor or reviewer exception below. Its native role adapter can translate
stream-json output and uses an agent-specific HOME under a Landlock write boundary. The CLI's
permission bypass grants its tools broad access: Landlock does not block network, Docker's Unix
socket, or host-file reads. The executor role declares no network, so without the opt-in the launch is
refused with `AGY_AUTHORITY_UNPROVEN`; the triager remains refused. Neither exception establishes a
verified network, IPC and read boundary. A live response or filesystem canary
alone does not establish those guarantees. The AGY selector and conversation ID are observable;
the underlying inference backend is not independently attested by this CLI. Opus/Sonnet xhigh is
not currently admitted. The catalog also lists `gemini-4-argon` and `gemini-3.8-flash` with no
admitted model class: the former returned a location restriction and the latter timed out in the
initial probes. Do not treat a routed, catalogued or listed model as a completed run.

The bridge supplies a session-only `--settings` object: `agentMode: accept-edits`,
`enableTerminalSandbox: false`, `allowNonWorkspaceAccess: true`,
`toolPermission: always-proceed`, `artifactReviewPolicy: always-proceed`, and
`disableSlashCommands: true`, alongside `--dangerously-skip-permissions`.
These are documented [AGY CLI settings](https://antigravity.google/schemas/v1/settings.json),
also accepted by the installed CLI's `--settings` flag. They avoid interactive file/artifact
approval and inherited terminal sandbox defaults without modifying persistent user settings.
The SKM role guard remains the filesystem boundary. CLI tool permissions and a terminal
sandbox are separate from that boundary; neither the existence of `--sandbox` nor plan mode
proves read-only isolation for all tools. See Google's [CLI permissions](https://antigravity.google/docs/permissions)
and [sandbox documentation](https://antigravity.google/docs/sandbox/).

For a local checkout, the owner can opt in for the conductor process by setting
`SKM_ORCH_AGY_UNSAFE_EXECUTOR=accept-unisolated-network-docker-host-reads` on its command line.
This permits only the JSONL AGY executor through the shipped bridge, with an agent-specific HOME,
the narrow Landlock write guard and no resume command. For workspace plans, the trusted work source supplies only
directories of the current item's declared `@plan/artifacts/` outputs. The guard opens those canonical directories
without following symlinks, and the per-attempt authority evidence lists them as output write roots. A missing or
symlinked output directory is refused at launch; other plans are not granted by this mechanism. The per-attempt
authority evidence records the explicit opt-in and that network, IPC (including Docker) and host reads are not
isolated. The `/dev` write grant includes `/dev/shm`, and Landlock ABI below 3 does not prevent
truncation outside the writable roots. The executor prompt forbids push, publication, tags and remote settings changes; those
instructions are not technically enforced. The opt-in is removed from the child environment.
The registered planner-orch bridge must be trusted to receive that invocation's opt-in for the
Planner claim. When the bridge is in a hub checkout, it resolves Planner and Orch from that same
checkout before PATH; explicit partner environment variables take precedence. Other invocations
do not inherit the opt-in from this run.
It also permits the exact explicitly selected `gemini-4-argon-high` selector to use the requested
stage class as a routing assumption; its class remains unverified. A later guarded bridge request
returned `OK` with matching init and terminal session `95071000-24a8-441e-8eb0-5a3da9486894`;
this does not prove a conductor or Planner run. Other
unknown AGY models still fail closed. This is not a verified sandbox or backend attestation.

For an owner-directed run, create a local options file with the executor explicitly selected:

```json
{"stages": [{"role": "executor", "provider": "antigravity", "model": "gemini-4-argon-high", "model_class": "implementation", "effort": "high"}]}
```

From the project checkout, substitute the actual plan ID, item and options file path. Inspect the dry run first;
the second command starts the real run and can change the checkout and plan:

```sh
SKM_ORCH_AGY_UNSAFE_EXECUTOR=accept-unisolated-network-docker-host-reads orch conduct --project . run --plan PLAN_ID --items ITEM --options /path/to/options.json --dry-run
SKM_ORCH_AGY_UNSAFE_EXECUTOR=accept-unisolated-network-docker-host-reads orch conduct --project . run --plan PLAN_ID --items ITEM --options /path/to/options.json
```

Planner's strict claim accepts this exact selector only with the same opt-in, records its route as
`ROUTE_MODEL_UNKNOWN`, and still checks the item's pinned route and effort. This is an owner routing
assumption, not evidence of the model's class or provider capability.

The reviewer has a separate per-process owner opt-in:
`SKM_ORCH_AGY_UNSAFE_REVIEWER=accept-unisolated-network-docker-host-reads`.
Select `"reviewer": "antigravity/gemini-4-argon-high/high"` in the normal run options and set this variable on
the conductor invocation. The executor opt-in does not admit a reviewer, and the reviewer opt-in does not admit
an executor, triager or another role. Without it the reviewer remains refused, including custom routes and fallbacks.
Only the exact explicitly selected `gemini-4-argon-high` receives the same unverified class assumption as the executor;
known catalogued models keep their ordinary class checks.

The reviewer requires the shipped JSONL bridge, a private agent HOME/XDG/TMPDIR and the canonical
`ro-run.py --metadata-guard --no-default-rw --protect <checkout> --rw /dev` prefix. Landlock ABI 3 or later protects
checkout contents, including truncation; the x86-64 seccomp metadata guard also denies chmod, timestamps and other
metadata changes in the provider and its descendants. Metadata mutation is denied in scratch as well.
The launch grants only private scratch and `/dev`, with no checkout, vendor, output, extra-path or resume grants.
Unsupported protection fails closed. Per-attempt authority evidence and the reviewer prompt record
`AGY_UNSAFE_REVIEWER_OPT_IN`: network, IPC (including Docker), host reads and external tools remain unisolated.
External tools or daemons can still change host state; this is an explicitly accepted local execution mode,
not a fully isolated read-only sandbox. The reviewer is instructed to avoid external mutations, Docker, push,
publication, tags and remote settings changes. Both AGY opt-in variables are removed from child agent environments.

For example, for a review-only input already prepared for the intended checkout:

```sh
SKM_ORCH_AGY_UNSAFE_REVIEWER=accept-unisolated-network-docker-host-reads orch conduct --project . run --input review.json --options review-options.json --dry-run
SKM_ORCH_AGY_UNSAFE_REVIEWER=accept-unisolated-network-docker-host-reads orch conduct --project . run --input review.json --options review-options.json
```

Local AGY 1.5.1 was checked on 2026-11-06. Its `--mode plan` prepends `/plan` instructions and does not establish
enforcement; `--sandbox` can have no effect when containment is unavailable. Custom agents and PreToolUse hooks
offer further provider controls, but their complete tool coverage has not been established here. The reviewer
exception therefore does not claim those controls as isolation. Sources: [execution modes](https://antigravity.google/docs/cli/modes/),
[CLI flags](https://antigravity.google/docs/cli/reference/), [permissions](https://antigravity.google/docs/permissions/),
[custom agents](https://antigravity.google/docs/subagents/) and [hooks](https://antigravity.google/docs/hooks/).

<!-- authority-matrix:begin -->
| role | provider | access | guard | network | enforced by | docker | setting sources | isolation |
|---|---|---|---|---|---|---|---|---|
| context-scout | claude-code | open | landlock-protect | none | claude-tools | blocked | user | full |
| context-scout | claude-code | confined | landlock-protect | none | claude-tools | blocked | user | full |
| context-scout | codex | open | codex-sandbox | none | codex-sandbox | blocked | all | partial |
| context-scout | codex | confined | codex-sandbox | none | codex-sandbox | blocked | all | partial |
| context-scout | grok | open | landlock-protect | open | - | open | all | partial |
| context-scout | grok | confined | landlock-protect | open | - | open | all | partial |
| executor | antigravity | open | landlock-rw | open | - | open | all | none |
| executor | antigravity | confined | landlock-rw | open | - | open | all | none |
| executor | claude-code | open | landlock-rw | open | - | open | user | full |
| executor | claude-code | confined | claude-sandbox | none | claude-sandbox | blocked | user | full |
| executor | codex | open | none | open | - | open | all | partial |
| executor | codex | confined | codex-sandbox | none | codex-sandbox | blocked | all | partial |
| executor | grok | open | landlock-rw | open | - | open | all | partial |
| executor | grok | confined | landlock-rw | open | - | open | all | partial |
| bounded-implementer | antigravity | open | landlock-rw | open | - | open | all | none |
| bounded-implementer | antigravity | confined | landlock-rw | open | - | open | all | none |
| bounded-implementer | claude-code | open | landlock-rw | open | - | open | user | full |
| bounded-implementer | claude-code | confined | claude-sandbox | none | claude-sandbox | blocked | user | full |
| bounded-implementer | codex | open | none | open | - | open | all | partial |
| bounded-implementer | codex | confined | codex-sandbox | none | codex-sandbox | blocked | all | partial |
| bounded-implementer | grok | open | landlock-rw | open | - | open | all | partial |
| bounded-implementer | grok | confined | landlock-rw | open | - | open | all | partial |
| reviewer | antigravity | open | landlock-protect | open | - | open | all | none |
| reviewer | antigravity | confined | landlock-protect | open | - | open | all | none |
| reviewer | claude-code | open | landlock-protect | open | - | open | user | full |
| reviewer | claude-code | confined | landlock-protect | open | - | open | user | full |
| reviewer | codex | open | codex-sandbox | none | codex-sandbox | blocked | all | partial |
| reviewer | codex | confined | codex-sandbox | none | codex-sandbox | blocked | all | partial |
| reviewer | grok | open | landlock-protect | open | - | open | all | partial |
| reviewer | grok | confined | landlock-protect | open | - | open | all | partial |
| triager | claude-code | open | landlock-protect | open | - | open | user | full |
| triager | claude-code | confined | landlock-protect | open | - | open | user | full |
| triager | codex | open | codex-sandbox | none | codex-sandbox | blocked | all | partial |
| triager | codex | confined | codex-sandbox | none | codex-sandbox | blocked | all | partial |
| triager | grok | open | landlock-protect | open | - | open | all | partial |
| triager | grok | confined | landlock-protect | open | - | open | all | partial |
| registrar | claude-code | open | landlock-protect | open | - | open | user | full |
| registrar | claude-code | confined | landlock-protect | open | - | open | user | full |
| registrar | codex | open | none | open | - | open | all | partial |
| registrar | codex | confined | codex-sandbox | none | codex-sandbox | blocked | all | partial |
| report-fixer | claude-code | open | landlock-rw | none | claude-tools | blocked | user | full |
| report-fixer | claude-code | confined | landlock-rw | none | claude-tools | blocked | user | full |
| report-fixer | codex | open | codex-sandbox | none | codex-sandbox | blocked | all | partial |
| report-fixer | codex | confined | codex-sandbox | none | codex-sandbox | blocked | all | partial |
| report-fixer | grok | open | landlock-protect | open | - | open | all | partial |
| report-fixer | grok | confined | landlock-protect | open | - | open | all | partial |
| researcher | claude-code | open | landlock-protect | open | - | open | user | full |
| researcher | claude-code | confined | landlock-protect | open | - | open | user | full |
| researcher | grok | open | landlock-protect | open | - | open | all | partial |
| researcher | grok | confined | landlock-protect | open | - | open | all | partial |
| advisor | claude-code | open | landlock-protect | open | - | open | user | full |
| advisor | claude-code | confined | landlock-protect | open | - | open | user | full |
| advisor | grok | open | landlock-protect | open | - | open | all | partial |
| advisor | grok | confined | landlock-protect | open | - | open | all | partial |
<!-- authority-matrix:end -->

## Isolation profiles

A role named in `instructions.isolate_roles` is kept away from its provider's own settings (the repository `CLAUDE.md` /
`AGENTS.md`, memory, plugins, hooks, MCP servers, personal skills) by the profile of the provider in
`configs/isolation-profiles.json` (conductor/v1 `isolation-profiles`, read by `policies/isolation.py`): its arguments, its
environment, its home directories, the flags its CLI must list, and what the first init event of its stream must not show.
The guarantee is honest: `full` only when every required surface is `off` or confirmed off by a live probe of the installed
CLI version.

| Provider | What an isolated role gets | Guarantee |
| --- | --- | --- |
| claude-code | `--safe-mode --strict-mcp-config`, `CLAUDE_CODE_DISABLE_CLAUDE_MDS=1`, `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1` (`--bare` stays refused: it does not read the OAuth subscription); the init event must list no `mcp_servers` and no `plugins` | full |
| codex | `--ignore-user-config -c project_doc_max_bytes=0`; `CODEX_HOME=<run dir>/isolation/codex-home` and `HOME=<run dir>/isolation/codex-user-home` (both 0700 and empty but for `auth.json`, a symbolic link to `auth.json` of the original `CODEX_HOME`, else `~/.codex`; `[orch.isolation.codex] auth = "copy"` copies it instead, for a machine whose codex refuses the link: a copy rotates the refresh token and can log the interactive codex out); `XDG_CACHE_HOME` stays the original one. The personal skills (`~/.agents/skills`), `~/.codex/config.toml` and the rules of the original HOME are not seen; a project is not trusted in the new CODEX_HOME, so its `.codex` layers are skipped. `project_doc_max_bytes=0` is undocumented: the repository instructions count as a canary | partial; full after `isolation-probe.py --provider codex --live` confirmed the repository instructions and the personal skills off for this version |
| grok | nothing: grok 1.0.50 has no switch for its instructions, skills, plugins or MCP servers; the init event must list no `mcp_servers` and no `skills` | partial |

- The flags are asked of the help command of the profile (`codex exec --help`: the flags of `exec` are not in
  `codex --help`), once per CLI file (real path, inode, size and change time: a CLI updated in place is asked again),
  version (`<cli> --version`), help command and flags in the process; a timeout is tried once more. A flag the CLI does
  not list is left out and the guarantee falls to partial. A route whose command is not `claude`, `codex` or `grok` (a
  wrapper of `[orch.conductor.argv]`, a stand-in) gets the flags of its profile as asked, but nothing is confirmed: its
  guarantee is partial (`the command of the route is not a provider CLI the profile can probe`).
- `instructions.isolation`: `prefer` (default) starts a role whose guarantee is not full and says `ISOLATION_PARTIAL` once
  per run, provider and reason; `require` stops with `ISOLATION_UNAVAILABLE` in the preflight, before any work, and before
  each later role of a provider that drifted; `off` adds no argument, environment or home. A work-source layer may only
  tighten it (`off` → `prefer` → `require`).
- The init event of claude-code and grok (`system/init`) is kept as names (`tools`, `mcp_servers`, `skills`, `plugins`,
  `slash_commands`) in `result.json` `isolation.observed` of an isolated role; a name in a field the profile keeps empty is
  `ISOLATION_DRIFT`. Codex streams have no init event: its probe is the live one.
- The session fingerprint carries the home of the provider (`isolation_home`: the CODEX_HOME of the run for an isolated
  Codex executor): a session kept in another home starts fresh (`fingerprint_changed:isolation_home`).
- `python3 packages/orch/scripts/isolation-probe.py --provider P [--live] [--json]`: without `--live` only `--version` and
  the help command, whether every flag is listed (exit 1 if not). `--live` (the owner runs it): codex renders a temporary
  project whose `AGENTS.md` holds a canary and a temporary HOME whose `.agents/skills/skm-canary/SKILL.md` holds another with
  `codex debug prompt-input` under the profile (no model is called); the render must be a JSON list of messages that carries
  the prompt the probe sent, else the probe fails (`ISOLATION_PROBE_FAILED`, exit 2) and records nothing. grok runs
  `grok inspect --json` for a temporary project with `CLAUDE.md`, `AGENTS.md` and a project skill, with a temporary `HOME`,
  XDG folders and `GROK_HOME` (its answer must be JSON). The claims are kept in
  `<state>/orch/isolation-probes.json` (conductor/v1 `isolation-probes`) per provider and version; no auth file is read.

## The runs of a project: `conduct runs`

`orch conduct runs [--limit N] [--json]` lists the conductor runs of the project, newest first (by the first line of
the journal, then by run id), reading only the run folders (`run.json`, `progress.jsonl`). It is additive: no existing
command and no contract changes. `--json` prints one object:

```json
{"runs": [{"run_id": "cnd-...", "status": "running|finished|blocked|...", "reason_code": null,
           "created": "2026-10-17T09:00:00Z", "items": ["P1.1"], "resumes": 0, "owner": null}]}
```

`status` and `reason_code` are those of `conduct status` (from the journal), `created` is the time of the first journal
line (`null` before any line), `items` are the pieces of work seen in the journal (else those of `run.json`), `resumes`
counts the `run.resume` lines. A project without runs gives `{"runs": []}`; a run whose `run.json` cannot be read is
`{"run_id": "cnd-...", "status": "unreadable", "owner": null}` and never an error. `--limit` is at least 1. Without `--json` one line
per run is printed. Exit 0; the project is required as for every other `conduct` verb.

`owner` is `{pid, host, started_at, command}` (and `start_ticks`, `boot_id`, `launcher` of a lease that has them) only while
the run lease is held, otherwise `null`; stale metadata alone never implies ownership. Every readable run also has `health`,
the class of `health.classify` (see Heartbeat and health), which `status --json` gives as an object. `status --json` adds the same metadata as `lease`, plus `limits`, `beacons` and
per-item `tokens`, `usage_incomplete`, `routes`. Existing journal fields retain their meaning. Missing item usage
is `null`, routes are `{}`, and missing limits are `{}`. Routes expose only `provider`, `model`, `effort`, `class`.
`limits.items` maps item refs to `tokens_max` and effective `tokens_hard_max`; `run_tokens_hard_max` retains
`{value, source, file?}` provenance, with an invocation source when raised. `limit_raises` preserves the raise history,
including an explicit zero removing a hard limit. `beacons` contains the last info event per code, in journal order,
for `BUDGET_OVER`, `BUDGET_UNMETERED`, `STAGE_INTERRUPTED`, `ROLE_ORPHAN_KILLED`, `LIMIT_RAISED`.
JSON display values are redacted before safe shortening; argv and environment from route snapshots are excluded.

### Removing old runs: `conduct prune`

`orch conduct prune --older-than DAYS [--dry-run] [--apply] [--json]` removes what runs that ended more than `DAYS` days ago
(`DAYS` at least 1; counted from the last journal line, else the folder time) left behind: the run state folder, the observer
reports `.swissknifeman/orch/reports/<run id>` and the fallback artifacts `.swissknifeman/orch-artifacts/<run id>`. It is a
dry run unless `--apply` is given (`--dry-run` says so explicitly; both together are refused), so by default it lists
`{run_id, status, age_days, paths, removed}` per run and removes nothing. The latest run (the default of `conduct status`), a
run that is running, and a run whose `run.json` cannot be read are never listed. Not touched: an `artifacts_dir` that a work
source names itself, and the aicore event journal (its compaction changes delivery offsets and is the owner's decision). The
fallback artifacts are committed records: after `--apply` the removal shows in `git status` and is committed by the owner.

**Compressing raw streams.** `orch conduct prune --compress-older-than DAYS [--dry-run] [--apply] [--json]` (instead of
`--older-than`; the two exclude each other) keeps the runs and packs only their raw role streams: every
`*.jsonl`, `*.txt`, `*.stderr` and `*.times` file in a `streams` folder below the run (the pieces, their earlier attempts
under `attempts/<n>/streams/`, the run's own `streams/` of group reviews and batch reviews) becomes `<name>.gz`. The runs are
those `--older-than` would remove (a status of `runs.PRUNABLE`, older than `DAYS`, never the latest run); the journal,
`state.json`, the agent records, the prompts and the check logs stay as they are, so `status`, `timeline`, `observe` and the
observer metrics read the run as before. A dry run (the default) lists the files and their size. `--apply` takes the run lease
first (a busy lease skips the run with the reason, as `prune` does), looks at the status and age again under it, writes each
copy under a temporary name, reads it back and compares it with the original, renames it into place and only then removes
the original; a copy that does not read back leaves the stream as it was (`reason: not packed …`). Links are neither
followed nor packed. Rows: `{run_id, status, age_days, compressed, bytes_before, bytes_after}` (`reason` when skipped;
`bytes_after` null for a dry run); `--json` prints them as a `compress-result` document (`schemas/conductor/v1`). The
readers of streams take the packed file in place of a missing one through `process.open_stream(path)`
(`<path>` else `<path>.gz`): the last command of a beacon, `scripts/step-profile.py` (with its `.times`), and
`scripts/run-usage.py` reads only `progress.jsonl`, which is never packed. The observer reads no stream at all.

## Observer

The observer only reads: the journal and state of the run and the `orch.*` and `planner.*` events of the
project's aicore event journal. Event counts use UTC, from the run start through `state.ended` or the last progress
line, inclusive. Only events whose subject or correlation id matches the conductor run id or an item's `orch_run`
are counted, including agent, provider, review and deviation events. At the end of every run (also a stopped one) the conductor
writes `observer.json` and `observer.md`: repeats and resumes, red checks per check id, review findings by severity,
triage confirmed and rejected, idle time between stages, seconds and tokens by role, scout cache hits, the heaviest prompt blocks by role and the prompt budget classes against their limits (`prompt_budgets_by_role`: largest tokens of a step, limit, steps, steps over; from the prompt manifests), the outcome of
each piece and proposals to improve the run options. `orch conduct observe --follow` prints the notable lines of a run
that is still going from another terminal; `orch conduct observe` writes the report again. Follow exits 0 only after
the latest start/resume segment has ended. Without that final `run.end`, two consecutive free-lease probes give
exit 3 and a resume hint; an unavailable probe keeps waiting. The observer never writes run state or progress.
Silence alone never returns success (`idle_exit_s` remains accepted by the Python helper but no longer ends follow).
Appending progress after a torn line first restores its newline, so the next event remains readable.

**Incremental reading of follow.** `follow` does not read the whole journal on every poll (2 s): `ProgressCursor`
(`observer/reader.py`) keeps the byte offset it has read and the unfinished tail, and each poll reads only the bytes
after the offset. Only lines ended by a newline are parsed; a line the writer has not finished stays in the tail until its
newline arrives, so no line is lost or read twice. A complete line that is not a progress line is skipped and counted, as
`read_lines` does. When the journal became shorter than the offset, its beginning differs from the one read, it was
replaced by another file or it disappeared, the cursor reads from the beginning again and `follow` forgets the lifecycle
it had seen. The printed lines, the exit codes and `observer.json` / `observer.md` are the same as before. A valid line
without its final newline is shown by the poll after the newline arrives (the whole-journal reader used by `build` and
`status` accepts it at once).
`state.ended` keeps the precise UTC end of a completed segment, including fractions of a second; it is cleared by
the next loop. A running segment uses the latest progress line even if an earlier end remains in an older state save.

**Checks by command.** `checks_by_command` (and the table *Checks by command* in `observer.md`) aggregates the command
rows of `state.items.*.steps.checks.*.result[]` (and of earlier attempts) by command: `runs` (every row), `executed` /
`invocations` (rows that started a process), `seconds` (elapsed time of those runs, not CPU time), `red` (executed rows that
failed), `skipped`, `reused` (with `saved_s` and the evidence in `reused_from`), `retried` (an executed check that an
earlier round of the same item had already executed), `ids`, `contexts` (`local`, `standalone`, `partner`, `installed`, from
the command text) and `items`. A skipped row (`fail_fast`, `phase_after_red`) and a reused row ran nothing: they are never
counted in `red` or `red_checks`, even when an older journal names them in a `red …` verdict. The same suite in different
contexts is not a duplicate. The old fields of the report stay as they were; `check_findings` holds what the proposals use
(`duplicate_modules`, `phase_after_red`, `executor_runs_checks`).

Proposals about checks: *item X runs the tests of M twice* (validate.sh of a module without `SKM_VALIDATE_SKIP_TESTS=1` and
the full `test.sh` or `affected-tests.py --run`, or a full `test.sh` and its `-p` subset, in one round and one context),
*phase checks of X ran after a red item check* (needs the cadence of the checks from the item's `input.json`), and
*`checks.executor_runs_checks` is true*. A red check never asks the executor to rerun unchanged acceptance or full suites:
the proposal names concrete new or failing diagnostics or a faster local variant, and the conductor keeps the named
acceptance checks and the phase gates.

### Observer — item metrics

`metrics` of `observer.json` (and the table *Item metrics* of `observer.md`) holds the metrics of every piece, written at
the end of every run with or without debug (`observer.item_metrics(run_dir)`, computed in `observer/metrics.py`). Sources:
`progress.jsonl`, `state.json`, `agents/*/{request,result,usage}.json` and `supervisor.jsonl`; never a raw stream. One row
per piece (state order):

| Field | Meaning |
| --- | --- |
| `wall_s` | Seconds the piece was on: from its first to its last journal line within each conductor process, summed over the resumes (the time between a stop and a resume is not the piece's). |
| `active_s` | `duration_s` of its `stage.end` lines by role group: `executor` (`executor.*`, corrections and follow-ups), `checks` (`checks.*`), `review`, `triage`, `scout`, `advice`, `registrar`, and `conductor` for the other deterministic steps (brief, prepare, register, commit). |
| `checks_share` | `active_s.checks / wall_s` (0 without wall time); a checks round is one step, so parallel checks are not counted twice. |
| `rounds` | Ended steps: `executor`, `review`, `checks`. |
| `resume_repeats` | Steps started again after a resume that an earlier conductor process of the run had started. |
| `heal` | `healed` (`RESULT_HEALED`), `repaired` (`RESULT_REPAIRED`), `unrepairable` (`REPAIR_FAILED`). |
| `beacons` | Info lines of the piece by reason code. |
| `tokens` | `input` (fresh), `cached` and `output` tokens of its agent runs (`usage.json`). |
| `deviations` | Deviations recorded for the piece (`deviation_ids` of the state). |
| `findings` | Triage `confirmed` and `rejected`, review findings `by_severity` of the current steps. |
| `health_transitions` | Changes of the health class in `supervisor.jsonl` (`{at, from, to, reason_code, action}`) while the run was on the piece: the piece of the last journal line at or before the action, unless that line ended it. |

`metrics.health_transitions` lists every transition of the run. The per-check table *Checks by command* stays as it was.
The field is additive in `records/v1 observer-report`; a report written before it reads as before.

### Debug mode

`[orch] debug` (default `false`) is set per machine (`~/.config/swissknifeman/config.toml`), per project
(`<project>/.swissknifeman/config.toml`, wins over the machine) or for one run with `run`/`resume --debug` or
`--no-debug` (wins over both; `SKM_ORCH_DEBUG` and `--config` sit in between). With it on, the run prints the beacon
`DEBUG_MODE` after `run.start` and after every resume: the layer that switched it on, the observer protocol
(`dev-skills/orch-debug/SKILL.md`), the observer report with the per-item metrics (`.swissknifeman/orch/reports/<run>/
observer.md`, `orch conduct observe --run <run>`) and `<run>/debug/journal.md` for the notes of the observer. The
announcement writes no file: the metrics are the observer's (written with or without debug), and `<run>/debug/journal.md`
is created by the agent of the orch-debug protocol only when it has something to record (a resume never touches it).
`run.json` records `debug`. The roles, their prompts, the decisions of the conductor and the lifecycle facts it records do
not change: the mode tells the agent who watches the run to work as a team-lead observer and where to keep its record.

## Configuration

The `report-fixer` role runs on the conductor's provider by default (an economy model: Claude Code haiku, Codex `gpt-6-luna`, grok);
a `stages` entry `{"role": "report-fixer", "provider": …, "model_class": …}` moves it, and `limits.repairs: 0` turns it off.

`[orch.conductor]` (`configs/config.schema.json`): `provider` (default `claude-code`), `reviewer`
(`grok/grok-4.7/high`), `registrar` (`orch/conductor`), `rules`, `on_blocked`, `questions` (`queue` default, `deny`, `defaults`, `advisor`), `risk` (weights, patterns and `diff_lines` of the dynamic review), `limits.tokens_max`,
`limits.stage_timeout_s`, `limits.check_timeout_s`, `limits.unmetered`, `limits.unmetered_charge_tokens`, `limits.role_timeout_s`, and `argv.<role>`: the command line of a role instead of the
launch catalog entry (`{model}`, `{effort}`, `{cwd}`, `{orch}` are filled in). `argv` is machine-wide: a project file
cannot set it. The tests use it to put fake providers in place of the real CLIs.

Every launch role/provider pair has exactly one entry or refusal in `configs/launch-catalog.json`:

| Role | claude-code | codex | grok |
| --- | --- | --- | --- |
| scout | ✓ | ✓ | ✓ |
| executor | ✓ | ✓ | ✓ |
| bounded-implementer | ✓ | ✓ | ✓ |
| reviewer | ✓ | ✓ | ✓ |
| triager | ✓ | ✓ | ✓ |
| registrar | ✓ | ✓ | refused: plan writes outside checkout |
| report-fixer | ✓ | ✓ | ✓ |
| researcher | ✓ | refused: read-only has no network | ✓ |
| advisor | ✓ | refused: read-only has no network | ✓ |

**File format.** The file states only what is specific. `defaults` hold the fields every entry shares (`transport`, `model_set`);
each role under `roles` holds the fields its providers share (`model_class`, `effort`, `transport`, `timeout_s`) and a
`providers` object with, per provider, its `argv` and only the fields that differ from the role (a `timeout_s` of one
provider, say). An `@name` item of an `argv` stands for the named list under `parts` (`@@` is a literal `@`); a part cannot
name another part and every part must be used. The sandbox and the tool restrictions of a role stay in its own `argv`, never
inside a shared part. `launch.expand_catalog` resolves the file into `launch` -> role -> provider -> entry, which is what every
reader sees (`orch.py launch list|show|argv`); a file already in that resolved form (a `launch` object) is accepted as it is.
`tests/golden/launch-catalog-resolved.json` pins the resolved catalog: a change to a command line, a sandbox flag, a class, an
effort or a timeout of any entry fails `test_launch_compact` until the snapshot is updated as the review of that change.
A machine or a project changes single fields without editing the file: `[orch.launch.entries]` (see
[configuration](configuration.md)).

`refusals: {role: {provider: reason}}` is optional for older catalogs. Each reason is a non-empty string of at most
300 characters; a pair cannot appear in both `launch` and `refusals`. Lookup of a refused pair returns
`LAUNCH_REFUSED: <role>/<provider>: <reason>`, while a pair in neither section keeps `LAUNCH_UNKNOWN`.
Required roles stop before work; optional roles (`context-scout`, `report-fixer`) are skipped. Dry-run marks such
roles `available: false` with the code and reason in `unavailable`, omitting them from `routes` because no argv
exists. `route explain` names the refused provider and reason too. The existing registrar.codex entry (sandbox
`{write_sandbox}`) remains an explicit exception to the read-only sandbox checks.

Grok's `executor` and `bounded-implementer` launch entries use jsonl under `scripts/ro-run.py --rw {cwd}`
(implementation/high, 3600 s and economy/medium, 1800 s respectively). The `reviewer`, `triager`, `researcher`,
`advisor` and `report-fixer` also use jsonl and the same wrapper. All read stdin through `--prompt-file /dev/stdin`, select `--model` and `--effort`,
use `bypassPermissions` and emit `--output-format streaming-messages-json`. A sanitized real stream fixture pins
the existing parser's text, terminal result, errors and token usage; no live model call is needed by the tests.
ACP routes are still refused. Preflight checks the provider after `--` without starting it and caches command
availability for the process: a missing Grok CLI gives `available: false` and `PROVIDER_UNAVAILABLE` in the dry-run,
and stops a required route before claim.

Ordinary Codex scout, and every other Codex role whose launch class is `economy` and whose route does not name a model,
uses `gpt-6-luna` (effort `low` for scout). `gpt-5.6-luna` stays in the inventory and is not the preferred selector.
An explicit executor, reviewer or owner model is kept. Implementation stays `gpt-6-sol` and frontier stays `gpt-6-astra`.
The Grok `scout` uses text transport, `--output-format plain`, `--disable-web-search`, economy/low and 300 s.
The `triager` and `researcher` use implementation/medium and 1800 s; the `advisor` uses frontier/high and 1800 s.
The `reviewer` and `triager` use `--protect {cwd} --rw {cwd}/vendor`; the `scout`, `researcher`, `advisor` and
`report-fixer` use `--protect {cwd}` with no checkout grant. Researcher/advisor keep `run_terminal_command` and
`web_search` to query research sources. `research query` prints results and passes the project cwd to source
commands; configured source processes inherit Landlock, and writes outside its writable areas fail.
All these protected roles disallow `search_replace,write,spawn_subagent,scheduler_create,scheduler_delete,workflow,image_gen,image_edit,image_to_video,reference_to_video`;
the report-fixer also disallows `run_terminal_command`. Landlock permits default writes to `/tmp`, `/var/tmp`,
`/dev` and `~/.grok`; the reviewer and triager also grant the checkout's real `vendor` directory for test caches. Runtime
`--rw` grants for authorized `scope.extra_paths` still apply.

`ro-run.py --protect DIR` is repeatable and fails before starting the provider (exit 3) when the real protected path
is inside a default writable root (`RO_RUN_PROTECT_OVERLAP: <DIR> is inside writable <root>`), an in-checkout
`--rw` path is a symlink or resolves outside it (`RO_RUN_RW_ESCAPE: <path>`), or Landlock ABI is below 3
(`LANDLOCK_ABI_TOO_OLD: <abi>`). This includes checkouts under `/tmp` and symlinked vendor grants. ABI 3 supplies
TRUNCATE protection; calls without `--protect` keep their existing writable rules.

Claude Code roles never use `--bare` (it does not read the subscription login) and
start with `--permission-prompts none`, so a request that would ask for permission is denied instead of waiting.

## Plan engines without `orchestration.options`

The planner declares `orchestration.options` as an extension slot and keeps no copy of this contract: the planner
bridge supplies `run-options` to it (`extends` in its `bridge.json`), so `set` and `check` validate the options by
this schema. A plan engine without the slot refuses the fields with `unexpected property`; a planner that does not find
the bridge refuses the options with `EXTENSION_UNAVAILABLE` and still keeps `orchestration.scenario`. The planner
bridge then reads the scenario and the options from orchestration overlay documents (`add-document`, id
`orchestration-<scope>`, section `orchestration` holding `{"scenario"?, "options"?}`, applying to a phase, an item or,
with `global`, the plan). A field of the same level wins over an overlay.
