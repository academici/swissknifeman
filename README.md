# academici

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> Local development toolset with Claude Code, Codex and Cursor.
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

Single manifest: contract `1.0.0`, catalog `1.0.0`, canonical SHA-256 `3c2bf3a8b2658034e415cf1d64a46718517d841506c8088572230b93cebf1370`. Manifest (`configs/provider-capabilities.json`) — source of truth, hand-edited, no generator: `root.generated-artifacts` does not apply to it. Details and operations: [provider support](docs/provider-support.md).

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
| `lifecycle.review-gate` | adapted | adapted | adapted | adapted |
| `lifecycle.router` | adapted | adapted | adapted | adapted |
| `lifecycle.run-report` | adapted | adapted | adapted | adapted |
| `lifecycle.terminal-admission` | adapted | adapted | adapted | adapted |
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
| **📋 Task management** | Plugin `task` (default-on): `/task:design\|dev\|review\|research\|fix` — each **kicks the model + effort + profile** under intent, without manual switching |
| **🪙 Token levers** | Flow discipline: ladder `context-economy` (trim CLAUDE.md to ~92%, routing models up to ~75%, audit MCP, selective-input 5–50×), concise conclusion (`compact-responses`, output-style `lean`), **PAO** for PHP (test output → ~20 tokens JSON) |
| **🧠 Memory and graph** | Hub **mAInd**: shared ecosystem memory (agentmemory-daemon, isolation by namespace) + code graph (Serena, navigate by symbols instead of reading files) + topology between projects. Observability - `maind analyze`/`verify`/`health` |
| **📈 Analytics and training** | Capturing a run with a hook `run-report` → post-run analysis `maind analyze` (verdict GREEN/ATTENTION/RED + memory usage metrics/column). Package **`analyst`** (P1 MVP): `analyst digest` deterministically extracts candidate lessons from a run → `review`/`promote` with **man in the gate** (auto-record disabled) → curated comes to mind mAInd. There is a cross-project aggregator (`scan`) and confidence-life cycle (`recompute`, Beta/decay + numeric state-machine) |
| **⚙️ Environment** | `harness` configures Claude Code: presets permissions on stacks, MCP-servers, hooks (auto-approve/memory/notify/run-report) |
| **🔎 RAG-discipline** | Verification of external facts before committing: staircase context7 → perplexity-web → WebSearch (skills `verify-claims`, `query-craft`, `mcp-advisor`) |

## Packages

| Package | Role | CLI |
|:--|:--|:--|
| [`packages/skiller`](packages/skiller/) | registry AI-skills - distributes skills to projects (connect/vendor) | `skiller` (alias `swissknifeman`) |
| [`packages/harness`](packages/harness/) | environment settings Claude Code (permissions, MCP, hooks, agent-packs) | `harness` |
| [`packages/maind`](packages/maind/) | hub of memory, graph and ecosystem coordination (MCP-bus) | `maind` |
| [`packages/analyst`](packages/analyst/) | continuous learning: capturing lessons from runs, man-gate, provenance | `analyst` |
| [`packages/task`](packages/task/) | task intent command plugin (`/task:*`, `$ task:*`) | plugins Claude Code and Codex |

General foundation - package [`core`](core/) (stdlib-only: `Env`, output, slug).

## Installation

```bash
./install.sh                  # CLI + router + basic Codex-plugins core/task (if Codex installed)
```

`install.sh` delegates batch post-configuration to their own installers,
puts a symlink `swissknifeman` → root router and connects to Codex local
marketplace with basic `core`/`task`. Opt-out: `--no-codex-plugins`.

> `.mcp.json` of this repo is machine specific (absolute paths to `maind`) and does not commit -
> template [`.mcp.json.example`](.mcp.json.example), generates the real file/updates `maind` (sync/deploy).

## CLI

```bash
swissknifeman <group> …       # root router: skills→skiller, env→harness, maind→maind, analyst→analyst; + setup, doctor
swissknifeman setup <project> # cross-batch onboarding (skills+environment+memory+graph) → maind onboard
skiller <cmd>                 # skill registry (connect, vendor, integrate, registry, …) — alias swissknifeman
harness <cmd>                 # environment Claude Code (permissions, mcp, hooks, agent-packs, doctor)
maind <cmd>                   # hub (memory, graph, onboard, deploy, sync, health, analyze, verify, …)
analyst <cmd>                 # continuous learning (digest, scan, review, promote, deprecate, doctor)
```

## Plugins Claude Code

One marketplace (`.claude-plugin/marketplace.json`, name `swissknifeman` = umbrella) declares everything
repo plugins: skill buckets, curated `core`, `task`, `skm`, `generate-skill`, `maind` and `analyst`.
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
