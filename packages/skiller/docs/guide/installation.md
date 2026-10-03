# Installation

Installation consists of two steps: install once CLI `swissknifeman`,
then each project is connected with a command from its own directory -
the registry does not need to know about your projects.

> Do you want to select all the functionality at once? (skills + permissions + hooks + memory + hub)
> through one interactive wizard - see. [Integration checklist](./integration-checklist)
> (`skiller integrate`). Below is the installation of skills individually.

## Step 1. CLI (once per machine)

```bash
cd ~/projects/packages/swissknifeman
./install.sh
```

`install.sh` creates a symlink `~/.local/bin/skiller → <repo>/bin/skiller`,
status directory `~/.swissknifeman/` and, when the CLIs are present, machine
plugins. Codex gets the local marketplace `swissknifeman` and basic plugins
`core` + `task`, so `$ task:*` is available in a new Codex session. Grok gets
the same marketplace plus `grok plugin install packages/task --trust` and the
`prefix-hold` plugin, so a new Grok session loads `/task:design`, `/task:dev`,
`/task:plan-design` and the other Task commands. Marketplace `core`
is not installed for Grok: its source is the monorepo root, and a path install
would copy the whole repository. Symlink means: after `git pull` the CLI is
always fresh, and it determines the path to the registry itself (via `readlink`).
The repository has moved — restart `./install.sh` from the new location to update
the Codex marketplace source and the Grok plugin path.

Flags: `--bin-dir DIR` (default `~/.local/bin`), `--force` (replace
someone else's file without question), `--no-codex-plugins` (skip Codex
`core` + `task`), `--no-grok-plugins` (skip the Grok `task` and `prefix-hold`
plugins). An additional
Codex plugin can be made repeatable `./packages/skiller/install.sh --codex-plugin NAME`;
basic plugins in this case are saved. A second Grok install that reports
`already configured` or `already installed` is success. If `~/.local/bin` is not
in `PATH`, the installer prints the shell command. Installation check: `skiller doctor`.

## Step 2. Connecting the project

From the project directory (the root is searched automatically upwards from CWD by
`.swissknife.json` → `.claude/` → `.git`):

```bash
# Claude Code — native plugin marketplace (recommended)
cd ~/projects/my-app
skiller connect

# Cursor — managed sync (recommended) or legacy vendor
cd ~/projects/my-app
# providers.selection.cursor.enabled=true in .swissknife.json, then:
skiller sync
maind onboard <path|id> && maind sync --project <id>
```

| Channel | Command | What goes into the project |
|---|---|---|
| **Claude Code** | `skiller connect` | only entries in `.claude/settings.local.json` |
| **Cursor** | `skiller sync` + `maind onboard/sync` | skills in `.agents/skills` (native discovery); MCP in `.cursor/mcp.json`; permissions — [adapter Cursor](../adapters/cursor) |
| **Cursor (legacy)** | `skiller vendor --agent cursor` | copies to `.cursor/skills` — avoid dual-write with `.agents` |
| **Codex (vendor)** | `skiller sync` with `providers.codex.enabled=true` | managed copies in `.agents/skills` + provider-qualified lock |
| **Grok** | `./install.sh` once, then per project `providers.selection.grok.enabled` + `maind sync --project <id>` + `harness hooks --provider grok … --target .` | machine plugins `task` and `prefix-hold` (`/task:*`); project MCP in `.grok/config.toml`; hooks in `.grok/hooks/`; skills through the connect catalog |

Grok plugins from step 1 are available in every project. They do not register
the project or turn Grok on. A project opts in with
`providers.selection.grok.enabled` in `.swissknife.json` after
`maind onboard <path|id>`. `maind sync --project <id>` then writes MCP, refreshes
skills, and appends `.gitignore` lines for service files that already exist.
Hook files are a separate `harness hooks --provider grok` step. See
[adapter Grok](../adapters/grok).

Basic Codex-plugins are installed once per machine in steps of 1 and are available in
all projects. Profile Codex skills are still delivered to the specific project
via vendor sync: the installer deliberately does not include globally all profile
plugins so that one project does not bloat other sessions.

::: tip Agents - only in plugin-channel
The bucket plugin can carry not only skills, but also a catalog `agents/` at its root
(`*.md` with YAML-frontmatter `name`/`description`/`tools`) — Claude Code
detects it automatically. Such agents are available **via channel only
`connect`**: `vendor` copies skills, but not agents, so in Cursor and others
generic-agents will not have them. Example - bucket `php` with agents `laravel-reviewer`
and `laravel-test-writer` (see skill `laravel-subagents`).
:::

Each connection automatically registers the project in
`~/.swissknifeman/projects.json` — this includes `skiller list` and
`skiller update --all`.

## Project with Laravel Boost (multi-agent, single source of truth)

