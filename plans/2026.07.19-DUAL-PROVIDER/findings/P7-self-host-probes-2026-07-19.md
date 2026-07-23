# P7.2 self-host probes — fresh D117 rerun

**Observed:** 2026-07-23
**Plan/item:** `2026.07.19-DUAL-PROVIDER` / `P7.2`
**Runtime:** `gpt-5.6-terra/high`; approval `never`; sandbox `danger-full-access`.

## Boundary

This is fresh P7.2 evidence only. No live apply, repair, rollback, package/source edit,
P7.3+, FOREMAN, fleet, tag, push or cleanup was executed. The historical P7.2 evidence
was not used as a GREEN substitute.

## Disposable-root evidence

The worktree-local public provisioner completed its temporary-root instruction matrix:

```text
./packages/maind/bin/maind sync --conformance <task-temp>/instruction-conformance.md
```

The generated report SHA-256 was
`60686d05fa8bf9830cad8a960782ce12cdcb369a44b49cd9b864db481bde453e`, matching the
P6.6 checkpointed instruction render. Its rows were GREEN for Claude-only (6 targets),
Codex-only (6 targets), and dual-provider (12 targets); dual parity was 49 common IDs and
18 provider-owned extensions. It also reports a no-op second run, managed-drift refusal plus
explicit repair with outside bytes preserved, unknown-provider refusal, and implicit full-access
refusal.

The umbrella installer was run only against an explicit task-temp `--bin-dir`; it created five
symlinks to worktree-local launchers. Claude `skiller connect --dry-run` and generic
`skiller vendor --dry-run` were exercised against task-temp projects. The disposable bin and
projects were moved to a task-local rollback capture; no repository or user-home path was used
as the rollback target.

## Live no-write preflight

Before and after SHA-256 snapshots of `.swissknife.json`,
`.swissknifeman/provider-artifacts.lock.json`, `.mcp.json`, `.codex/hooks.json`,
`.codex/hooks/lifecycle.py`, and `.claude/settings.local.json` were identical.

The explicit absolute-path Codex hook check was correctly fail-closed:

```text
./packages/harness/bin/harness hooks --target /home/vostrikov/projects/packages/swissknifeman \
  --provider codex --observer --trusted --dry-run
```

It returned `ownership-conflict → refuse (unmanaged-target)` for
`harness.codex.lifecycle.hooks` and `missing → create` for its handler; exit status was 1 and
no write occurred. `./packages/maind/bin/maind sync --project swissknifeman --dry-run --json`
reported a non-green required provider aggregate without writing. This is expected until the
sealed D108/P2 live transaction is selected and separately owner-approved; it is not an
authorization to adopt or repair either path.

## Native Codex marketplace/plugin row — RED

The documented D118 route was run with a fresh task-specific `CODEX_HOME` and `HOME`:

```text
env CODEX_HOME=<task-temp>/codex-home HOME=<task-temp>/home \
  codex plugin marketplace add /home/vostrikov/projects/packages/swissknifeman --json
env CODEX_HOME=<task-temp>/codex-home HOME=<task-temp>/home \
  codex plugin add core@swissknifeman --json
```

Both commands exited `0`. The native marketplace resolved as `swissknifeman` at the repository
root and `core@swissknifeman` installed as version `0.4.0` only at
`<task-temp>/codex-home/plugins/cache/swissknifeman/core/0.4.0`; the marketplace and plugin
response SHA-256 values were respectively
`1fdc6b6ffc59bb6c7a611b4f61b1f20f51668821a21b8a9a6c859643948bbf87` and
`305fd2c106cba0f81cf9f1867b9dfb9018cff9e568c20ae5a0edb60bc02883f6`. Repository snapshots were
identical before and after (`delta=0`). The explicit task-temp root, including its 12 Codex cache
files and snapshots, was moved intact to
`/tmp/p72-codex-rollback.Cqukos/native-codex-row`; no live rollback was attempted.

The host Codex snapshot was not identical (`delta=1`), so this row is `RED` under P7.2 and D118.
The observed paths were host-session/log SQLite state and the active host-session JSONL:
`~/.codex/{logs_2.sqlite-shm,logs_2.sqlite-wal,state_5.sqlite,state_5.sqlite-shm,state_5.sqlite-wal}`
and `~/.codex/sessions/2026/07/23/rollout-2026-07-23T06-57-09-019f8d1e-bda2-7081-b38c-c554d8f73910.jsonl`
(plus the concurrent session JSONL recorded in the SHA comparison). The evidence does not assign
those host writes to the isolated plugin commands, but P7.2's strict zero-delta rule does not
permit an attribution exception or host-state fallback.

Consequently the isolated matrix and rollback rehearsal cannot be declared GREEN, no exact live
path/action inventory was derived, and the post-isolated Approval Owner D# request was not
reached. P7.2 remains in progress; the owning native Codex/session-state isolation surface needs
a plan-design decision before the row can be rerun.

## D120 ordinary authenticated native proof — GREEN carrier acceptance

**Observed:** 2026-07-23

**Runtime:** `gpt-5.6-terra/high`; approval `never`; sandbox `danger-full-access`.
**Authority:** D120 is the Owner-authorized narrow replacement for the D119 carrier only. It
rejects the temporary `HOME`/`CODEX_HOME`/`CODEX_SQLITE_HOME` plus automation-credential
clean room and uses this ordinary authenticated `NEW SESSION`. Frozen provider semantics and
the live apply/repair/rollback gate are unchanged.

The host-authenticated native commands both exited `0`:

```text
codex plugin marketplace add /home/vostrikov/projects/packages/swissknifeman --json
codex plugin add core@swissknifeman --json
```

The marketplace response was `alreadyAdded: true`. The plugin response identified
`core@swissknifeman`, version `0.4.0`, at
`/home/vostrikov/.codex/plugins/cache/swissknifeman/core/0.4.0`. This is an idempotent native
marketplace/plugin proof; no plugin was removed, no credential value was printed or persisted,
and no repository/live provider apply, repair or rollback was invoked.

An explicit before/after metadata snapshot of `/home/vostrikov/.codex` (excluding the contents
of `auth.json`) and `git status --porcelain=v1` found repository delta `0`. It found no added or
removed host files and 13 metadata changes, classified as follows:

| Class | Count | Paths / meaning |
|:--|--:|:--|
| Plugin/install state | 11 | `plugins/cache/swissknifeman/core/0.4.0/{.codex-plugin/plugin.json,publication-lock.json,skills/**/SKILL.md}` — native cache refresh for the proven plugin |
| Marketplace/config state | 1 | `config.toml` — ordinary marketplace configuration state |
| Active-session runtime state | 1 | `logs_2.sqlite-wal` — concurrent Codex runtime state |

No active-session JSONL file changed during this short snapshot interval. JSONL and
SQLite/WAL files remain separately observable active-session runtime state; they are not
described as plugin leakage and were not excluded from the snapshot. The preflight lifecycle
dry-run still returned `ownership-conflict → refuse (unmanaged-target)` for
`harness.codex.lifecycle.hooks` (exit `1`); it is an environmental known deviation, recorded
without repair.

**Native-row verdict:** GREEN under D120's ordinary-session acceptance boundary. The earlier
D118/D119 clean-room RED history remains preserved. P7.2 itself remains `🟡`: the exact live
path/action Approval Owner D# is still required before any live mutation.
