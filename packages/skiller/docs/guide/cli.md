# CLI swissknifeman

`bin/skiller` — single entry point: connecting projects, updating,
diagnostics and registry maintenance. Installed by symlink in `~/.local/bin`
(see [Installation](./installation)); determines the path to the registry itself via
`readlink` own file - there is no path configuration.

## Commands for projects

All commands find the project root automatically - by moving up from the current one
directories to the nearest marker: `.swissknifeman/config.toml` → `.swissknife.json` → `.claude/` → `.git`
(directory or file - worktree and submodule are considered). Nearest marker
wins: submodule — is its own project; to move the root, put
`.swissknifeman/config.toml` to the desired directory. Inside the registry itself project-commands
refuse to work.

### `skiller connect`

Connects the project to the native one plugin marketplace Claude Code: writes
`extraKnownMarketplaces.swissknifeman` and `enabledPlugins."<bucket>@swissknifeman"`
in `.claude/settings.local.json`. Merge-only: explicit `false` does not fray,
enabled above the profile is not disabled, backup in `*.bak`.

The skill selection comes from `[skiller]` in `.swissknifeman/config.toml` (the legacy `.swissknife.json` is read
with a warning). Provider selection is taken from `.swissknife.json::providers`: in the absence
layer is saved legacy-mode only for Claude Code. Self-host checkout
uses thin Codex marketplace, and external connect-project receives
repo-contained marketplace and self-contained bundles only selected plugins,
including runtime-skill files (`snippets/`, `references/`, scripts/assets).
Project publication does not change user-level plugin state: basic `core` + `planner`
sets machine `install.sh`, and profile Codex plugins are added only
explicitly. Native manifest each bucket lists skill-directories explicitly, so Codex
reveals them after installation. Dual-selection passes preflight all provider-targets
before the first write, so the conflict does not leave the successful half of the connection.

```
skiller connect [--profile P | --plugins a,b]
                      [--file settings.json|settings.local.json]
                      [--cleanup-vendored] [--list] [--dry-run] [--hub]
```

### `./install.sh [--no-codex-plugins] [--no-grok-plugins]`