If the project already uses [Laravel Boost](../boost-compatibility) — he has
`boost.json`, directory `.ai/` (guidelines + skills) and the command
`php artisan boost:update`, which generates `CLAUDE.md`/`AGENTS.md` and
scatters copies of skills across `.cursor/`, `.gemini/`, `.codex/`, `.github/`.
For skills swissknifeman lived in **one source of truth** and diverged along
to all tools automatically - we vendor directly in `.ai/skills/` and give away the distribution
Boost-y.

```bash
cd ~/projects/my-laravel-app
skiller vendor \
  --agent generic \
  --skills-path .ai/skills \
  --profile laravel-project \
  --exclude code-style-spatie,node-pnpm-preflight \
  --hub
php artisan boost:update      # or: composer ai:sync
```

What's happening:

1. **`vendor --skills-path .ai/skills`** — skills are copied to the source of truth
   Boost. When detected `boost.json` CLI automatically takes **flat-layout**
   `.ai/skills/<skill>/SKILL.md` (Boost detects user-skills through
   `glob('.ai/skills/*')` one level - bucket-he would not have found the subfolder).
   If the name of our skill matches an existing one in the project - installation
   will stop on a collision; add this skill to `--exclude` (draft version
   priority).
2. **Detected `boost.json`** — CLI idempotently overwrites vendor skills
   in `boost.json::skills` (by `name` from frontmatter) and prints the tooltip
   `php artisan boost:update`.
3. **`--hub`** — installed index is written to
   `.ai/guidelines/swissknifeman-hub.md`; Boost will build it into itself
   `CLAUDE.md`/`AGENTS.md` when `boost:update`.
4. **`boost:update`** — regenerates root docks and copies of skills for all
   agents from `boost.json::agents`.

