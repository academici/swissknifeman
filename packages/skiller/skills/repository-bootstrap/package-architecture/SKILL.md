---
name: package-architecture
bucket: repository-bootstrap
version: 0.1.0
description: "Full map of the swissknifeman package: distribution channels, CLI, scripts, configs, generated artifacts and what regenerates them. Activate at the start of any task in this repository touching skills/, bin/, scripts/, configs/, profiles/, the registry, or manifests."
risk: read
persona: oss-dev
tags: [skiller, architecture, distribution, root-bootstrap]
requires: []
produces_for: []
outputs: [chat]
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# swissknifeman package architecture

Internal skill (not exported). Facts only — the package map. Procedures: creating skills →
[skill-authoring], closing out changes → [release-discipline], documentation →
[docs-maintenance].

[skill-authoring]: ../skill-authoring/SKILL.md
[release-discipline]: ../release-discipline/SKILL.md
[docs-maintenance]: ../docs-maintenance/SKILL.md

## When to activate

- At the start of any non-trivial task in this repository.
- Before changing any script, config, or schema.
- When answering "how does the package work" questions.

## Distribution channels

1. **Claude Code plugin marketplace** (primary for Claude Code). Bucket = plugin:
   `skills/<bucket>/.claude-plugin/plugin.json`, root file — `.claude-plugin/marketplace.json` +
   the `generate-skill` plugin. Plugin version = git SHA: consumers see changes **only after a
   commit**. Project connection: `skiller connect` (writes `extraKnownMarketplaces` +
   `enabledPlugins."<bucket>@swissknifeman"` into the project's
   `.claude/settings(.local).json`; merge-only, an explicit `false` is not overwritten, backup in
   `.bak`).
2. **Vendor via `sync`** (physical transfer into the repo — primary for Claude outside the
   marketplace). Config `.swissknifeman/config.json` (`mode: vendor`, `include`/`buckets`/
   `exclude`) → `skiller sync` copies skills into `.claude/skills/<name>/`, writes
   `skills-lock.json` (`managed: true` + sha256) and the manifest
   `.swissknifeman-manifest.json`. **Files are committed to the project's repo** — the channel
   for projects handed to external developers without registry access (unlike `connect`, where
   the marketplace points to a local registry path). Safe removal by `managed`, foreign skills
   untouched (`--force` overwrites an occupied path). Implementation — `skillset.py`; `do_sync`
   is the entry point for `integrate`/`onboard`.
3. **Legacy vendoring** (Cursor and other agents): `skiller vendor` — copies skills into
   `.cursor/skills` / `.ai/skills` (flat layout; for `--agent claude` **deprecated** — use
   `sync` for Claude). Profiles `profiles/*.json` (laravel-project, obsidian-vault, php-package,
   standalone), precedence: flags > project's `.swissknife.json` > autodetect (`.obsidian/` /
   `artisan`+`composer.json` / `composer.json`). Transitive frontmatter `requires` resolution;
   `--exclude` beats a dependency. `.swissknifeman-manifest.json` manifest — clean reinstall
   without blind overwrites.

**Class-A private/source-only exception (P1.2, D31).** The `repository-bootstrap` bucket exists
ONLY as a source for 13 root-bootstrap identities (13 canonical `SKILL.ru.md`/`SKILL.md` pairs, 26
thin projections `.claude/skills/<id>/`+`.agents/skills/<id>/`). `build_registry` indexes it for
owner/hash lookup, but `build_publication_catalog` excludes it from ordinary Claude/Codex bucket
units, from `core` membership, and from both marketplaces; consumer vendor/connect rejects
source-only records instead of copying them into a consumer project. The sole producer of root
projections is `registry.py` → `publication.py`'s root-bootstrap renderer from
`configs/repository-bootstrap-skills.json`; `skillset.py` implements only the consumer exclusion,
never this self-host producer (see
[semantic-identity-ownership-v1](../../../../../plans/2026.07.24-AGENT-RELIABILITY/root/contracts/semantic-identity-ownership-v1.md)).

## Two project configs (don't confuse, don't merge)

- **`.swissknife.json`** — lightweight config for **connect** (+ legacy vendor):
  `project_type/buckets/exclude/presets/agent` (+ agent-framework `shape/stacks/skills_map`).
  Keys `CONFIG_KEYS` (`common.py`), validator `config.validate_config`. **bucket-granular.**
- **`.swissknifeman/config.json`** — canonical SoT for **vendor mode** (`sync`):
  `version/mode/agent/skills_path/presets/include/buckets/exclude`. Keys `SKILLSET_KEYS`
  (`skillset.py`), validator `load_skillset_config`. **skill-granular.**
