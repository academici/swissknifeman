# Review findings

This page records operational limitations and the behavior covered by regression tests.

## 1. Concurrent migrations on a fresh PostgreSQL cluster

The migration runner prepares the two cluster-wide roles before it executes the immutable project baseline.
A competing transaction can create the same role. The runner accepts that specific duplicate and both
databases can finish their first migration. Database owners without role-creation privileges still need
the operator to provision the roles for server mode.

## 2. Verified launches on relocatable CPython installations

Each interpreter snapshot has its own private directory. For CPython, its `pyvenv.cfg` names the
installation's original binary directory so the copied executable can find the standard library.
The executable and Landlock wrapper remain pinned. The worktree and Landlock launch tests execute
the runtime. Landlock requires kernel ABI 3.

## 3. Graceful shutdown

On the first termination signal, the HTTP server starts stopping background services and drains requests
against the same deadline. The shutdown regression keeps a database lock held and measures both
connection release and process exit from delivery of that signal.

## 4. `local clean --worktrees` previews a worktree that the real run then skips

- **Where:** the preview (`skm local clean --worktrees --dry-run`) in
  `src/skm/bootstrap/local_cleanup.py::clean_worktrees`, and
  `src/skm/modules/execution/application/commands/mark_environments_removed.py::handle`.
- **What:** the preview lists a discarded worktree of a completed attempt, but `--yes` can report `marked: 0`
  for it. `handle` skips an environment while any assignment of the attempt still holds an unexpired lease, a
  stage has started without a result, or an effect is unresolved; the preview applies none of these guards.
- **Impact:** the operator is told a worktree will be removed and it silently stays.
- **Suggested fix:** compute the preview with the same selection as `handle` (one shared query), or make the
  preview report the skipped worktrees with the reason.
- **Status:** still present on this branch. An earlier findings entry was dropped after e2e updates on `new`;
  the product gap in the preview was not removed. This branch leaves the product and
  `tests/e2e/test_local_lifecycle_shutdown.py::test_worktree_preview_and_removal_through_postgres`
  unchanged. The test is flaky: it failed with `marked == 0` after a matching dry-run on run
  45614423092, passed on later runs, failed on 18.7 e2e in 45622999401 while 19.0 passed, and failed
  on 19.0 e2e in targeted run 45629580423 while 18.7 passed.

## Operational findings

The following entries describe independently observed behavior. Open items still require a product change
or an owner decision.

### S1. High: the interactive `safe_dirs` hook treats `~/…` as a path inside the worktree

- **Status:** fixed on this branch. `LocalHookState` expands a leading `~` from the hook process's `HOME`
  (falling back to the passwd entry), resolves the result, and the hook's `ScopeRoots` carries that home, so home
  writes are judged outside the worktree and secret paths such as `~/.ssh` are recognised. Regression:
  `tests/security/test_hook_home_paths.py`.

- **Where:** `src/skm/adapters/git/hook_state.py:208` (`LocalHookState.resolve`, also used by `facts()` at
  line 221), called from `src/skm/modules/integrations/host/evaluate_hook.py:216-221`.
- **What:** `resolve` joins the raw word onto `cwd` with `Path(cwd) / path`, so `~/.bashrc` becomes
  `<cwd>/~/.bashrc`. The shell parser leaves `~/` words for `PathFacts` to expand (only `~user`, `~+` and `~-` are
  made opaque, `policy/domain/shell_words.py:341`), and `StaticPathFacts.resolve` does expand them, but the hook
  implementation does not. The `ScopeRoots` built for the hook also has `home=None`.
- **Impact:** in the interactive enforcement hook, `echo x >> ~/.bashrc`, `cp key ~/.ssh/authorized_keys` and the
  same targets in `Write`/`Edit` tool calls are classified as writes to `main:~/…` inside the worktree. That is the
  allowed scope, so the guard says nothing about a write to the real home directory.
- **Reproduce:** with the policy test layout (`tests/unit/policy/domain/layout.py`), classify
  `RunCommand("echo x >> ~/.bashrc", WT)` once with `LocalHookState(...).facts(WT)` and once with `FACTS`. The hook
  facts give `OperationHit(modify_write_set, subject='/w/attempt/repo/~/.bashrc', scoped=worktree:main:~/.bashrc)`.
  The static facts resolve `/home/dev/.bashrc`, which is outside the worktree. Checked locally on `10360ac31`.
