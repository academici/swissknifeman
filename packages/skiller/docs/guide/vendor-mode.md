# Vendor-mode: physical transfer of skills (`sync`)

Two channels for delivering skills to the project:

| Channel | Command | What it does | Granularity |
|---|---|---|---|
| **connect** (marketplace) | `skiller connect` | Includes plugin buckets Claude Code via `enabledPlugins`. Skill files **are not copied** in the repo. | Entire bucket |
| **vendor** (physical. transfer) | `skiller sync` | **Copies** selected skills in the repo, writes derivative `skills-lock.json`. | Individual skills |

`connect` is good when you don't need a commit to the repository and are happy with «whole bucket».
**vendor-mode** — when needed: see skills in the repo, select exactly the right positions
from different areas, fix the set and update it from the library by lock-file.

::: tip Main case vendor — external developers
`connect` connects plugins via `extraKnownMarketplaces`, which points to
**local registry path swissknifeman**. From the developer who was given the repository
project, but **no** repo swissknifeman, plugins will not connect - it will not see the skills.

`vendor` (`sync`) puts **skill files directly in the project repo** (`.claude/skills/`,
git-tracked). Anyone who cloned the project immediately receives skills - registry swissknifeman
he doesn't need. This is a channel for projects with an external team.
:::

Channel selection concerns **only skills** — they have no other functionality except distribution
files. Memory, graph and MCP-hub tools mAInd are configured regardless of channel.

## Config - a single source of truth

The vendor mode is the `[skiller.sync]` table of `.swissknifeman/config.toml` at the root of the project.
One config instead of scattered files: the rules unfold into a flat set of skills.

```toml
[skiller.sync]
agent = "claude"
skills_path = ".claude/skills"
presets = ["laravel-admin"]
include = ["architect/api-design"]
buckets = ["quality"]
exclude = ["laravel-extras/medialibrary"]
```

A project that still has the legacy `.swissknifeman/config.json` keeps working: it is read with a warning until
the table is written. See [Configuration](./configuration).

The rules are combined: **set = (presets ∪ buckets ∪ include) − exclude**.

- `presets` — named skill clusters (`presets/<name>.json`): are expanded in
  `buckets`/`include` (with recursive `extends`). Comfortable «pieces» instead of manual enumeration -
  e.g. `laravel-admin` = core Laravel + Filament/rights/media. See [Presets](./presets).
- `include` — specific skills from any area: `"bucket/rel"` or simply `"name"`.
- `buckets` — entire buckets.
- `exclude` — subtraction (name or `"bucket/rel"`); hits both presets and dependencies.
- Can only be set `presets` or only `include` — is transferred exactly what is needed.

> Presets - concept **vendor-channel** (are expanded in per-skill set). B `connect`
> the bucket is atomic, so presets do not work there (like skill-level `exclude`).

## Synchronization thread

```
[skiller.sync] in .swissknifeman/config.toml   (source of truth - man rules)
        ↓ resolve            (buckets ∪ include) − exclude → flat set
   set of library skills   (resolves by skills.json registry)
        ↓ sync               install + update(by sha256) + prune(by managed)
                             + CORE-default skills (like vendor/connect)
.claude/skills/<name>/        physical copies (sees Claude)
skills-lock.json             derived map: managed-entries + aliens untouched
.swissknifeman-manifest.json  manifest in skills_path (reinstallation + hub index)
CLAUDE.md / .ai/guidelines    skill index (managed-block), if available or --hub
```

```bash
skiller sync --dry-run     # show plan: +add ~update -remove =keep
skiller sync               # apply (CORE is heard by default)
skiller sync --force       # overwrite someone else's path with a version from the library
skiller sync --hub         # additionally generate a skill index
skiller sync --no-core     # without CORE-skills; --no-hub — without index
```

`sync` writes `.swissknifeman-manifest.json` in `skills_path` (contract clean
reinstallation and source for `generate-hub.sh`), distributes `CORE_SKILLS` by
default (`--no-core` disables) and updates the skill index in the project root
(managed-block `CLAUDE.md` or `.ai/guidelines/swissknifeman-hub.md` for Boost),
if it is already in the project or transferred `--hub`.