- Both JSON schemas — `schema/*.json` (DX/IntelliSense via `$schema`); runtime validation is
  manual, stdlib-only; `tests/test_schema.py` and `skiller doctor` keep schema↔code in sync.
- Vendor config bootstrap — `skiller init` (from autodetect, no copies). Bridge: `sync`/`init`
  lazily materialize `.swissknifeman/config.json` from a profile/legacy config,
  non-destructively.

## Runtime skill consumption (anti-straw-man)

Skill bodies are read at runtime by **Claude Code itself**, not skiller's Python process: vendor
→ from disk `.claude/skills/<name>/SKILL.md`; connect → from the registry via the marketplace.
**No `load_skill`/`loader.py`** — skiller only copies/registers and parses frontmatter (for
metadata). So a "skill loading cache" inside skiller **has no caller**; the savings come from
Claude Code's own automatic prompt caching. Full canon — `docs/guide/skills-architecture.md`.

## CLI `bin/skiller`

Installed as a symlink into `~/.local/bin` via `./install.sh`; it derives the registry path from
its own `readlink -f` (no path config needed; repo moved → rerun install.sh). State:
`~/.swissknifeman/projects.json` (version 1, records keyed by path+channel) — populated
automatically on connect/vendor/update; disk is always the source of truth, records are replay
defaults.

Commands: `connect`, `vendor`, `integrate`, `update [--all]` (channel detection by markers, adopts
unregistered projects, repairs marketplace path drift), `init` (create
`.swissknifeman/config.json` without copying), `sync` (vendor), `lock`, `status`, `budget`
(`--first-turn` — the project's always-on first-turn footprint: skills+agents+CLAUDE.md/rules+live
hook run+MCP, target ≤7K/warn >10K; fleet — `maind doctor --context`), `list [--prune]`, `topology
[init|show]`, `registry` (maintainer), `validate`, `doctor`, `version`. Project root is searched
upward from CWD: `.swissknife.json` → `.claude/` → `.git`. Inside the registry itself,
project-commands refuse to run. Launcher `bin/skiller` allowlists commands in a `case` — a new
command must be added to both `COMMANDS` (`lib/skiller/cli.py`) and the `case`.

**Channel hygiene (`status.channel_overlap`).** `status` catches a bucket active SIMULTANEOUSLY as
a plugin (connect, `enabledPlugins`) and vendored (vendor, manifest `source_path` → bucket) →
`⚠ CHANNEL DUPLICATE`. One check, in skiller (the skill owner); the umbrella calls it via
`swissknifeman skills status`, not duplicated per package. Sync invariant: only `managed: true`
records are touched — foreign/manual `skills-lock.json` entries survive `sync`.

**Topology (`topology`, `lib/skiller/topology.py`).** Global map of the local environment
`~/.swissknifeman/topology.json` (version 1): three hub nodes `brain`/`swissknifeman`/
`projects_base` (roles `docs-hub`/`skills-hub`/`workspace`). `init` — interactive collection
(autodetected defaults: swissknifeman = registry root, projects_base = common ancestor of paths
in `projects.json`, brain = `~/Vaults/Brain`), atomic write with `.bak` backup, `created_at`
preserved. `show [--json]` — print. The file is machine-specific, not committed into projects.
Offered on `install.sh` (TTY). The distributed skill `skills/system/local-topology` explains the
scheme and resolves nodes from this file.

`scripts/connect-claude.sh` and `sync.sh` are one-release deprecation wrappers. Brain-sync was
removed: brain is an ordinary consuming project.

## Generated artifacts — never hand-edited

| Artifact | Generator |
|---|---|
| `skills.json` (registry v5: sha256 + content_sha256, provenance, requires/produces_for, optional `level`) | `skiller registry` |
| `skills/*/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` | `skiller registry` |
| `docs/guide/graph.md` (Mermaid dependency graph) | `skiller registry` → `scripts/generate-graph.sh` |
| 26 thin root-bootstrap projections (`.claude/skills/<id>/`+`.agents/skills/<id>/`) + `adapters/repository-bootstrap/publication-lock.json` | `skiller registry` → `publication.py`'s root-bootstrap renderer |
| Project hub (managed CLAUDE.md block or `.ai/guidelines/swissknifeman-hub.md`) | `scripts/generate-hub.sh` |
| Permissions/MCP/hooks in a project | package **`harness`** (`harness permissions\|mcp\|hooks`); skiller delegates via subprocess |

## Validation — `scripts/validate.sh` (== CI)