Machine installation registers the current checkout's marketplace in Codex.
Its default plugin selection combines CORE policy with the host's
`default_command_plugins`. Grok installs the sources and optional holds declared
in `machine_plugins.grok` with `--trust`; standalone has no host machine plugins.
The ecosystem host supplies planner (`/planner:*`) and `prefix-hold`.
If a provider CLI is missing, its step is skipped.
`--no-codex-plugins` and `--no-grok-plugins` opt out. Add a global Codex plugin
with repeatable `./install.sh --codex-plugin NAME`.
Grok does not receive `core` or the profile plugins.
See [host configuration and standalone installs](./installation#host-configuration-and-standalone-installs)
for discovery and field definitions.

`connect`, `sync`, `update`, `doctor` and `--dry-run` user-global Codex state not
are changing. Profile plugins are not automatically installed globally.

A bucket the library leaves to the host (`system`) expands into the host plugins named by `bucket_aliases`; see
[Configuration](./configuration#host-provided-buckets).

### `skiller describe`

Prints the `skill-descriptor/v1` of one skill of the library or of a host module: name, version, license, digest,
provenance, `requires`, adapters, and `compatibility` and `allowed_tools` when the skill declares them.

```bash
skiller describe SKILL [--json]
```

`SKILL` is a name or `bucket/rel`. An unknown skill exits 1. See [Skill metadata](./configuration#skill-metadata).

### `skiller select`

The skills an orchestration role gets for a piece of work: a pure function over `skills.json` (the `selection` sidecars) and `configs/exclusive-groups.json`.

```bash
skiller select --role ROLE [--paths P…] [--deps D…] [--project DIR] [--include ID…] [--exclude ID…] [--tools T…] \
  [--budget TOKENS] [--model-class C] [--provider P] [--policy explicit|auto] [--json] [--explain]
```

Steps: explicit `--include` → path and dependency triggers (only under the policy `auto`) → filters: `role_not_allowed` (`selection.roles`), `excluded` (`--exclude`, wins over include), `tool_missing` (`requires_tools` against `--tools`), `kind_not_preloaded` (`router`, `reference`, `persona`: listed in `discoverable`), `duplicated_by_role_contract` (`replaced_by`) → `exclusive_group` (the group `max`) → `over_budget` (`--budget`; a body is never cut). An explicit include is exempt from the filters except `--exclude` and from the budget. `--project` adds the dependencies of its `composer.json`, `package.json` and `pyproject.toml`; the policy comes from `[skiller.selection] policy` (`explicit`, the default, or `auto`) unless `--policy` is given. The answer is `{included: [{id, name, path, reason, tokens}], excluded: [{id, reason, detail?}], discoverable, tokens, request}`; `--explain` adds the trace of every step. `--provider` and `--model-class` are echoed in `request` and do not change the selection yet.

### `skiller selection`

The selection policy of the library (`selection.json` beside each `SKILL.md`, contract `skill-selection/v1`; `skiller registry` copies it to `skills.json` as `selection`).

```bash
skiller selection report [--json]   # decisions against the audit summary 3.5 (configs/selection-summary.json)
skiller selection check             # schema, conflicts, exclusive groups (configs/exclusive-groups.json); exit 1 on a problem
```

`report` lists the differences from the audit counts and does not fail; `check` is a gate of `validate.sh`. The sidecar is not part of the skill content: it is not hashed and not copied to consumers.

### `skiller resolve`

Reads the package's `skills.json` and resolves requested skills plus their transitive
`requires`, without changing files. Accepts `bucket/name`, `bucket:name`, or a unique
bare name. Ambiguous names report `SKILL_AMBIGUOUS` with the candidate IDs.

```bash
skiller resolve quality/code-review [SKILL ...] [--provider claude-code|codex|grok] [--json]
```

JSON uses `schema: "skiller.resolve/v1"` and contains normalized `requested` IDs,
`provider` (null when omitted), sorted `skills`, and `diagnostics`. Each skill includes
its ID, name, bucket, package-relative `path`, `requested` flag, and sorted immediate
`required_by` IDs. The default text output shows IDs and their selection reason.

Unknown requested skills report `SKILL_UNKNOWN` and exit 1; ambiguous names also
exit 1. JSON still includes diagnostics and any successfully resolved skills.
Missing transitive requirements produce `SKILL_REQUIRED_UNKNOWN` warnings and exit 0.
No skill arguments or invalid options exit 2; `--help` describes the command.

`--provider` echoes the provider and, when a registry entry declares `adapters`, warns
with `SKILL_PROVIDER_UNSUPPORTED` for an unsupported provider while keeping that skill
in the result. The `claude` adapter accepts `claude-code`. Entries without adapter
metadata remain available without a warning.

### `skiller vendor`

Vendors skills to the project (Cursor and other agents): profiles, autodetection,
transitive resolve `requires`, manifest-reinstall - see.
[Installation](./installation) and [Vendoring](./vendor-skills).

```
skiller vendor [--agent claude|cursor|generic]
                     [--profile P | --buckets a,b] [--exclude x,y]
                     [--skills-path P] [--list] [--dry-run] [--force] [--hub]
```

### `skiller integrate`

Interactive integration wizard: passing [checklist](./integration-checklist) by
all functionality (skills, permissions, MCP, hooks auto-approve/memory/output-style,
hub) and applies the selection. Skills/hub — himself skiller; environment (permissions/MCP/
hooks, including terse output-style `lean` — is included in all bundles) is delegated
package [`harness`](/harness/) via subprocess. Safe -
`--dry-run`, merge-only, backups.

```
skiller integrate [--target P]
                        [--bundle minimal|recommended|full|custom]
                        [--yes] [--dry-run] [--file settings.json|settings.local.json]
```

### `skiller update [--all] [--dry-run]`

Updates the project connection. Disk is the source of truth: channels are determined
by markers (`extraKnownMarketplaces.swissknifeman` in `.claude/settings*.json`;
`.swissknifeman-manifest.json` in `skills_path` / `.claude/skills` /
`.cursor/skills` / `.ai/skills`), the project can be on both channels at once.

- **marketplace**: fixes the registry path if the repository has moved
  (with backup), adds plugins that appear in the profile, regenerates the hub,
  shows HEAD SHA registry and warns about uncommitted skills
  (marketplace only sees commits).
- **vendor**: clean reinstallation according to manifest - deleted/renamed
  in the registry, skills are removed from the project.

::: warning A clean reinstall removes previously vendor skills
`vendor` (and `update`) reads `.swissknifeman-manifest.json` and **deletes** skills,
that were previously vendored but are no longer part of the current registry set
(skill removed/was renamed in the registry, or it fell out of selection `--buckets`/
`--exclude`). This also applies to **uncommitted** local copies with the same path.
Project skills that need to be saved **keep in git** (or outside
`skills_path`/manifest); when Boost copies of them remain in `.cursor/skills`,
`.claude/skills` and are restored from there. Preview of the deleted item - `--dry-run`.
:::

Project with markers, but no entry in `projects.json`, is registered
automatically (adopt) — project map is self-healing.
`--all` crawls all registered projects, skipping missing ones
directories, and prints a summary.

### `skiller status`

Read-only report: root and marker, channels, drift of plugins relative to the profile,
crossed path marketplace, status of vendor skills, SHA registry.

### `skiller list [--prune]`

Table of registered projects with status `ok|missing`. Entries never
are not deleted automatically - only explicit `--prune`.

### `skiller profiles [--json]`

Read-only list of the project-type profiles delivered with skiller
(`profiles/*.json`). `--json` prints one document with the schema
`urn:swissknifeman:skiller:profiles-list:v1`.

### `skiller topology`

Deprecated alias of `maind topology`: the machine topology map moved to maind.
The alias prints `SKILLER_TOPOLOGY_MOVED` to stderr and runs the maind command
found on `PATH` (or through `SKM_MAIND_ROOT`); without maind it exits with
`PARTNER_UNAVAILABLE`.

### `skiller analyze-run [--last | --session ID] [--project DIR] [--json] [--store]`

Post-run analysis of the run JSONL-logs Claude Code (deterministic, no waste
tokens): fact tokens/timings/cache-hit by agent + effective/dead skills +
runtime failures. Complements quality skill `system/session-observer`. Details,
format and restrictions - [analyze-run](./analyze-run.md).

## Maintainer Commands

| Command | What it does |
|---|---|
| `skiller registry` | regenerates `skills.json`, plugin manifests `.claude-plugin/*` and `docs/guide/graph.md` (ex `./sync.sh --update-registry`) |
| `swissknifeman validate` | `scripts/validate.sh` (same as CI) |
| `skiller doctor` | python3, symlink, PATH, projects.json, registry cleanliness, profiles |
| `skiller doctor --context --provider codex [--target DIR] [--json]` | reads the actual Codex prompt inventory via native CLI and displays typed diagnostics `SKILL_DUPLICATE_NAME`, `CODEX_PLUGIN_ENABLED_OUTSIDE_PROJECT_POLICY` and `CODEX_DESIRED_PLUGIN_NOT_EFFECTIVE`; command read-only, separates observed inventory from managed project estimate and explicitly excludes platform overhead from the total |
| `skiller budget --first-turn [--provider claude-code\|codex\|cursor\|grok] [--target DIR] [--json] [--strict]` | provider-aware always-on footprint of the first move. Claude Code believes skills+agents+CLAUDE.md/rules+alive SessionStart+MCP; Codex believes `AGENTS.md`, excludes Claude agents/hooks and replaces managed skill estimate actual native prompt inventory. Unavailable native inventory gives `INCOMPLETE`, a `--strict` terminates with a non-zero code. Threshold managed footprint: OK ≤16K / ELEVATED ≤23K / WARN >23K. Fleet - `maind doctor --context`. MCP remains a mode-dependent evaluation `deferred|auto|off` |
| `skiller budget --first-turn --with-plugins [--target DIR] [--json]` | adds always-on price installed marketplace-project plugins (`claude plugin list/details`, call `details` — under `cwd` project, local-scope alien plugins CWD do not resolve) additive keys `plugins`/`session_total`/`session_verdict`; without the flag, the output does not change. Requires `--first-turn`; listing failure → `n/a`; unclaimed plugin price - `broken` (the listing itself declared the plugin a broken field `errors`) separate from `unparsed` (unrecognized upstream format), never silent 0. **The verdict thresholds are calibrated precisely at this plugin-inclusive value** (`session_total`): baseline fleet n=22, median plugin sum 8,741 current → `16K`/`23K` instead of the previous ones `7K`/`10K`, counted before plugins were even counted |
| `skiller budget --provider claude-code\|codex [--profile P\|--config F\|--target DIR]` | adds to normal skill-budget listing model without the rest first-turn surfaces. For complete provider receipt use the combination `--first-turn --provider ...`. `--profiles` compares each supplied profile with both providers |

**String «excluded entries: N (by field …)»** in reports `--first-turn` and `--provider`
. Recording a skill that carries `disable-model-invocation: true`
or `paths:`, to resident listing Claude Code **not included** — the meter does not count it and
prints the number of exceptions with a reason field, and next to it the price that was removed from the listing. Base -
OBSERVATION of the stand on live 2.1.220, not documentation: both fields gave the same axis delta A
(−88 for recording, played back byte-by-byte in two runs), and for `paths:` this
contradicts dockline «The listing always contains every skill name»
(§3.1–3.2). Mechanism condition
`paths:` — «session READ matched file», and not «file is in the tree»
(`findings/P3-paths-mechanism.md` §2), and on the FIRST move there are no read files by construction,
so the exception is unconditional. B JSON information arrives additively:
`sources.skills.excluded`/`excluded_by`/`excluded_raw` (`--first-turn`) and
`listing.excluded`/`excluded_by`/`excluded_raw` (`--provider`) — keys `total`/`verdict` and
the meaning of the previous keys does not change. For `--provider codex` exception **not applicable**:
fields measured only on Claude Code, and codex-thread deliberately continues to overestimate, instead
unproven understatement.
| `swissknifeman version` | git SHA + path to the registry |

## Project map: `<state>/skiller/projects.json`

Replenishes automatically when `connect`/`vendor`/`update`. Records with a key
(path, channel):

```json
{
  "version": 1,
  "projects": [
    {
      "path": "/home/user/projects/my-app",
      "channel": "marketplace",
      "profile": "laravel-project",
      "profile_source": "autodetect",
      "plugins": ["architect", "php", "quality"],
      "settings_file": "settings.local.json",
      "hub": true,
      "first_connected_at": "2026-06-12T10:00:00Z",
      "updated_at": "2026-06-12T10:00:00Z"
    }
  ]
}
```

`profile_source` controls behavior `update`: `autodetect`/`config`
will be re-resolved from disk, explicit `flag`/`plugins`/`buckets` are being reproduced.
Write is atomic; the damaged file is renamed to
`projects.json.corrupt.<date>` and is recreated - records are restored
adopt-ohm at the next `update` in the project.

Provider-aware vendor lock stores legacy Claude entries in `skills`, a Codex — in
`providers.codex`; project map key - `(path, channel, provider)`. Two
provider-and cannot own one physical skills path: operation fail-closed to
copy or prune.

## Troubleshooting

- **`bash: swissknifeman: No such file or directory`** — symlink hung
  (registry repository has moved or been deleted). Restart `./install.sh`
  from the new repository location.
- **`~/.local/bin` not in PATH** — `install.sh` prints the command for your
  shell; After adding, restart the terminal.
- **`python3 is required`** — install python3 (`apt install python3` /
  `brew install python3`).
- **Project not found** — no `.swissknife.json`, neither `.claude/`, neither
  `.git` up the tree; create `.swissknife.json` in the project root.
- General diagnostics: `skiller doctor`.

## Deprecated

`scripts/connect-claude.sh` and `./sync.sh --update-registry` — thin
wrapper's for one release, will be redirected to CLI. Brain-sync (`BRAIN_PATH`)
deleted: brain connects as a regular project (`cd <brain> && swissknifeman
vendor`, next `skiller update`).
# Verified release delivery

`skiller version --json` shows umbrella tag/commit and independent unit versions/digests.
`skiller attest --release vX.Y.Z --previous vA.B.C` generates `releases/vX.Y.Z.json`;
`--check` checks freshness and immutable version tuple. After verification generator locks
and commit run `python3 scripts/verify-tag.py vX.Y.Z` before creation annotated tag.

`skiller deliver --release vX.Y.Z --all --dry-run` classifies lost ownership without entry.
Without `--dry-run` command updates registered projects and installed native plugins,
restoring only exact-current/exact-known-old or closed generated marketplace form.
Modified/unknown files are saved and left PARTIAL. Until changes are saved preimages.
`--target PATH` limits project delivery; `--no-native` explicitly excludes cache stage.

Standard post-tag path - `./bin/swissknifeman release-fleet vX.Y.Z [--dry-run]`. He demands,
to local annotated tag pointed to `HEAD`, checks tag and release attestation, executes
`skiller deliver --all` and `maind sync --all`, then repeats both dry-run and fleet diagnostics.
The command does not create or move tags, does not push and does not publish GitHub Release.

Delivery builds a story from release snapshot, committed under real-life tags.
After provider update it removes from Claude/Codex cache only unlinked legacy directories
whose managed bytes exactly coincide with a tagged snapshot or the current attestation. This also
retires an untagged intermediate-SHA directory when its bytes exactly match the current release.
Current and referenced directories are saved; unknown/modified cache and unavailable provider state
give blocked/PARTIAL. Solution,
digest and readback deletions are recorded in delivery receipt; dry-run shows the same plan without
removal.

Receipt is stored in `~/.swissknifeman/receipts/delivery/<release>/`; GREEN requires readback
all selected targets. Existing sessions are marked `restart-required`: start a new session.
Source-managed bytes, native cache, project projection and loaded session — different surfaces.
Commit SHA is added to runtime receipt via annotated tag: committed attestation stores tag,
date and tree digests, to avoid creating a self-referencing SHA release commit.
# Native cache and legacy Codex copies

`connect --cleanup-codex-vendored` explicitly retires only directories declared by a known v1 `.agents/skills` vendor manifest. It keeps unlisted local skills, refuses foreign lock ownership, and moves the old copies into `.swissknifeman/backups/` so they can be restored. It does not change the project's configured plugin selection.

Release attestation distinguishes contained `codex` skill bundles from full `codex-native` source caches. Ignored local telemetry is not a release surface. Added evidence coverage is checked against the previous Git source tag; changing already recorded bytes still requires a new unit version.
