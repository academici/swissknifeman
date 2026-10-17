# Get started

SwissKnifeMan does not require a plan for each task. Choose a shortcut based on the scale of work;
`planner` and full onboarding are enabled by an explicit solution.

## Requirements

Check the machine first: `scripts/check-env.sh` is read-only, installs nothing and prints, for every gap, the command that fixes it
(`--strict` also fails on a missing recommended item, `--json` prints `skm-env-check/v1`, `--quiet` shows only the gaps).

```bash
scripts/check-env.sh
```

| Level | Program or feature | Version | Needed for | Install (Debian/Ubuntu) |
|:--|:--|:--|:--|:--|
| required | `bash` | 4+ (macOS: any) | `install.sh`, hooks | preinstalled |
| required | `python3` | 3.9+ | every module (they use only the standard library) | `sudo apt install python3` |
| required | `git` | any (2.38+ for `workspace`) | `planner`, delivery, project steps; `workspace connect`/`clone`/`sync` need 2.38 (`WORKSPACE_GIT_TOO_OLD` otherwise) | `sudo apt install git` |
| recommended | `~/.local/bin` on `PATH` | | the `swissknifeman`, `skiller`, `maind`, `harness`, `analyst`, `brain`, `plan.py` commands | `export PATH="$HOME/.local/bin:$PATH"` in your shell profile |
| recommended | `jq` | any | Claude Code hooks (review-gate, observer) and the status line | `sudo apt install jq` |
| recommended | `node` | 18+ | the memory daemon (`maind`), building these docs | `sudo apt install nodejs` or `nvm` |
| recommended | `uvx` (from `uv`) | any | the code-graph MCP server (Serena) in a project's `.mcp.json` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| recommended | `systemctl --user` | | `maind service install` (otherwise `maind start --only memory`) | a systemd user session |
| recommended | `bubblewrap` (`bwrap`) and `socat` | | the sandbox of `orch` and of Claude Code / Codex roles ([setup](#sandbox-on-ubuntu-24-04)) | `sudo apt install bubblewrap socat` |
| recommended | one agent client | | `claude`, `codex` or `grok`: the program that reads skills and commands | see each vendor |
| optional | `php`, `composer` | | Laravel and PHP packs (`pint`) | `sudo apt install php-cli composer` |
| optional | `pnpm` | | Node projects with husky or lint | `corepack enable` |
| optional | `ruff`, `rsync` | | development of this repository (`scripts/lint.sh`, `scripts/dev-sandbox.sh`) | `pipx install ruff`, `sudo apt install rsync` |

On macOS use `brew install` with the same package names; the sandbox needs no `bubblewrap` there (the system sandbox is used).
`swissknifeman doctor` checks the same things later from inside the installed modules (`orch.sandbox`, `maind.environment`, ...);
`check-env.sh` is the one you can run before anything is installed.

### Sandbox on Ubuntu 24.04+

`bubblewrap` installed is not enough on Ubuntu 24.04 and later: `kernel.apparmor_restrict_unprivileged_userns = 1` stops `bwrap` from
creating a user namespace unless an AppArmor profile allows it, and `check-env.sh` then reports
`sandbox-namespaces: bwrap cannot start` (the error is `bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted`). Allowing it is a
change of the machine and is made by its owner:

```bash
sudo tee /etc/apparmor.d/bwrap >/dev/null <<'EOF'
abi <abi/4.0>,
include <tunables/global>

profile bwrap /usr/bin/bwrap flags=(unconfined) {
  userns,
  include if exists <local/bwrap>
}
EOF
sudo apparmor_parser -r /etc/apparmor.d/bwrap
scripts/check-env.sh --quiet        # sandbox-namespaces must be ok now
```

Without the sandbox `orch` still runs, but Codex roles are unavailable and the shell commands of Claude Code roles run under the
filesystem guard only (`instructions.sandbox: prefer`); with `require` a run stops with `SANDBOX_UNAVAILABLE`.

## Check installation

From a cloned root SwissKnifeMan:

```bash
scripts/check-env.sh                             # read-only: is everything the modules call on this machine?
./install.sh --bin-dir ~/.local/bin              # every module (profile full)
# or choose a profile; --dry-run first prints the plan and writes nothing
./bin/swissknifeman install --profile minimal --dry-run
./bin/swissknifeman install --profile standard   # the default
swissknifeman doctor
```

Profiles `minimal` (skills and plans), `standard` (adds the environment, the second brain and the orchestrator) and `full`
(adds `maind` and `analyst`) are described in [install profiles](install-profiles.md).

`doctor` runs the read-only checks that every module declares ([reference](reference/doctor.md)). See the status of a specific connected project
via `swissknifeman status <project-id>`; is a different check.

## First task in the project

Open the project in the selected agent client with its own access mode for only
reading and ask to study one section of code. For Codex CLI is, for example,
`codex -a never -s read-only` from the project directory; accessibility and meaning of the regimes of others
clients check in their settings. Request «do not write» in itself does not limit rights.
For a task with changes, first look at the work tree (`git status --short`), then give
agent purpose, boundaries and verification method. For local reversible editing, it is enough to change the code,
perform affected check and show diff. Plan and planner are not required for this.

If the project needs skills through the channel `connect` for Claude Code, being in its directory,
first look at the changes:

```bash
skiller connect --dry-run
```

`connect` — separate connection of skills, and not a condition for normal work with code. Full
onboarding with environments and services is described in [connection manual](/maind/guide/onboarding-decision-tree).

## Select work path

| Task | Action | What to save |
|:--|:--|:--|
| Local reversible edit | Work directly with the agent; perform a review of the affected behavior | Diff and check result |
| A job that is difficult to complete in one reliable pass | Explicitly call `/planner:design` or `/planner:dev` in Claude Code, `$ planner:design` or `$ planner:dev` in Codex | Plan, decisions and handoff in the repository |
| Change of public contract, data or external environment | Before application, name the boundaries, check the affected scenarios and separately resolve the issue of irreversible action | Solution, check and recovery method |

This is a choice of how things work, not new machine access modes. Real rights are given
settings and sandbox selected client; the task text does not create isolation. Availability
client capabilities are listed in [provider matrix](/provider-support).

For daily work with planner use [command overview](/planner/). Setting up multiple layers and
drift search - in [control-surface](/control-surface). Detailed runbook Claude Code —
[development with Claude Code](/develop).
