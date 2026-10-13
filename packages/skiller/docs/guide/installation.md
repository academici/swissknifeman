# Installation

Installation consists of two steps: install once CLI `swissknifeman`,
then each project is connected with a command from its own directory -
the registry does not need to know about your projects.

> Do you want to select all the functionality at once? (skills + permissions + hooks + memory + hub)
> through one interactive wizard - see. [Integration checklist](./integration-checklist)
> (`skiller integrate`). Below is the installation of skills individually.

## Step 1. CLI (once per machine)

```bash
cd /path/to/skiller
./install.sh
```

`install.sh` creates a symlink `~/.local/bin/skiller → <package>/bin/skiller`
and the state directory `~/.swissknifeman/`. When provider CLIs are present, it
registers the local marketplace and installs the configured machine plugins.
Codex selection combines CORE policy with the host's `default_command_plugins`;
Grok source paths and optional hold plugins come from `machine_plugins.grok`.
For the ecosystem host, these include planner and `prefix-hold`, exposing `$ planner:*`
in Codex and `/planner:*` in Grok. Standalone installs have no host command plugins.
Grok does not install the root `core` plugin or profile plugins.

After moving the checkout, rerun `./install.sh` to refresh the symlink and native
marketplace/plugin paths. Flags: `--bin-dir DIR` (default `~/.local/bin`),
`--force` (replace an occupied binary path), `--no-codex-plugins`, and
`--no-grok-plugins`. Add a global Codex plugin with repeatable
`./install.sh --codex-plugin NAME`; default selection remains enabled.
An already configured or installed Grok plugin counts as success.
If `~/.local/bin` is absent from `PATH`, the installer prints the shell command.
Check the installation with `skiller doctor`.

## Host configuration and standalone installs

Skiller reads optional host-repository integration data from `configs/skiller-host.json`.
This is separate from a consumer project's `[skiller]` and `[skiller.sync]` settings in
`.swissknifeman/config.toml` (see [Configuration](./configuration)): those select skills
and providers for that project.
The host config describes the repository containing the **Skiller installation**.

Discovery starts at the installed package root and finds its enclosing repository.
When Skiller is nested in that repository, it reads the root's
`configs/skiller-host.json`. A repository rooted at Skiller itself has no implicit
host. `SKILLER_HOST_CONFIG` overrides discovery and must point to an existing
file by absolute path. Paths inside the document remain relative to the detected
repository root (or the Skiller package root when no repository is found), regardless
of the override file's location. Discovery never uses the target consumer project.

Only `schema_version: 1` is required. Omitted fields disable their corresponding
integrations. The schema is `schema/host.schema.json` (`urn:skiller:host:v1`).
The following example uses the host's integration fields with an illustrative
`plugins/` and `tools/` layout; replace paths and plugin names with your host's data:

```json
{
  "schema_version": 1,
  "plugin_dirs": ["plugins/*"],
  "default_command_plugins": ["planner"],
  "version_files": [{"path": "plugins/planner/configs/command-routing.json", "key": "plugin_version"}],
  "machine_plugins": {
    "grok": [{"name": "planner", "path": "plugins/planner", "holds": ["plugins/planner/adapters/grok/prefix-hold"]}]
  },
  "runtime_projection_plugins": ["planner"],
  "codex_link_roots": ["plugins/planner/adapters/codex/skills"],
  "legacy_runtime_links": [{"link": "plugins/planner", "plugin": "planner", "source": "plugins/planner"}],
  "commands": {
    "permissions": {"argv": ["tools/harness/bin/harness", "permissions"], "env_override": "SKM_HARNESS_BIN", "install_hint": "tools/harness/install.sh"},
    "settings_doctor": {"argv": ["tools/harness/bin/harness", "doctor", "--settings"], "env_override": "SKM_HARNESS_BIN"},
    "environment": {"argv": ["tools/harness/bin/harness"], "env_override": "SKM_HARNESS_BIN"},
    "environment_doctor": {"argv": ["tools/harness/bin/harness", "--help"], "env_override": "SKM_HARNESS_BIN"},
    "trace_doctor": {"argv": ["tools/analyst/bin/analyst", "doctor"]}
  },
  "mcp_servers": {"maind": {"tools": 11, "instructions_tokens": 0}},
  "bootstrap": "configs/repository-bootstrap-skills.json"
}
```

| Field | Meaning |
|---|---|
| `plugin_dirs` | Repository-relative globs for sibling plugins containing `.claude-plugin/plugin.json`; Skiller itself is excluded. |
| `bucket_aliases` | Skill buckets the library leaves to the host (`"provided_by": "host"` in `buckets.json`): bucket name mapped to the host plugins whose skills it expands to on connect, vendor and sync. |
| `default_command_plugins` | Command plugins added to the default install and delivery selection. |
| `version_files` | JSON files and top-level keys updated to the umbrella release version. |
| `machine_plugins` | Provider-keyed arrays of plugin `name`, source `path`, and optional `holds` paths for machine installation. |
| `runtime_projection_plugins` | Plugins whose generated runtime projections join release and delivery evidence. |
| `codex_link_roots` | Host source directories used to recognize and retire legacy Codex skill links. |
| `legacy_runtime_links` | Legacy `link`, owning `plugin`, and `source` records used during runtime migration. |
| `commands` | Named external commands: `argv`, optional binary `env_override`, and optional `install_hint`. |
| `mcp_servers` | Optional per-server `tools` and `instructions_tokens` counts for first-turn budget estimates. |
| `bootstrap` | Repository-relative config for source-only repository skill identities and their generated projections. |

For `commands`, an `argv[0]` containing `/` resolves from the host root; a bare
command name resolves through `PATH`. A configured `env_override` takes precedence
when set. Other argv entries are passed unchanged. An unconfigured or unavailable
external command is skipped by its owning optional integration.

Validation is closed: unknown fields, wrong types, absolute document paths, and
`..` path components fail with `HOST_CONFIG_INVALID`. A bad explicit override also
fails; it never falls back silently. Commands needing host data stop on invalid
config, while `skiller --help` and `skiller version` remain available.

With no host config, Skiller uses an empty host. Registry, skill resolution and
consumer skill operations remain available; host plugin aggregation, version-file
updates, machine plugin additions, bootstrap projections and command delegations
are disabled. Host-dependent validation reports a standalone skip. The current
standalone layout includes the shared `core/` dependency and its provider catalogs;
packaging or vendoring that dependency belongs to the actual repository move.
See [`skiller resolve`](./cli#skiller-resolve) for the read-only skill-resolution API.

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
| **Grok** | `./install.sh` once, then per project `providers.selection.grok.enabled` + `maind sync --project <id>` + `harness hooks --provider grok … --target .` | machine plugins `planner` and `prefix-hold` (`/planner:*`); project MCP in `.grok/config.toml`; hooks in `.grok/hooks/`; skills through the connect catalog |

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
`<state>/skiller/projects.json` — this includes `skiller list` and
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