::: warning Eliminate conflicting
`--exclude` removes skills whose rules contradict the project. Typical
conflicts: `code-style-spatie` (not-`final` default) against project with
mandatory `final`; `node-pnpm-preflight` (pnpm) vs yarn-project.
Compatibility Policy - [boost-compatibility.md](../boost-compatibility),
core principle - [What is SwissKnifeMan](./#_6-compatible-kernel-conflict-policy).
:::

**Update** of such a project is normal `skiller update`: he re
vendor, adding `boost.json` and regenerates the hub; then manually
`php artisan boost:update`.

### Tools out Boost: managed-block in root files

For projects **without** Boost the same index can be put managed-block directly in
agent root files:

```bash
./scripts/generate-hub.sh --target . --root-files AGENTS.md,GEMINI.md
```

The block is inserted between markers `<!-- swissknifeman:hub:start -->` …
`<!-- swissknifeman:hub:end -->` in `CLAUDE.md` (default) and in each
specified file; content outside the markers is not touched, the file is created when
missing.

### Block form: by target channel, not by project

U Claude Code yes **yours** skill listing: name and description of each available
skill (project and plugin) are resident from the beginning of the session, the body is loaded by
call. Index inside `CLAUDE.md` would be the second paid copy of the same
list, so the shape of the block depends on where it is written:

| Purpose | Native listing | Block shape |
|:--|:--|:--|
| `CLAUDE.md` | yes | **short** — source priorities, search rules, index |
| `.ai/guidelines/swissknifeman-hub.md` (Boost) | yes (fragment goes to `CLAUDE.md`) | **short** |
| `AGENTS.md`, `GEMINI.md` and others `--root-files` | no | **full** — with skill index |

The same run writes both forms: `CLAUDE.md` gets short, and
`AGENTS.md` from `--root-files` — full. Return index to all targets (rollback):

```bash
./scripts/generate-hub.sh --target . --full-index
./scripts/generate-hub.sh --target . --full-index --dry-run   # just look
```

Before abbreviation generator **checks detection**: skill leaves the block,
only if it is also in the active project set (`skiller budget`), and in the channel,
which the client lists natively (enabled marketplace plugin or copy in
`.claude/skills`). Unconfirmed skills remain in the block section «Skills outside
native listing», and the discrepancy is printed to the command output. Freshness-stamp
`<!-- swissknifeman:registry sha=… -->`, which verifies `skiller doctor`,
is present in both forms.

## Step 3: Update

```bash
cd ~/projects/my-app && skiller update   # current project
skiller update --all                     # all registered
```

`update` defines the channel itself(s) project by markers on disk, updates
vendor skills / settings marketplace, repairs the registry path if it
has moved and is regenerating the hub. Details of all commands are in
[directory CLI](./cli).

## Preview without installation

```bash
skiller vendor --list      # what will be installed, the files will not be touched
skiller connect --dry-run  # final settings.json without entry
```

## Explicit control

Auto profile detection (`.obsidian/` → obsidian-vault; `artisan`+`composer.json`
→ laravel-project; `composer.json` → php-package; otherwise standalone) you can
override:

```bash
skiller vendor --profile php-package
skiller vendor --buckets php,quality
skiller vendor --buckets php,quality --exclude botkit
skiller connect --plugins php,quality
```

For Dart-libraries or SDK connect `dart` explicitly: `skiller connect --plugins dart`.
This is a batch set (public API, null safety, tests and compatibility); Flutter-layout by
Figma remains separate `mobile`-with a bucket.

Configuration source priority: **flags CLI → `.swissknife.json` → autodetection**.
Explicit selection (`--profile`, `--buckets`, `--plugins`) is stored in
`projects.json` and plays when `update`; autodetect will re-resolve
from disk every time.

## Dependencies between skills

Field `requires` in frontmatter skill is resolved transitively: with selective
installation (`--buckets`, `--exclude`) `vendor` falls short of dependencies - in that
number from buckets that you did not select (in bucket-layout reached skill
saves the directory of its bucket, for example `founder/competitive-analysis`
during installation `--buckets pm`). Reached skills are marked in `--list` and
`--dry-run` like `(dependency of <skill>)`.

`--exclude` defeats addiction: the excluded skill is never set,
CLI only warns (`WARN: ... excluded by --exclude, skipping`).

The whole picture of connections is on [dependency graph page](./graph).

::: warning Marketplace-channel does not resolve dependencies
B plugin marketplace Claude Code plugin = bucket: enable plugin `php`
will not enable the dependent skill from the bucket `architect`. Resolution only works
in the vendor channel. Include related buckets manually using the dependency graph.
:::

## Fixing the configuration: `.swissknife.json`

A project can commit its installation configuration to `.swissknife.json`
at the root - `connect`, `vendor` and `update` will read it automatically:

```json
{
  "project_type": "laravel-project",
  "buckets": ["architect", "php", "quality"],
  "exclude": ["botkit", "devops/gitops"],
  "skills_path": ".claude/skills",
  "agent": "claude"
}
```

All keys are optional. If set `buckets`, field `project_type` is ignored.
The file passes schema validation: unknown key or incorrect type - clear
error with hint (`unknown key 'bucket' — did you mean 'buckets'?`).
Keys starting with `_`, are considered comments.
Template - [.swissknife.example.json](https://github.com/academici/swissknifeman/blob/main/.swissknife.example.json).

### Config media inside skiller

The read file lives in the code not as a bare dictionary, but as an object
`skiller.config.ProjectConfig` — frozen dataclass on stdlib (none `pydantic`
or `jsonschema`). Object fields are the only carrier of the list of keys: list
`CONFIG_KEYS`, with whom `skiller doctor` and `tests/test_schema.py` are verified
`schema/swissknife.schema.json`, **is output** from fields (`metadata["json_type"]`
of each field carries the same Python-type with which the value is validated). Add
key = add field and property to schema; third place where you can forget your keys
update, no.

Object read-only: no one mutates the project config after loading, so
`frozen=True` (in contrast to the NODE config wrapper mAInd — there is a subclass `dict`
with `save()`). The original dictionary is saved as `raw` — are read from it
`_`/`$`-keys and subbranches `providers`; old access display
(`config.get("agent")`, `config["agent"]`) continues to work byte-for-byte.

Object Home - Package `skiller`, not generic `core/`: criterion for accepting a primitive into
foundation - «is duplicated between ≥2 packets with stable boundary», and validation
`.swissknife.json` is tied to local knowledge of the registry (list of profiles,
`AGENT_DEFAULTS`, reserved keys). The only external file reader is
`maind` — takes only the subbranch `providers`, and it is typed in `core`.

## Manifest, reinstallation and collisions

`vendor` writes a manifesto `.swissknifeman-manifest.json` next to the skills -
in both layouts (flat and bucket). Reinstallation first removes
**only** listed in the manifest, then reinstalls - other people's skills are not
are starting to move.

If the skill's target folder already exists and is not listed in the manifest, installation
breaks with a collision list. Rewrite consciously: `--force`.

## Mode `--agent claude` (deprecated)

Vendoring for Claude Code left for compatibility (flat layout
`.claude/skills/<name>/SKILL.md`, collisions resolved by prefix bucket-a),
but the preferred path is `skiller connect` ([marketplace](../adapters/claude-code)).
Migrate from vendor: `skiller connect --cleanup-vendored`.
The flag also removes **raw vendor** (symlinks/copies to `.claude/skills` without
`.swissknifeman-manifest.json`), if the skill name is already turned on
marketplace-bucket; project-specific records and maind-managed
`ecosystem-mcp`/`ecosystem-setup` are not touched.

## What's next

After installing skills, tighten up the presets permissions, so that the agent can immediately
work without prompts - see. [Permissions for Claude Code](/harness/configs/claude-permissions).
