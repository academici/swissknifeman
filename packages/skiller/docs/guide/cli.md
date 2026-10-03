# CLI swissknifeman

`bin/skiller` — single entry point: connecting projects, updating,
diagnostics and registry maintenance. Installed by symlink in `~/.local/bin`
(see [Installation](./installation)); determines the path to the registry itself via
`readlink` own file - there is no path configuration.

## Commands for projects

All commands find the project root automatically - by moving up from the current one
directories to the nearest marker: `.swissknife.json` → `.claude/` → `.git`
(directory or file - worktree and submodule are considered). Nearest marker
wins: submodule — is its own project; to move the root, put
`.swissknife.json` to the desired directory. Inside the registry itself project-commands
refuse to work.

### `skiller connect`

Connects the project to the native one plugin marketplace Claude Code: writes
`extraKnownMarketplaces.swissknifeman` and `enabledPlugins."<bucket>@swissknifeman"`
in `.claude/settings.local.json`. Merge-only: explicit `false` does not fray,
enabled above the profile is not disabled, backup in `*.bak`.

Provider selection is taken from `.swissknife.json::providers`: in the absence
layer is saved legacy-mode only for Claude Code. Self-host checkout
uses thin Codex marketplace, and external connect-project receives
repo-contained marketplace and self-contained bundles only selected plugins,
including runtime-skill files (`snippets/`, `references/`, scripts/assets).
Project publication does not change user-level plugin state: basic `core` + `task`
sets machine `install.sh`, and profile Codex plugins are added only
explicitly. Native manifest each bucket lists skill-directories explicitly, so Codex
reveals them after installation. Dual-selection passes preflight all provider-targets
before the first write, so the conflict does not leave the successful half of the connection.

```
skiller connect [--profile P | --plugins a,b]
                      [--file settings.json|settings.local.json]
                      [--cleanup-vendored] [--list] [--dry-run] [--hub]
```

### `./install.sh [--no-codex-plugins]`

Machine installation adds marketplace current checkout in Codex and default
installs basic plugins from CORE-policies (`core` + `task`). If Codex CLI
is missing, this step is clearly skipped without breaking the installation of the others CLI;
`--no-codex-plugins` — explicit opt-out. An additional global plugin is installed
repeatable `./packages/skiller/install.sh --codex-plugin NAME`.

`connect`, `sync`, `update`, `doctor` and `--dry-run` user-global Codex state not
are changing. Profile plugins are not automatically installed globally.

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

## Project map: `~/.swissknifeman/projects.json`

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