## skills-lock.json — derived, not source

`sync` writes for each of our skills an entry marked with origin:

```json
"laravel-best-practices": {
  "source": "swissknifeman",
  "managed": true,
  "bucket": "php",
  "sha256": "…",
  "installed_path": ".claude/skills/laravel-best-practices"
}
```

- **`managed: true`** — skill under control vendor-mode. **Removal**: with sync
  full sample is taken `managed`-records, checked against the config; something that no longer exists
  in the config, **is removed** from lock and from the repo.
- **Other people's posts** (`managed` missing/false — manual vendoring, skills from another
  hub, legacy Boost) sync **does not touch**: neither deletes nor erases. You can add more
  in `skills-lock.json` own skills manually - `sync` synchronizes **only
  `managed: true`** and other people's records are experiencing sync (even with an empty config).
- **Drift** — for discrepancy `sha256` with the library the file is copied (`~update`).
- **Manual cleaning lock.** If you delete our `managed`-entry manually, and skill folder
  remains - `sync` without `--force` will consider the path foreign (pass with warning), `--force`
  will purely re-adopt the skill (one `managed`-record, without tails).

## Channel hygiene: do not hold the bucket in both at once

One bucket should not be distributed **at the same time** plugin (`connect`) and vendor
(`vendor`) — otherwise the skills will arrive twice. `skiller status` this catches and prints
`⚠ DOUBLE CHANNELS: …` with a list of intersecting buckets. Check lives in skiller
(skill owner) and is accessible from the umbrella - `swissknifeman skills status`. Treatment:
remove the bucket from `enabledPlugins` (connect) **or** from `[skiller.sync]`
(vendor) + `skiller sync`.

## Conflicts

If the path of our skill is already taken **strangers** (directory/symlink/file that is not ours
`managed`), `sync` without `--force` him **skips** with warning, so as not to overwrite
alien. `--force` replaces the occupied path with the version from the library (the symlink is removed,
symlink target remains in place).

## Channel selection during onboarding (`integrate` / `onboard` / `setup`)

The channel is asked in advance - no need to write `[skiller.sync]` manually:

```bash
# the wizard will ask for the channel (connect/vendor) interactive
skiller integrate
# or without asking:
skiller integrate --skills-channel vendor --yes   # vendor → sync in .claude/skills
skiller integrate --skills-channel connect --yes  # plugins marketplace

# on full onboarding into the ecosystem (also asks; flag for non-interactive):
maind onboard <project> --skills-channel vendor
swissknifeman setup <project> --skills-channel vendor
```

When `--skills-channel vendor` for Claude-project `integrate` **generates itself**
`[skiller.sync]` from the project profile (`buckets` by type) and immediately applies
`sync` — skills are in `.claude/skills/`. Then refine the set by editing
config (`include`/`exclude`) and repeat `skiller sync`. For Cursor/Gemini physical
transfer to `.ai/.cursor` — separate legacy-command `skiller vendor --agent cursor`.

## Philosophy: Laravel Boost do not use as a channel

Laravel Boost — this **MCP-server** (database-query, tinker, logs, docs…) **and** channel
skills. Useful as MCP, but how **skill source** we remove it: all skills must
undergo a single library check swissknifeman, without separate compatibility with Boost.

- Boost **remains as MCP** (`boost.json: "mcp": true`, server `laravel-boost` in
  `.mcp.json`) and can leave their guidelines (`"guidelines": true`).
- Boost **ceases to be a skill channel**: `boost.json::skills` → `[]`. His former
  skills are replaced **direct analogues from the library** (`managed`, via config) —
  e.g. `inertia-vue-development`→`frontend-backend/inertia-vue`,
  `tailwindcss-development`→`frontend-tailwind/tailwind-conventions`.
- needed, but missing in the library Boost-skill **is imported into it** as external
  (`source: external`), undergoes registry validation and then lives as usual.
- own project skills (git-tracked, e.g. in `.ai/skills/`) remain untouched -
  `sync` does not grind them (they don't `managed`).

See also [Installing skills](./installation) (channel connect) and
[Registry skills.json](./registry) (source of truth set).
