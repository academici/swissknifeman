# academici

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> Local development toolset with Claude Code, Codex, Cursor and Grok.
> Ecosystem umbrella monorepository **academici**: skills, projections for clients,
> task tools and shared memory/graph - with explicit boundaries of provider support.

**What does this give to the developer:** you can connect the necessary skills and projections of the client to the project;
Task and long workflow are called only for tasks that benefit from them. Matrix below
shows where client capabilities are native, customized, or unavailable.

👉 **[Get started](docs/getting-started.md)** — shortcut to the first task and scale selection
process. Details Claude Code — in [developer's runbook](docs/develop.md).

## Features

<!-- BEGIN GENERATED PROVIDER CAPABILITIES -->
### Provider support (generated)

Single manifest: contract `1.0.0`, catalog `1.0.0`, canonical SHA-256 `484277fb69ea46e280a194b67e9edc0c96ea373d7380a1ee435b381113bf1db7`. Manifest (`packages/aicore/configs/provider-capabilities.json`) — source of truth, hand-edited, no generator: `root.generated-artifacts` does not apply to it. Details and operations: [provider support](docs/provider-support.md).

| Capability | Claude Code | Codex | Cursor | Grok |
|:--|:--:|:--:|:--:|:--:|
| `agent-packs.lifecycle` | adapted | adapted | adapted | adapted |
| `agents.catalog` | adapted | adapted | adapted | adapted |
| `analytics.legacy-migration` | adapted | unsupported | unsupported | unsupported |
| `analytics.normalized-events` | adapted | adapted | adapted | adapted |
| `analytics.run-report` | adapted | adapted | adapted | adapted |
| `command.external-research` | adapted | adapted | adapted | adapted |
| `command.filesystem-read` | native | native | native | native |
| `command.filesystem-write` | native | native | native | native |
| `command.git-read` | native | native | native | native |
| `command.git-write` | native | native | native | native |
| `command.subagents` | native | native | native | native |
| `command.workflow-carrier` | native | adapted | adapted | adapted |
| `context.observer` | unsupported | native | adapted | adapted |
| `context.output-style` | native | unsupported | unsupported | unsupported |
| `context.plans-directory` | native | unsupported | unsupported | unsupported |
| `doctor.environment` | adapted | adapted | adapted | adapted |
| `doctor.provider` | adapted | adapted | adapted | adapted |
| `instructions.project` | native | native | native | native |
| `lifecycle.auto-approval` | adapted | native | adapted | adapted |
| `lifecycle.changelog-gate` | adapted | adapted | adapted | adapted |
| `lifecycle.command-log` | adapted | adapted | adapted | adapted |
| `lifecycle.daemon-safety` | adapted | adapted | adapted | adapted |
| `lifecycle.git-guardrails` | unsupported | adapted | adapted | adapted |
| `lifecycle.memory` | adapted | adapted | adapted | adapted |
| `lifecycle.notification` | adapted | unsupported | unsupported | unsupported |
| `lifecycle.pack-guard` | adapted | adapted | adapted | adapted |
| `lifecycle.plan-guard` | adapted | adapted | adapted | adapted |
| `lifecycle.plan-regen` | adapted | unsupported | unsupported | unsupported |
| `lifecycle.review-gate` | adapted | adapted | adapted | adapted |
| `lifecycle.router` | adapted | adapted | adapted | adapted |
| `lifecycle.run-report` | adapted | adapted | adapted | adapted |
| `lifecycle.tool-telemetry` | unsupported | adapted | adapted | adapted |
| `mcp.catalog` | adapted | adapted | native | native |
| `security.safe-dirs` | adapted | adapted | adapted | adapted |
| `settings.audit` | adapted | adapted | adapted | adapted |
| `settings.permissions` | adapted | adapted | adapted | adapted |
| `skills.repository` | native | native | native | native |
| `workflows.status` | adapted | unsupported | unsupported | unsupported |

Unsupported reasons legend: `not implemented` (adapter/binding not shipped), `API-capped` (provider has no suitable project-scoped API), `not applicable` (intent has no provider object to migrate/read).
<!-- END GENERATED PROVIDER CAPABILITIES -->

| What | Briefly |
|:--|:--|
| **🔌 Plugins with skills** | Single marketplace Claude Code (skill buckets). Curated **CORE** (8 skills ≈ 480 resident tokens) is distributed to each project; the rest depends on the type of project. Two channels: `connect` (marketplace, auto update) and `vendor` (physical. copies for giving out) |
| **🎭 Roles and workflow** | `agent-packs` — versionable subagent bundles + workflow + hooks: stack packs (Laravel/Node/Python/Flutter) and role-packs (tech-lead/CTO/founder/maintainer). **dev-loop** drives vertical slices through risk-adaptive **review-gate** (Haiku→Sonnet→Opus by risk) |
| **📋 Task management** | Plugin `planner`: Claude and Grok `/planner:design\|dev\|review\|research\|fix` plus `/planner:plan-design\|plan-run\|plan-close\|plan-audit`, Codex `$ planner:*`, Cursor `planner:*`. Grok qualifies every planner command with the `planner:` prefix |
| **🪙 Token levers** | Flow discipline: ladder `context-economy` (trim CLAUDE.md to ~92%, routing models up to ~75%, audit MCP, selective-input 5–50×), concise conclusion (`compact-responses`, output-style `lean`), **PAO** for PHP (test output → ~20 tokens JSON) |
| **🧠 Memory and graph** | Hub **mAInd**: shared ecosystem memory (agentmemory-daemon, isolation by namespace) + code graph (Serena, navigate by symbols instead of reading files) + topology between projects. Observability - `maind analyze`/`verify`/`health` |
| **📈 Analytics and training** | Capturing a run with a hook `run-report` → post-run analysis `maind analyze` (verdict GREEN/ATTENTION/RED + memory usage metrics/column). Package **`analyst`** (P1 MVP): `analyst digest` deterministically extracts candidate lessons from a run → `review`/`promote` with **man in the gate** (auto-record disabled) → curated comes to mind mAInd. There is a cross-project aggregator (`scan`) and confidence-life cycle (`recompute`, Beta/decay + numeric state-machine) |
| **⚙️ Environment** | `harness` configures Claude Code, Codex, Cursor and Grok: permissions, MCP and hooks. Grok everyday profile is `workspace-contained` (`--permission-mode acceptEdits`); `trusted-full-access` is only the swissknifeman self-host |
| **🔎 RAG-discipline** | Verification of external facts before committing: staircase context7 → perplexity-web → WebSearch (skills `verify-claims`, `query-craft`, `mcp-advisor`) |

## Packages

| Package | Role | CLI |
|:--|:--|:--|
| [`packages/skiller`](packages/skiller/) | registry AI-skills - distributes skills to projects (connect/vendor) | `skiller` (alias `swissknifeman`) |
| [`packages/harness`](packages/harness/) | environment for Claude Code, Codex, Cursor and Grok (permissions, MCP, hooks, agent-packs) | `harness` |
| [`packages/maind`](packages/maind/) | hub of memory, graph and ecosystem coordination (MCP-bus) | `maind` |
| [`packages/analyst`](packages/analyst/) | continuous learning: capturing lessons from runs, man-gate, provenance | `analyst` |
| [`packages/planner`](packages/planner/) | task intent commands (`/planner:*`, `$ planner:*`, Cursor `planner:*`) | plugins Claude Code, Codex and Grok |

General foundation - package [`aicore`](packages/aicore/) (stdlib-only: `util`, `provider`, `artifacts`, `usage`).

## Installation

Requirements: `python3` 3.9+, `git`, `bash` 4+; recommended `~/.local/bin` on `PATH`, `jq`, `node` 18+, `uvx`, `bubblewrap` + `socat`
(sandbox) and one agent client. Check them first with the read-only `scripts/check-env.sh` (full table and the Ubuntu 24.04 sandbox
setup: [Get started](docs/getting-started.md#requirements)).

```bash
scripts/check-env.sh          # read-only: lists what is missing and how to install it
./install.sh                  # every module: profile full (CLI + router + Codex core/planner + Grok planner plugin)
./bin/swissknifeman install --profile minimal --dry-run   # look first; profiles: minimal, standard (default), full
swissknifeman doctor          # read-only checks of every module
```

Profiles are data in `configs/install-profiles.json`; see [install profiles](docs/install-profiles.md). `install.sh` is
a wrapper over `swissknifeman install --profile full` and delegates batch post-configuration to their own installers,
puts a symlink `swissknifeman` → root router, connects the Codex marketplace
with `core`/`planner`, and installs the Grok plugins `packages/planner` and
`prefix-hold` (`grok plugin install … --trust`). planner commands are `/planner:*`.
Grok does not install marketplace `core`: that entry's source is the
repository root. Opt-out: `--no-codex-plugins`, `--no-grok-plugins`. A new Grok
session picks up the commands. The script is once per machine: a project still
opts in with `providers.selection.grok.enabled`, then `maind sync --project <id>`
and `harness hooks --provider grok`.

> `.mcp.json` of this repo is machine specific (absolute paths to `maind`) and does not commit -
> template [`.mcp.json.example`](.mcp.json.example), generates the real file/updates `maind` (sync/deploy).

## CLI

```bash
swissknifeman <group> …       # root router: skills→skiller, env→harness, maind→maind, analyst→analyst; + setup, doctor
swissknifeman setup <project> # cross-batch onboarding (skills+environment+memory+graph) → maind onboard
skiller <cmd>                 # skill registry (connect, vendor, integrate, registry, …) — alias swissknifeman
harness <cmd>                 # environment (permissions, mcp, hooks, agent-packs, doctor), including Grok
maind <cmd>                   # hub (memory, graph, onboard, deploy, sync, health, analyze, verify, …)
analyst <cmd>                 # continuous learning (digest, scan, review, promote, deprecate, doctor)
```

## Plugins Claude Code

One marketplace (`.claude-plugin/marketplace.json`, name `swissknifeman` = umbrella) declares everything
repo plugins: skill buckets, curated `core`, `planner`, `skm`, `generate-skill`, `maind` and `analyst`.
Generated `skiller registry`. Plugin `maind` — commands only `/maind:*` (MCP-hub tools
come per-project server `maind` from `.mcp.json` project, not from the plugin).

## Documentation

- **[Get started](docs/getting-started.md)** — installation, first task and path selection.
- **[Developer's runbook](docs/develop.md)** — how to conduct the development process with Claude Code.
- [Ecosystem Overview](docs/index.md) · [control-surface projects](docs/control-surface.md) ·
  [source routing/tasks](docs/routing.md) · [references](docs/reference.md).
- Packages: [skills](packages/skiller/docs/) · [environment](packages/harness/docs/) ·
  [memory and graph](packages/maind/docs/) · [continuous learning](packages/analyst/README.md).

## Development

Tests/validation - by package:

```bash
bash packages/skiller/scripts/validate.sh
bash packages/harness/scripts/validate.sh
bash packages/maind/scripts/validate.sh
```

Details in `CLAUDE.md` root and each package (+ `CONTRIBUTING.md`). Commits - Conventional Commits in Russian.
