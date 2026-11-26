# Adapter: Claude Code

Full cycle of integration with Claude Code: plugins (skills) + permissions.

Main mechanism - **native plugin marketplace**: swissknifeman is
plugin marketplace (`.claude-plugin/marketplace.json`), each bucket —
separate plugin. Skills are not copied to the project repository: they live in the cache
Claude Code and are updated from this repo.

## Once per machine: add marketplace

```bash
claude plugin marketplace add ~/projects/packages/swissknifeman
```

Source - local folder: push is not needed, but the plugin version is tied to git SHA,
so the edits are being updated **after local commit** (then
`/plugin marketplace update swissknifeman` + `claude plugin update <p>@swissknifeman`
or session restart).

## For each project: connect plugins

```bash
cd ~/projects/my-app && skiller connect
```

The command defines the project type (same markers as `skiller vendor`;
the project root is located automatically from the current directory) and writes
in `.claude/settings.local.json` project:

```json
{
  "extraKnownMarketplaces": {
    "swissknifeman": {
      "source": { "source": "directory", "path": "/home/<you>/projects/packages/swissknifeman" }
    }
  },
  "enabledPlugins": {
    "php@swissknifeman": true,
    "quality@swissknifeman": true
  }
}
```

File `settings.local.json` is not committed - the local path is not included in
project repository. Merge idempotent: explicit `false` does not fray,
extra enabled plugins are not disabled (only reporting).

Useful flags: `--profile`, `--plugins a,b,c`, `--list`, `--dry-run`,
`--cleanup-vendored`, `--file settings.json`.

## Plugins and namespaces

Plugin = bucket (+ meta plugin `generate-skill`). Plugin skills are received
namespace `<plugin>:<skill>`: `php:laravel-packages`, `quality:code-review`,
`devops:docker-php`. For skills from `imported/` name is taken from frontmatter, and not
from the folder: `imported:ai-agent-super-skill`.

Manifests (`.claude-plugin/plugin.json` in each bucket-e and root
`marketplace.json`) **are generated** — after adding/skill moves
run `skiller registry`; `validate.sh` catches obsolete ones.

## Updates

- Plugin version = git SHA repository (field `version` is not set intentionally),
  so skill edits are visible in projects **after local commit** in this repo.
- Pull up: `/plugin marketplace update swissknifeman`, then
  `claude plugin update <plugin>@swissknifeman` (or session restart).

## Migration from old vendor

Previously, skills were copied to `.claude/skills/` project (vendoring - now
`skiller vendor --agent claude`, deprecated for Claude Code).
`skiller connect` finds the old manifest
`.swissknifeman-manifest.json` and by flag `--cleanup-vendored` deletes **only**
vendor copies - the project's own skills are not affected.

## Switch to GitHub-source (another car / CI)

The local path only works on this machine. Where is the repo available at git:

```json
{
  "extraKnownMarketplaces": {
    "swissknifeman": {
      "source": { "source": "github", "repo": "academici/swissknifeman" }
    }
  }
}
```

Such a source can also be placed in a committed `.claude/settings.json`
(`skiller connect --file settings.json` + manual editing source). For background
private repo auto-updates needed `GITHUB_TOKEN` surrounded.

## Permissions

After the plugins, tighten up the permission presets:

```bash
./scripts/apply-permissions.sh --target ~/projects/my-app
```

Details in [guide to permissions](/harness/configs/claude-permissions).

## Delta-files

Specifics Claude Code inside the skill is placed in `adapters/claude.md` —
overrides for CLAUDE.md-specifics. Format - in
[adapter delta specifications](../guide/adapter-deltas).

## Vendoring (deprecated for Claude Code)

`skiller vendor --agent claude` (from the project directory) still
works (flat layout + manifest), but for Claude Code preferred
marketplace: single
source, updates without reinstallation, nothing extra in the project repo.
Vendoring remains the main route for Cursor and other agents - see.
[Installing skills](../guide/installation).
