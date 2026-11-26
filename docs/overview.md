# How SwissKnifeMan works

SwissKnifeMan prepares a project for AI agents (Claude Code, Codex, Cursor, Grok) and runs planned work through them. The principles behind it: [Philosophy](philosophy.md).
It is one repository of modules: each does one job, reaches the others only through their commands, bridges or
events, and shares the foundation `aicore`. This page explains what each part does and how the parts meet; the pages
it links hold the reference.

## The map

```mermaid
flowchart TB
  subgraph face [The face]
    cli[swissknifeman CLI<br/>units, install, doctor, aliases]
    skm[/skm plugin<br/>skills, integrate, status, doctor/]
  end
  subgraph prepare [Prepare a project]
    skiller[skiller<br/>skill registry and delivery]
    harness[harness<br/>permissions, hooks, MCP, agent packs]
    maind[maind<br/>memory, graph, projects, onboarding]
    brain[brain<br/>Obsidian vault, notes]
  end
  subgraph work [Plan and run work]
    planner[planner<br/>plans, intent commands]
    orch[orch<br/>conductor, roles, run policies]
  end
  analyst[analyst<br/>run analytics, lessons]
  aicore[(aicore<br/>config, state, events,<br/>providers, schemas)]

  cli --> skiller & harness & maind & planner & orch
  skm --> cli
  maind -- provisioning --> skiller & harness & brain & planner
  planner <-- "bridge planner-orch" --> orch
  orch <-- "bridge orch-skiller" --> skiller
  orch <-- "bridge orch-harness" --> harness
  planner -. "planner.* events" .-> analyst & brain
  orch -. "orch.run.* events" .-> analyst
  skiller & harness & maind & brain & planner & orch & analyst --> aicore
```

| Module | The job | Start with |
| --- | --- | --- |
| [skiller](skiller/guide/) | one registry of provider-neutral skills (`SKILL.md`), delivered to a project by marketplace (`connect`) or as copies (`vendor`) | `skiller status`, `/skm:skills` |
| [harness](harness/) | the agent environment: permission presets, auto-approve modes, MCP servers, hooks, agent packs, instructions | `harness permissions`, `harness mcp` |
| [maind](maind/guide/) | the hub of the machine: shared memory, the connection graph, the project registry, onboarding and sync of projects, an MCP server | `maind onboard`, `maind status` |
| [brain](brain/guide/) | the Obsidian vault: where it is, project documents synced into it, notes written on plan events | `brain vault`, `brain doctor` |
| [planner](planner/) | plans as JSON (phases, items, decisions, checks) and the `/planner:*` intent commands (dev, fix, review, research, plan-*) | `/planner:plan-design`, `plan.py next` |
| [orch](orch/) | runs the items of a plan through narrow roles (scout, executor, reviewer, triager) with checks, review and recovery | `swissknifeman orch conduct run --plan P --items A` |
| [analyst](analyst/guide/) | reads what runs did: run reports, metrics, lessons a person may promote to memory or skills | `analyst runs`, `analyst digest` |
| aicore | the foundation every module imports: layered configuration, state locations, events, provider catalogs, schemas, release attestation | `swissknifeman config explain MODULE` |

## A project from zero

```mermaid
sequenceDiagram
  participant P as Person
  participant U as swissknifeman / skm
  participant M as maind
  participant S as skiller
  participant H as harness
  participant B as brain
  P->>U: ./install.sh (profile minimal | standard | full)
  U-->>P: CLIs on PATH (swissknifeman, skiller, harness, maind, ...)
  P->>M: maind onboard PROJECT
  M->>M: register the project (type, memory namespaces)
  M->>S: skiller integrate: skills (connect or vendor), hooks, permissions
  S->>H: harness presets: permissions, hooks, MCP
  M->>M: deploy memory + graph, seed the graph
  M->>B: vault of the project (brain vault --json)
  M-->>P: onboarded (a missing partner is a skipped step with a warning)
  P->>U: /skm:status, /skm:doctor
```

`install.sh` installs the CLIs of a profile ([install profiles](install-profiles.md)). `maind onboard` chains the
steps through the partner commands, each one standalone-safe; `/skm:integrate` is the integration wizard inside the
agent. Every writer is merge-only and keeps backups; `swissknifeman doctor` checks every module read-only and prints
the remediation.

## Skills: one canon, two channels

```mermaid
flowchart LR
  canon[packages/skiller/skills/<br/>bucket/name/SKILL.md] --> registry[skiller registry<br/>skills.json, plugin manifests,<br/>marketplace, Codex adapters]
  registry --> connect{channel}
  connect -- "connect (Claude Code)" --> market[marketplace plugins<br/>enabledPlugins in .claude/settings.local.json]
  connect -- "vendor (Cursor, others, offline)" --> copies[managed copies<br/>.claude/skills, .agents/skills<br/>skills-lock.json]
  upstream[upstream.json<br/>external skills] -- "update-upstreams.sh<br/>weekly PR with diff" --> canon
```

