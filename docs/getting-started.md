# Get started

SwissKnifeMan does not require a plan for each task. Choose a shortcut based on the scale of work;
`planner` and full onboarding are enabled by an explicit solution.

## Check installation

From a cloned root SwissKnifeMan:

```bash
./install.sh
swissknifeman doctor
```

`doctor` checks the tools on the machine. See the status of a specific connected project
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