- **Suggested fix:** expand `~` and `~/` in `LocalHookState.resolve` from the hook process's `HOME`, the way
  `StaticPathFacts.resolve` does. Pass that home into the hook's `ScopeRoots`. Add a hook-level regression for
  `~/.bashrc` that asks or denies.

### S2. High: every runtime event is a full lease renewal, and two fast failures cancel the run

- **Where:** `src/skm/modules/execution/host/stages/agent_step.py:78-82,116` calls
  `BoundStageClient.report_progress` (`src/skm/modules/execution/host/stage_client.py:108`) for every
  `TextDelta`, `ToolRequested`, `ToolCompleted` and `UsageReported` event. Each call dispatches `renew_lease`
  (`stage_client.py:81-106`) with a new idempotency key. On the server side,
  `src/skm/modules/execution/application/commands/renew_lease.py:274-300` touches the step, renews the lease and
  extends integration slots, assignment tokens and artifact grants.
- **What:** there is no throttle between the runtime stream and the control plane. The failure latch in `_renew`
  (`__failures >= 2` → `lease_lost`) was sized for heartbeat cadence (`renew_every_seconds` < TTL/2), but progress
  reports share the counter. `_report_progress` suppresses the exception after the latch has already fired.
- **Impact:** a short API outage or restart of one or two seconds, during a chatty stream, gives two consecutive
  failures within milliseconds. The worker cancels a healthy agent with `lease_lost` while the lease still has
  most of its TTL. In steady state each streamed event costs one control-plane transaction with about six row
  updates and one idempotency receipt. Receipts are kept for `storage.idempotency.ttl_hours` (72 h), so a few busy
  workers add millions of rows.
- **Reproduce:** use a `BoundStageClient` whose client raises `BackendUnavailable` twice, then call
  `report_progress` twice in a row. The cancel source is latched with `lease_lost` without a heartbeat ever
  failing; checked locally on `10360ac31` (two dispatches, `cancelled=True`, reason `lease_lost`). Separately, count
  `renew_lease` dispatches for a fake runtime that emits N `TextDelta` events: there are N, plus the heartbeats.
- **Suggested fix:** coalesce progress on the host. Keep the latest progress and pending tool calls, and send at
  most one renewal per interval (for example 1-2 s, or immediately for a tool-call batch of 100). Count only
  heartbeat-due renewals toward the `lease_lost` latch. The alternative is to latch on time since the last
  successful renewal compared with the lease expiry, not on the number of failed calls.

### S3. Medium: worktree environments that fail mid-prepare or mid-remove can never be cleaned up

- **Where:** `src/skm/adapters/git/environments/worktree.py:186-197` (prepare replay), `:354-383`
  (`_remove_mount`, `remove`), and `src/skm/modules/execution/host/clean_environments.py:70-75`.