A skill is written once, in English, in its module (shared skills in skiller, module skills in their module).
`skiller registry` regenerates every projection and CI proves they are current (`skiller registry --check`). The
channel is always the person's choice: `connect` keeps skills live in the marketplace, `vendor` copies them into the
repository for people without swissknifeman. The curated `core` set is delivered by default; `--no-core` opts out;
`skiller budget` reports what each set costs in context tokens.

## Planned work

```mermaid
flowchart LR
  idea([request]) --> research[/planner:research/]
  research --> design[/planner:plan-design/<br/>phases, items, checks, write sets/]
  idea --> design
  design --> check[plan.py check<br/>0 errors]
  check --> run{who runs it}
  run -- "agent session" --> planrun[/planner:plan-run/]
  run -- "conductor" --> conduct[orch conduct run<br/>--plan P --items A B C]
  planrun --> close[/planner:plan-close/]
  conduct --> close
  close --> archive[(plans/archive)]
  close -. "reopen / amend" .-> design
```

A plan is JSON under `plans/<ID>/` (`plan.json`, phases, items, decisions; Markdown views are generated, never read by
agents). An item is ready when it has a goal, scope, a write set, acceptance checks and a route. The owner runs it in a
session (`/planner:plan-run`) or hands a batch to the conductor. Ordinary work needs no plan: `/planner:dev` and
`/planner:fix` run directly. See [methodology](planner/methodology.md).

## The conductor in one picture

```mermaid
flowchart LR
  claim[claim] --> brief[brief] --> prepare[prepare] --> scout[scout]
  scout --> exec[executor]
  exec --> checks[checks]
  checks -- red --> exec
  checks -- green --> review{review?}
  review -- yes --> rv[review → triage]
  rv -- "confirmed Major+" --> exec
  rv -- clean --> register[register]
  review -- no --> register
  register --> commit[commit]
```

The conductor branches only on exit codes, closed role results and limits; it never reads the plan itself. Limits
are targets that print beacons, not walls; a stop is resumable and keeps every closed step. The full set of diagrams
(item lifecycle, correction rounds, the review decision, batches, questions, provider failures, recovery, settings,
debug mode) is on [How work flows](orch/flows.md); the reference is [Conductor](orch/conductor.md).

## Events: who hears what

```mermaid
flowchart LR
  planner -- "planner.plan.created/closed<br/>planner.item.started/finished<br/>planner.phase.closed" --> journal[(aicore event journal<br/>state/events)]
  orch -- "orch.run.started<br/>orch.run.stage.finished ..." --> journal
  journal --> analyst[analyst: run outcomes, metrics]
  journal --> brain[brain: a note per closed plan]
  brain -- "brain.note.created" --> journal
```

A source never knows its subscribers. Event data follow `event-data/v1`, are redacted before they are written, and
carry the digests of the configuration and run options, so two runs can be compared.

## Settings: one model for every module

```mermaid
flowchart LR
  d[schema defaults] --> m[machine<br/>~/.config/swissknifeman/config.toml]
  m --> p[project<br/>.swissknifeman/config.toml]
  p --> e[environment<br/>SKM_MODULE_KEY]
  e --> i[--config FILE]
  i --> f[flags]
  f --> v([effective value])
```

Each module has a table (`[orch]`, `[planner]`, `[skiller]`, `[maind]` ...) with a schema and a generated
`config.example.toml`. The most specific layer wins; `swissknifeman config explain MODULE KEY` names the layer, file
and line. Some keys are machine-only (a project cannot set its own trust), and the run options of orch may only
tighten isolation below the conductor configuration. State lives in standard places (`~/.local/state/swissknifeman`,
`<project>/.swissknifeman`), never in scattered dot-files.

## Releases

```mermaid
flowchart LR
  change[change] --> unreleased[CHANGELOG Unreleased]
  unreleased --> guard[version-guard.py status<br/>bump changed units]
  guard --> reg[skiller registry]
  reg --> attest[skiller attest --release vX.Y.Z<br/>releases/vX.Y.Z.json]
  attest --> verify[verify-tag.py vX.Y.Z]
  verify --> tag[tag on main]
  tag --> ci[release-tag job:<br/>on main, CHANGELOG, manifest]
  ci --> deliver[skiller deliver --release vX.Y.Z --all]
```

Every installable unit has its own version; provider caches are keyed by it, so changed bytes need a bump. The
attestation records the SHA-256 of every delivered file per provider; a unit whose bytes changed under the same version
is `RELEASE_IMMUTABLE_TUPLE`. Workflows pin actions by commit SHA and never push to `main`; see
[SECURITY.md](https://github.com/academici/swissknifeman/blob/main/SECURITY.md).

## Where to go next

- New here: [Getting started](getting-started.md), then [Install profiles](install-profiles.md).
- Running work with agents: [orch quickstart](orch/quickstart.md) and [How work flows](orch/flows.md).
- How the modules are divided and why: [Architecture](architecture/) and its [decisions](architecture/decisions/README.md).
- What works today and what does not: [Status](status.md).