Check groups: (1) SKILL.md frontmatter — local skills require name/bucket/version/description,
skills with upstream.json only need name/description; (2) upstream.json schema; (3)
profiles/*.json; (4) skills.json parses; (5) snippet manifests; (6) buckets.json 1:1 with bucket
directories; (7) plugin manifest freshness; (7b) forbids nested SKILL.md; (8) name uniqueness
within a bucket (across buckets — warning); (9) requires/produces_for: existing names, no
self-ref or cycles; (10) soft lint of internal `.claude/skills/` skills (name+description,
kebab-case == directory name); (11) `bash -n` on all scripts + CLI executability. Description
budget: `DESC_WARN_MAX=300` (warn) / `DESC_ERROR_MAX=450` (hard error) + burn-down ratchet
`scripts/desc-burndown.txt` (inherited debt over 300 is legal only while listed; new debt outside
the list is an error; one-way — stale entries warn for removal).

## `integrate` wizard (`lib/skiller/integrate.py`)

Checklist wrapper over the commands: prerequisites → skills → permissions → **MCP** →
auto-approve → memory → hub → brain. Bundles `minimal`/`recommended`/`full`/`custom`
(`BUNDLES` = pre-answers). All writes merge-only, `*.bak` backup, `--dry-run`.

**Skills channel (`--skills-channel connect|vendor|skip`).** `_resolve_channel`: flag >
interactive question (TTY) > bundle default (`connect`). Skills block routes: `connect` →
`do_connect`; `vendor` + `agent=claude` → **`do_sync`** (physical copies into `.claude/skills/`
via `.swissknifeman/config.json`); `vendor` + `cursor|generic` → legacy `do_vendor`. `maind
onboard`/`swissknifeman setup` forward the same flag and also ask the channel (skills only;
memory/graph are separate planes, channel-independent).

**Environment is delegated to `harness`.** The permissions/MCP/auto-approve/memory blocks don't
write files themselves — they call `harness permissions|mcp|hooks` via subprocess (launcher
resolution: `harness_bin(env)` → `SKM_HARNESS_BIN` or
`<monorepo>/packages/harness/bin/harness`; no harness → block softly skips). What stays here is
POLICY selection: `_default_mcp(target)` gives `DEV_MCP` (currently `context7`) to everything
**except** `obsidian-vault`; `recommended`/`full` include dev-MCP, `minimal` — no, `custom` —
asks. The MCP/permissions presets themselves and their merge live in the `harness` package
(`configs/claude-code/`). To add a server: a preset under
`packages/harness/configs/claude-code/mcp/`, plus `DEV_MCP` in integrate if needed.

## Other tools and contracts

- `scripts/update-upstreams.sh --check|--apply` — sync external skills via upstream.json
  (sha256, fetched_at).
- `scripts/scan-skills.sh` / `scan-and-pr.sh` — candidate scanner, quality threshold ≥60
  (`.skills-scanner.json`).
- `references/` — lifecycle of external sources: planned → imported/rejected.
- `buckets.json` — mandatory metadata for every bucket (description/category/tags).
- `SKILL_TEMPLATE.md` — canonical frontmatter schema.
- `docs/` — VitePress (`docs/.vitepress/config.mts` — sidebar).

## Sync matrix ("what pulls what")

| Change | Required actions |
|---|---|
| A skill added/changed/moved/removed | `validate.sh` → `skiller registry` → commit the regenerated output |
| New bucket | entry in `buckets.json` |
| `requires`/`produces_for` changed | graph regeneration (part of `registry`) |
| External skill file updated | `update-upstreams.sh --apply` (sha256 + fetched_at) |
| Substantive change | CHANGELOG `[Unreleased]` → [release-discipline] |
| Process/capability changed | docs/ assessment → [docs-maintenance] |

## Related skills

- [skill-authoring] — procedure for creating/editing skills.
- [release-discipline] — closing out a change (validate → registry → CHANGELOG → PR).
- [docs-maintenance] — decision on updating docs/ after a task.

## Links

- `CONTRIBUTING.md` — canonical contribution process.
- `README.md`, `docs/guide/index.md`, `docs/guide/cli.md`.

## Provenance (root-bootstrap, P1.2)

Class-A private/source-only root-bootstrap identity (D31/D38, `plans/2026.07.24-AGENT-RELIABILITY`):
canonical source is this file's `SKILL.ru.md`; thin projections —
`.claude/skills/package-architecture/SKILL.md` and `.agents/skills/package-architecture/SKILL.md`
(generated by `skiller registry`, never hand-edited). Bucket `repository-bootstrap` is
private/source-only: never published as an ordinary unit/core/marketplace entry, never
vendored/connected into a consumer project.

<!-- ru-source-sha256: 16a3d675f6daaeb1ecb86836736b6f0b828033ec3bf4d9dae739766b6d6a2e65 -->
