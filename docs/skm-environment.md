# SKM environment variables and the shell profile

Installing Swiss Knife Man on a machine exports three variables from the shell profile, so every shell, the agent's Bash
and the project launcher see the same machine. A project needs no knowledge of where the machine keeps things: it reads the
variables and runs everything through its launcher.

| Variable | Holds | Default when unset |
| --- | --- | --- |
| `SKM_HOME` | the machine home (`config/`, `state/`, `cache/`, `workspaces/`, module data) | `~/.local/share/swissknifeman` |
| `SKM_WORKSPACES` | the folder of the workspaces (one git repository each) | `<machine home>/workspaces` |
| `SKM_WORKSPACE` | the code of the active workspace | the only workspace of the machine |

The names are fixed in one table, `aicore.state.envtable` (`packages/aicore/lib/aicore/state/envtable.py`). The installers, the
doctors and the plugin environment allowlist take them from it; the stdlib-only hook libraries of the harness carry copies that
`packages/harness/tests/test_skm_env_table.py` pins to the table. `SKM_WORKSPACES_ROOT` is the older name of the workspaces
folder: it is read first when set and is never exported.

## The shell snippet

`aicore shell-env install` writes one managed block into the profile of the shell in `$SHELL` (`~/.bashrc` for bash,
`~/.zshrc` for zsh; `--profile FILE` names another file):

```sh
# >>> swissknifeman environment (managed by swissknifeman: do not edit between the markers) >>>
[ -n "${SKM_HOME-}" ] || SKM_HOME=/home/me/.local/share/swissknifeman
export SKM_HOME
[ -n "${SKM_WORKSPACES-}" ] || SKM_WORKSPACES=/home/me/.local/share/swissknifeman/workspaces
export SKM_WORKSPACES
[ -n "${SKM_WORKSPACE-}" ] || SKM_WORKSPACE=axioma
export SKM_WORKSPACE
# <<< swissknifeman environment <<<
```

- **A default, not an override.** A variable already in the environment wins, so `SKM_WORKSPACE=other claude` works.
- **Idempotent.** A second run changes nothing; a changed value updates the block in place; every line outside the markers stays.
- **`aicore shell-env uninstall`** removes the block and the blank line it added (a profile that held nothing else is deleted).
  Markers that do not pair up are refused (`SHELL_PROFILE_BLOCK_BROKEN`); nothing is written then.
- **`SKM_HOME` is left out while the machine still uses the old XDG folders.** A set `SKM_HOME` marks a sandbox and switches the
  lookup of the old folders off; run `swissknifeman config migrate-home` first, the next `shell-env install` then adds it.
  `SKM_WORKSPACE` is left out while the machine has no workspace or several without a choice.
- A fish profile is not written (`SHELL_UNSUPPORTED`); export the three variables yourself.

`aicore shell-env show [--json]` prints the table, what would be exported and the state of the snippet (`absent`, `current`,
`stale`, `broken`). `maind/install.sh` and `skiller/install.sh` run `shell-env install` (and the root `install.sh` through them);
`--no-shell-env` or `SKM_NO_SHELL_ENV=1` skips it, and a failure only warns. Open a new shell after the first install.

## Doctors

`swissknifeman project doctor` reports `project.env-snippet` and `project.env-variables`; `swissknifeman workspace doctor`
reports `workspace.env-snippet` and `workspace.env-variables`; `aicore shell-env doctor` reports both under `aicore.`. The snippet
check is `ok` (current), `warn` (absent or stale: the remedy is `aicore shell-env install` and a new shell), `fail` (broken
markers) or `skip` (a shell without a snippet). The variables check warns about a variable that is not set in this shell, a
folder that does not exist and a workspace code that is not a workspace of the machine.

## What a skill or a project instruction says

Text for skills and project instructions of Swiss Knife Man (keep it short, it is read on every task):

> - Read the SKM variables instead of guessing paths: `SKM_HOME` (machine home), `SKM_WORKSPACES` (folder of the workspaces),
>   `SKM_WORKSPACE` (active workspace code). If one is empty, run `swissknifeman project doctor` and follow its remedy.
> - Run Swiss Knife Man through the project launcher: `python3 -I .swissknifeman/launcher.py <group> <args...>` from the project
>   root (`swissknifeman project init` once per checkout). The launcher passes the variables on unchanged.
> - A project does not know where its plans, tasks or configuration live: they are in the workspace
>   (`$SKM_WORKSPACES/$SKM_WORKSPACE/projects/<code>/`). Ask the launcher (`planner`, `project context`); use `plans/` and `tasks/`
>   of the checkout only when the optional links exist.
> - `$VAR` in a path of `rm`/`rmdir` is refused by the safe-dirs hook; do not route around it.

The launcher copies its environment to the hub (`os.environ.copy()` plus the `SKM_LAUNCHER_*` variables) and invents none of
the three: without them the hub falls back to the defaults of the table above.

## Tests

`packages/aicore/tests/state/test_shellenv.py` covers the table, the values, install/uninstall idempotency, a fresh interactive
`bash` that reads the profile (children see the variables, an existing value wins, a clean shell after uninstall), the
`aicore shell-env` command, both doctors' checks and the launcher with and without the variables. The installers' tests are in
`packages/skiller/tests/test_install.py` and `packages/maind/tests/test_install.py`; the workspace doctor in
`packages/workspace/tests/test_doctor.py`. The test scripts of the packages unset the three variables, so a developer's own
exports never reach a sandbox.