- **What:**
  - A crash between `state: "preparing"` and `"ready"` leaves a marker that `prepare` refuses ("incomplete prepare
    requires reconciliation"). `remove` also refuses it, because it requires `state == "ready"`. No code path
    reconciles a `preparing` worktree marker.
  - `remove` is not idempotent. Suppose `git worktree remove` succeeds and `git branch -D` then fails, or the
    process dies between the two. The mount keeps a non-null `binding` whose path no longer exists. The next
    `remove` fails in `_verify` with `CHECKOUT_MISMATCH`. If the item had been marked, `_remove_mount` would run
    `git worktree remove` again on a missing worktree and fail.
  - `clean_environments` catches these errors, skips the row and retries it forever.
- **Impact:** each such attempt leaks a worktree directory, an `.git/worktrees/<name>` entry and a
  `skm/attempt/<id>/<mount>` branch in the user's source repository. The environment row is never marked removed.
  Disk use grows, and stray branches show up in the user's repository.
- **Reproduce:** in `tests/integration/git/test_environments.py`, prepare with `safe_cleanup`. Make `git.run`
  raise on `["branch", "-D"]` and call `remove` (it raises). Restore `git.run` and call `remove` again: it raises
  `PreconditionFailed: CHECKOUT_MISMATCH: checkout filesystem binding changed`. This was checked locally on
  `10360ac31`. For the prepare half, `test_prepare_crash_keeps_partial_owned_state` already shows the stuck
  marker.
- **Suggested fix:** make removal a resumable state machine. Mark the mount `removing` before the git calls. On
  retry, treat a missing worktree, or a branch that no longer exists, as done once its identity is proven, using
  `git worktree list --porcelain` and the recorded branch and baseline. Add a reconciliation path for `preparing`
  markers: after the same cleanup proof, remove only the worktrees and branches that the marker records and git
  confirms.

### S4. Medium: `reroute_task` accepts any runtime and model, and a bad value makes the task unclaimable

- **Where:** `src/skm/modules/execution/application/_operator_control.py:62-66,53-55`,
  `_live_control.py:68-76` (`controlled_selection`), `_stage_agent_helpers.py:155-177`
  (`stage_route_available`), `_stage_preparation.py:252,399-400`.
- **What:** the command checks only that `runtime_id` and `model` are not empty and stores them as a pending
  control. During claim, `stage_route_available` applies the override and turns `CAPABILITY_UNAVAILABLE`,
  `ROUTE_UNDERSHOOT` and `ADMISSION_REFUSED` into "not available for this worker". Pending controls are cleared
  only after a step is prepared successfully, and no command deletes one. A later control can only overwrite the
  same key.
- **Impact:** a typo, a runtime that no worker offers, or a model outside `runtimes.allowed` leaves the task
  `ready` and silently never claimed by any worker. The operator sees `pending_controls: ["reroute_task"]` but
  gets no error and has no way to cancel the control.
- **Reproduce:** start a run, call `execution.reroute_task` with `runtime_id="nope"` and `model="x"` for a
  `ready` task, then run the scheduler and claims. No worker claims the task, and no error is reported to the
  caller.
- **Suggested fix:** at command time, validate the route against the run's frozen `runtimes.allowed` and the
  runtime catalog, and reject it with `CAPABILITY_UNAVAILABLE`. Add a way to clear a pending control, either a
  `clear` flag or a dedicated command. When a pinned override is unroutable for longer than a threshold, raise a
  blocking reason on the task.

### S5. Medium (product decision): ad hoc runs skip plan approval and review under the same `run.start` permission

- **Where:** `src/skm/modules/execution/application/commands/run_adhoc.py:63-110,175-179`,
  `src/skm/modules/execution/domain/workflow/adhoc.py:38-60`.
- **What:** `execution.run_adhoc` (`skm exec`, `skm pipe`) needs only `run.start`, the same permission as
  starting an approved revision. Planned runs also need a revision approved with `plan.approve`. An ad hoc task is
  created with `review_mode=SELF` and `review_rounds=0`, and the caller supplies the workflow. Only `phase_gate`
  and `plan_acceptance` stages are rejected, so `integrate` and `run_checks` stages are allowed. Policy, isolation
  and budgets still apply. Whether an `integrate` stage completes without a reviewer was not checked end to end.
- **Impact:** a principal who may start runs but not approve plans can get work integrated with no plan approval
  and no independent review. That defeats the separation between `plan.approve` and `run.start`.
- **Suggested fix:** decide whether this is intended. If it is not, either require a distinct permission for ad
  hoc runs (for example `run.adhoc`), or refuse `integrate` stages and require `ReviewMode.REQUIRED` unless the
  caller also holds `plan.approve`. Document the decision in the CLI reference.

### S6. Low: each scheduler tick locks every active run, whatever its `limit`

- **Where:** `src/skm/modules/execution/application/commands/schedule_ready_tasks.py:489-540`,
  `src/skm/adapters/postgres/execution/runs_tasks.py:115-123,275-289`.
- **What:** the tick reads all active run ids (`limit=2**31-1`), takes `FOR UPDATE SKIP LOCKED` on all of them,
  and calls `reap_expired` on each. Locks are held to the end of the transaction, which also prepares up to
  `limit` tasks. `limit` bounds only the tasks scheduled.
- **Impact:** with hundreds of active runs, every tick, which re-runs immediately when the limit is hit, holds
  row locks on all runs for the full transaction. Operator commands that call `lock_run` without `SKIP LOCKED`
  (pause, cancel, controls) wait for it. The tick's own runtime grows linearly with the number of active runs.
- **Suggested fix:** page through runs in bounded batches, one transaction per batch, with a cursor. Lock and reap
  only the batch.

### S7. Low: idempotency for working-tree reviews scans every stored patch in the project

- **Where:** `src/skm/modules/execution/host/request_review.py:53-76`.
- **What:** to find an earlier upload of the same patch, the host pages through `ListFiles(origin="patch")` for the
  whole project, 200 rows per page, compares titles on the client, and fetches the match.
- **Impact:** a working-tree review costs O(number of past patches) round trips and grows without bound over
  the project's life.
- **Suggested fix:** dispatch `AddFile` directly with the deterministic idempotency key `add_key`, which already
  deduplicates, or add a server-side filter by title or source reference.

### S8. Medium: any non-inspectable process of the same user started after an attempt blocks its worktree cleanup

- **Where:** `src/skm/bootstrap/local_cleanup.py::_containment_empty`, the `PermissionError` branch.
- **What:** to prove that nothing still runs inside a discarded worktree, cleanup reads `/proc/<pid>/cwd`
  and `/proc/<pid>/fd` of every process of the same uid. When that read is refused, it returns "not empty"
  if the process started later than one second before the attempt. Processes refuse it whenever they are
  non-dumpable, which is routine and unrelated to SKM: `ssh-agent` and `gpg-agent` call
  `prctl(PR_SET_DUMPABLE, 0)`, and so do processes that changed credentials. The check does not look at
  where such a process runs, only when it started.
- **Reproduction:** with an attempt `started_at` 30 s ago and an empty target directory,
  `_containment_empty(target, state, attempt)` returns `True`; start `ssh-agent -D -a /tmp/a.sock` and it
  returns `False`; stop the agent and it returns `True` again. On a shared host the same branch fires on
  short-lived processes of other users of the account, which is also why
  `tests/unit/entrypoints/cli/test_local_clean.py::test_clean_worktrees_plans_real_git_removal_and_marks_only_terminal_attempts`
  is flaky (finding 4): the extra skip was logged for a transient `php8.4` process of another job.
- **Impact:** `skm local clean --worktrees` reports `containment unconfirmed` for every attempt older than
  the newest such process, so on a workstation where an agent started during the retention window the
  worktrees are never removed and disk use grows without bound. The operator gets no hint of which process
  blocks.
- **Suggested fix:** keep failing closed for processes SKM could have launched, but decide that from
  launch evidence the worker already records (ownership facts, cgroup or process-group of the step) rather
  than from start time alone; at minimum, report the blocking pid and command name in the skip reason so
  the operator can act.

### S9. Interrupted backups and restores

The console unwinds on SIGTERM and exits 143. A failed backup removes its own partial archive.
Restore serializes attempts for the requested database using a PostgreSQL advisory lock.
An unfinished restore is eligible for automatic removal only when the server address and catalog OID match the journal and the database's control row matches the attempt ID and state directory. A completed profile, an active connection, or an unproven catalog
prevents removal. An uncatchable kill between database creation and the first ownership commit can
therefore require operator inspection. Old journals without catalog identity require manual inspection. New staging records contain no credentials.

### S10. Re-registering a host

Registration checks the caller before looking up the recorded host. Reuse requires instance-level
`host.manage`. The default name comes from the recorded host, then the bootstrap profile, then the OS.
Concurrent CLI registrations on one machine serialize the pointer update. Incompatible platform overrides
are refused when reusing a host.

### S11. Diagnosing checkout markers

Doctor parses the full marker and compares the workspace, project, repository, mount and available
instance identity. An invalid or absent marker is an error when strict enforcement is enabled.

### S12. Hook checks

The daemon caches successful Git observations for three seconds on plain checkouts and validates
checkout trust on every cache hit. The Claude version probe caches success for sixty seconds in private
runtime state. Comparison includes the executable's change time.

### S13. Integration removal

A new apply records the original file state, including files adopted from the checkout. Removal keeps
pre-existing files and user content, including TOML comments. It prunes empty directories carrying a
matching creation tag. Directories without that proof, including filesystems without user extended
attributes, are preserved.
