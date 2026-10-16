# Control-surface project (4 layer)

Project tools in the ecosystem are **four independent layers**. Their condition and
controls re-synchronization **scripted control-surface**: view with one command
full inventory, pointwise re-sync any layer. Everything is machine readable (`--json`) — suitable
for both person and agent (Claude Code sees for himself drift and fixes it point by point).

## Four layers

| Layer | What is this | Source of Truth / lock | Status | Spot repair / re-sync |
|:--|:--|:--|:--|:--|
| **Skills** | knowledge (connect-plugins / vendor-copies) | `.claude/settings.local.json` (enabledPlugins) · `skills-lock.json` | `skiller status [--json]` | `skiller connect`/`sync` · `skiller update` |
| **Roles/agents** | subagents + workflow + review-gate | `.claude/agent-pack.lock.json` | `harness agent-packs doctor --target . [--json]` | `harness agent-packs render/upgrade` · `maind sync --only agent-pack` |
| **MCP** | tools (memory/code graph/…) | `.mcp.json` | `maind health --project <id>` | `maind sync --only mcp` · `maind deploy` |
| **Memory/graph** | general context + federation of connections | demon `:4111` · hub graphs · `.claude/memory.env.ini` | `maind verify [--json]` · `maind status` | `maind sync --only memory,graph,code-graph` · `maind start --only memory` |

> Layers **independent** (skiller / harness / maind don't know about each other); single point - umbrella
> CLI and orchestrator `maind`.

**Project-bound invocation.** Inside a project every command goes through `.swissknifeman/launcher.py`
(`python3 -I .swissknifeman/launcher.py <group> ...`): a transport, not a fifth layer. It binds the project root and
hands over to the installed `swissknifeman`; `swissknifeman project init|sync|verify|context|doctor` manage it. See
[project-launcher.md](project-launcher.md).

## Checking a project with one command

```bash
swissknifeman status <project-id>        # single 4-layer project inventory
swissknifeman status --all               # entire fleet (per line per project)
swissknifeman status --all --json        # machine readable (for agent/panels)
```

Output (per line per project): `status · mcp[a/m/c] · trust · skills=N · packs=N · scope` —
plus **drift→fix tips** (`⚠ layer: problem → repair command`). `<project-id>` facades in
`maind projects status --project <id>`; bare `swissknifeman status` (or `--target`) — back-compat
in `skiller status` (skills of the current project).

```
Projects (1) — layers: mcp[a/m/c] · skills · packs(roles) · trust:
  connected   agelto   mcp[-mc] trust· skills=42  packs=1  project:agelto
      ⚠ agent-pack: profile is waiting for packs backend-laravel — not installed → maind sync --only agent-pack --project agelto
```

B `--json` each project carries `skills`, `agent_packs`, `configured` (MCP), `status` and an array
`fixes` (`{layer, issue, fix}`) — agent reads `fixes` and executes the exact command.

## Operating cycle: status → spot re-sync

1. **Status** — `swissknifeman status <id> --json` (or `--all`). Look `status` and `fixes`.
2. **Drift** — each `fixes[]` gives the exact command to the layer (not «re-configure everything»).
3. **Re-sync** — execute it; almost always this `maind sync --only <cap> --project <id>`
   (capability-granular, idempotent, `--dry-run` for preview, `--json` for parsing):

```bash
maind sync --project <id> --only mcp                 # only MCP
maind sync --project <id> --only agent-pack          # roles only/agents (render/upgrade)
maind sync --project <id> --only memory,graph        # memory only/graph
maind sync --project <id> --only mcp,graph --dry-run --json   # plan without recording
```

Provisioners `maind sync --only`: `mcp · code-graph · graph · memory · memory-hook ·
health-hook · health-doc · feature-log-hook · ecosystem-skill · agent-pack`.

## Machine readability (for agent)

| Command | What gives |
|:--|:--|
| `swissknifeman status --all --json` | entire fleet: per-project 4 layer + `fixes` |
| `maind projects status --project <id> --json` | same project, same |
| `maind projects health --all --evidence-set <file> --json` | exact-set provider/axis health by sealed redacted evidence; without repair |
| `skiller status --json --target .` | detailed skill layer (channels, profile, budget, overlap) |
| `harness doctor --settings --provider claude-code\|codex --target . --json` | provider-qualified settings audit |
| `harness agent-packs doctor --target . --json` | role layer (pack directory + installed) |
| `maind verify --json` | proof-of-life memory/column/code-graph (not «raised», a «really write») |

## Environment diagnostics (not project inventory)

`swissknifeman doctor` — fan-out for three packages (`skiller`/`harness`/`maind` doctor): health
**of the tools themselves** (PATH, registry, daemon, presets). It's about the car/installation, and
`swissknifeman status` — about **project-specific status/fleet**.

## Execution of the plan in a wave

`swissknifeman env run <PLAN-ID> <Pn>` leads ready-made `plan-run` items single phase
sequentially: first builds a queue, then stops at the first RED. Start with
`--dry-run`: it shows which items the driver will take or refuse to drive, and nothing
writes. Manual and terminal items remain with the operator; contract, journal and final verdict
are saved by ordinary owners.

## Three source layers: canonical → generated → effective

The layers above respond «what's connected». Single axis - «where did this come from and what is real
active»; it cannot be confused with layers, because they are repaired with different commands:

| Layer | What is this | Who owns | How to check (read-only) |
|:--|:--|:--|:--|
| **canonical** | handwritten source of truth: `packages/*/skills/**`, `packages/planner/commands/*.md`, package configs | person/package | normal `git diff`, review |
| **generated** | canon projections: `skills.json`, both `marketplace.json`, `adapters/**`, `.claude/skills`+`.agents/skills`, publication-locks, part of the doc pages | generator (`skiller registry`, `render-provider-commands.py`) — **cannot be adjusted by hand** | `skiller registry --check` · `python3 packages/planner/scripts/render-provider-commands.py --check --root .` |
| **effective** | what the agent actually sees in the session: active semantic identity, its provenance, collisions, hook owner, trace quality | provider runtime | `skiller doctor --effective-source [--json]` |

**Rule:** drift `generated` being repaired **regeneration of the owning command**, rather than editing
file; manual editing of the generated - a defect that will catch `--check`. Layer diagnosis
`effective` — read-only: `skiller doctor --effective-source` does not write anything (proven
comparison `git status --porcelain=v1` before and after) and prints for each diagnostician
`owner/source/status/evidence/quality/next_command` with status `ok`/`degraded`/`unknown`/`n/a`.

**Quality is printed as measured, never rounded.** Where a source is incomplete, the diagnostic prints a named `unknown` gap instead of `ok` (for example `trace-quality` while no per-project trace store exists). Details and common cases: [diagnostics skiller](/skiller/guide/troubleshooting).

One specific mechanism living entirely in the layer `generated` (twelve projections
`CLAUDE.md`/`AGENTS.md` from the general canon, two drift observations, two machine gates) —
[canon of root instructions](/harness/reference/instruction-canon). Neighboring media of the same
sort (contract diagram → data → stdlib-gate `[10/10]` in `validate.sh`) —
[declarative execution policy](/harness/reference/execution-policy).

## Full project setup

Order «give everything to the project» (all 4 layers) — operational runbook `project-tooling-runbook`
(skill) and [onboarding decision tree](/maind/guide/onboarding-decision-tree). Briefly:
onboarding to the hub → skills (channel) → **agent-packs (roles)** → MCP/Boost → memory/graph →
auto-approve → `swissknifeman status <id>` for review.
