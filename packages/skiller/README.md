# academici/swissknifeman

[![Tests](https://github.com/academici/swissknifeman/actions/workflows/test.yml/badge.svg)](https://github.com/academici/swissknifeman/actions/workflows/test.yml)
[![Validate](https://github.com/academici/swissknifeman/actions/workflows/validate.yml/badge.svg)](https://github.com/academici/swissknifeman/actions/workflows/validate.yml)
[![Docs](https://github.com/academici/swissknifeman/actions/workflows/docs.yml/badge.svg)](https://academici.github.io/swissknifeman/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> Universal personal registry AI-skills and snippets: one source of truth,
> installation in any project and any IDE, tracking of external sources.

**Documentation:** [academici.github.io/swissknifeman](https://academici.github.io/swissknifeman/)
(locally: `npm install && npm run docs:dev`)

## What is this package for?

Unified skill library (provider-neutral `SKILL.md` + `snippets/`) under mine
work scenarios:

1. **Documentation** — writing and maintaining technical documentation
2. **Obsidian vault** — knowledge management, notes, knowledge bases
3. **Technical specifications** — preparation of technical specifications (BRD → PRD → architecture)
4. **PHP-packages** — development open-source packages, first Laravel
5. **Large Laravel-projects** — architecture, patterns, DevOps, quality

Skills accumulate gradually: your own - from the experience of real projects (AzGuard,
botkit etc.), external - selectively from the best open sources with tracking
updates. The frame is universal: one register → installation in Claude Code, Cursor
or any other agent.

**Compatible kernel.** The registry only holds mutually compatible skills - which
lies there and does not conflict with each other. External source (for example Laravel Boost)
is checked in pairs against the kernel: necessary, complementary, version-stable and not
requiring render-source context - moved to the kernel with `upstream.json`
(first to the registry, then to projects); version-specific or conflicting -
remains with the source according to the trust policy (priority: project > source >
registry). More details - [docs/guide/index.md](docs/guide/index.md#6-compatible-kernel-conflict-policy)
and `references/laravel-boost.md`.

## Skills vs. work flow

Two layers that do not need to be mixed:

- **Skills** (`skills/`) — are utilitarian. One skill = one skill working
  **inside a specific IDE/agent** (Claude Code, Cursor). The skill contains purely
  skill and does not describe the joint behavior of different systems.
- **Workflow** ([docs/workflows/](docs/workflows/index.md)) — **intersystem
  layer**: like Perplexity → Claude → Cursor → reviews pass work to each other.
  This is a methodology, not an executable skill; she is not tied to one IDE.

TK from the work flow describes *what* build; skills - *like* do this in that IDE,
where the agent is running.

## Structure

```
skills/                    # skill = folder + SKILL.md + snippets/ (+ upstream.json for external)
├── architect/  (9)        # architecture, API, data, security
├── devops/     (6)        # Docker, CI/CD, GitOps
├── founder/    (5)        # ideas, competitor analysis, pitches
├── imported/   (12)       # external super-skills (are tracked via upstream.json)
├── operator/   (5)        # incidents, runbook, postmortem
├── oss-dev/    (6+refs)   # open-source development + language references/
├── php/        (7)        # Laravel, packages, tests, patterns
├── pm/         (8)        # BRD, PRD, roadmap, monetization
├── quality/    (4)        # code review, tests, technical debt
└── roles/      (4)        # persons: tech-lead, startup-cto, ...

profiles/                  # project type → set bucket-ov
references/                # directory of external sources (what to take, status)
adapters/                  # integration docs: claude-code, cursor, perplexity
docs/workflows/            # cross-system methodologies (Perplexity→Claude→Cursor→review)
bin/                       # CLI skiller (connect/vendor/update/status/list/registry/doctor)
scripts/                   # validate, update-upstreams, scanner
generate-skill/            # meta-skill for creating new skills
skills.json                # registry (is generated skiller registry, with provenance)
buckets.json               # metadata bucket-ov (description/category/tags)
.claude-plugin/            # marketplace.json — native marketplace Claude Code (is generated)
docs/                      # documentation (VitePress)
```

> `references/` at the root - a directory of external sources for selection;
> `skills/oss-dev/references/` — language reference-files inside bucket-a. These are different things.

## Installation

### Step 1: CLI (once per machine)

```bash
cd ~/projects/packages/swissknifeman
./install.sh        # CLI + basic Codex-plugins core/task (if Codex installed)
skiller doctor
```

Then everything is done **from the project directory** — the root is searched automatically,
the registry doesn't need to know about your projects (connection map is accumulated in
`<state>/skiller/projects.json`). Command reference: [docs/guide/cli.md](docs/guide/cli.md).

### Claude Code: plugin marketplace (recommended)

Repository - native marketplace plugins Claude Code: each bucket = plugin,
skills get namespace `<bucket>:<skill>` (for example `php:laravel-packages`).
Skills **are not copied** to the project - live in the cache Claude Code and are updated from here.

```bash
cd ~/projects/my-app
skiller connect                      # auto profile detection → settings.local.json

# Preview / explicit set / migration from old vendor
skiller connect --dry-run
skiller connect --plugins php,quality
skiller connect --cleanup-vendored
```

Plugin version = git SHA: skill edits are added to projects after
local **commit** (push is not needed) — `/plugin marketplace update swissknifeman`
or session restart. Plugin manifests (`.claude-plugin/`) are generated
`skiller registry`.

### Cursor / other agents: vendor

`skiller vendor` itself determines the type of project and copies the appropriate set of skills:

```bash
# Laravel-project (artisan+composer.json) → architect, php, devops, quality, operator
cd ~/projects/my-laravel-app
skiller vendor --agent cursor

# Obsidian vault (.obsidian/) → architect, pm, founder, operator, roles, imported
cd ~/vaults/brain && skiller vendor

# Preview without installation
skiller vendor --list

# Explicit profile / bucket-s / exceptions
skiller vendor --profile php-package
skiller vendor --buckets php,quality --exclude botkit
```

### Updating connected projects

```bash
cd ~/projects/my-app && skiller update   # current project (channel is detected by itself)
skiller update --all                     # all registered
skiller status                           # report on the current project
skiller list                             # project map
```

Reinstallation only cleans what you installed yourself (manifest
`.swissknifeman-manifest.json` in both layout modes); existing aliens
skill folders - collision error, overwriting only with `--force`.
Mode `--agent claude` (flat vendoring) is left for compatibility,
for Claude Code preferred marketplace.

A project can commit its configuration to `.swissknife.json`
(see [.swissknife.example.json](.swissknife.example.json)) — priority:
flags → `.swissknife.json` → autodetection. The file passes schema validation
(typo in key → error with hint).

### Root skill hub (generate-hub.sh)

After connecting the skills, generate them in the project «splitter» — priorities
reading sources + index of installed skills with search rules:

```bash
skiller update          # regenerates the hub if it is already in the project
./scripts/generate-hub.sh --target ~/projects/my-app   # or flag --hub y connect/vendor
```

- project **with Laravel Boost** (yes `boost.json`) → fragment is written
  `.ai/guidelines/swissknifeman-hub.md`; in CLAUDE.md/AGENTS.md will insert it himself
  Boost when `php artisan boost:update`;
- project **without Boost** → managed-block in `CLAUDE.md` between markers
  `<!-- swissknifeman:hub:start/end -->`; custom content outside of markers
  is not affected, restart is idempotent.

Installed is determined by `enabledPlugins` in `.claude/settings*.json`
(channel marketplace) and/or manifests `.swissknifeman-manifest.json`
(vendor channel). Priorities and routing table «task type → skill» —
[routing.md (umbrella)](../../docs/routing.md); compatibility policy Laravel Boost —
[docs/boost-compatibility.md](docs/boost-compatibility.md); device of a single
source of truth for skills in the project - skill `general/skills-ssot`.

## Presets permissions for Claude Code

Setting up the environment Claude Code (presets permissions, MCP-servers, hooks) **taken out
into a separate package [`harness`](../harness/README.md)**. skiller delegates there:
`connect`/`vendor`/`integrate` name `harness permissions` under the hood (`--no-permissions`
disables). Directly:

```bash
# base + stack autodetect (artisan → laravel, package.json → node, ...)
harness permissions --target ~/projects/my-laravel-app

# Explicit set / preview
harness permissions --target . --preset base,laravel,docker
harness permissions --target . --dry-run

# Global baseline (read-only) + hook-logger of all Bash-commands in ~/.claude
harness permissions --global
```

Presets: `base`, `laravel`, `php-package`, `node`, `python`, `docker`, `yolo`, `global`.
Merge in `.claude/settings.local.json` without overwriting existing rules, with backup.
Dangerous operations (`git push`, `rm -rf`, `migrate:fresh`) — via ask, secrets
(`.env`, keys, `~/.ssh`) — deny.

## Profiles

| Profile | Autodetect | Bucket-s |
|---|---|---|
| `obsidian-vault` | `.obsidian/` | architect, pm, founder, operator, roles, imported |
| `laravel-project` | `artisan` + `composer.json` | architect, php, devops, quality, operator |
| `php-package` | `composer.json` without `artisan` | oss-dev, php, quality, devops |
| `standalone` | no markers | all + generate-skill |

## Upstream-sync: tracking external skills

Skill taken from an external source contains `upstream.json` next to `SKILL.md`:

```json
{
  "schema_version": 1,
  "source": "github",
  "repo": "get-zeked/research-knowledge-super-skill",
  "strategy": "notify",
  "files": [
    { "path": "SKILL.md",
      "url": "https://raw.githubusercontent.com/.../SKILL.md",
      "sha256": "…", "fetched_at": "2026-06-11" }
  ]
}
```

- **No `upstream.json`** → self-written skill, sync-tuning does not touch him
- **`strategy: replace`** → file is mirrored as is, updates are applied automatically
- **`strategy: notify`** → local copy adapted; about upstream updates
  only reported, file not overwritten

```bash
./scripts/update-upstreams.sh --check        # report: what is outdated (exit 10 = there are changes)
./scripts/update-upstreams.sh --apply        # apply replace-updates, write sha
./scripts/update-upstreams.sh --apply --force --skill imported/research   # overwrite conflict
```

GitHub Action `upstream-sync.yml` checks all upstreams weekly and opens
PR with diff - changes from other people's repositories are included in main only after the review.

## Registry

`skills.json` is generated `skiller registry`: path, version, sha256
and provenance of each skill (`source: local|github|http`, `upstream` URL,
`fetched_at`).

```bash
skiller registry                         # rebuild the registry + manifests + graph
```

Separate mirroring in brain no longer exists: brain — normal consuming
project (`cd <brain> && skiller vendor`, next `skiller update`).

## Adding skills

- **Your skill:** folder + `SKILL.md` by `SKILL_TEMPLATE.md` (see [CONTRIBUTING.md](CONTRIBUTING.md))
- **External skill:** folder + `upstream.json` → `./scripts/update-upstreams.sh --apply --skill ...`
- **Candidate sources:** directory [references/](references/README.md) — what to take selectively and where from

## Scanner

Extracting snippets from local projects (paths in `.skills-scanner.json`):

```bash
./scripts/scan-skills.sh              # find candidates
./scripts/scan-skills.sh --extract    # anonymize in .scanner-output/
./scripts/scan-and-pr.sh              # commit + PR
```

## CI/CD

| Workflow | Purpose |
|----------|------------|
| `modules.yml` (hub) | `scripts/validate.sh` and `scripts/test.sh` of the skiller unit (Python 3.11, 3.13, 3.14), including `skiller registry --check` |
| `upstream-sync.yml` | Weekly check of upstreams → PR with diff |
| `sha256-update.yml` | `skiller registry --check` on push and PR (read-only) |
| `scanner-pr.yml` | Weekly scan → PR; on a hosted runner the local scan paths are absent (`SCAN_PATHS_ABSENT`), run `scan-and-pr.sh` locally |

## Security

Vulnerability disclosure policy and procedures - in [SECURITY.md](SECURITY.md)
(trust model of imported skills, sha256 in `upstream.json`, rule «no
secrets in snippets»).

## License

[MIT](LICENSE) © Dmitry Vostrikov. External (imported) skills retain licenses
of their sources - see. `upstream.json` next to each one.
