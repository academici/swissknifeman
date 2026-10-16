# ADR 0079: The `skm` front door is a plugin of the hub root

## Status

Accepted

## Context

`skm` (`/skm`, `/skm:skills`, `/skm:integrate`, `/skm:status`, `/skm:doctor`) is the face of swissknifeman in a
project, but it lived in `packages/skiller/skm` and was published by skiller as a `management` unit with a generated
Codex adapter (`packages/skiller/adapters/codex/skm`). skiller has `destination: own-repo`: once it moves out, the
umbrella would lose its front door, or the skiller repository would carry the umbrella's plugin. Its `/skm:doctor`
diagnosed skiller only, while the hub has `swissknifeman doctor` for every module (ADR 0073).

## Decision

- **Place.** The plugin lives at `plugins/skm/` of the hub root: `.claude-plugin/plugin.json`, `commands/`, and for
  Codex `.codex-plugin/plugin.json` with its skill under `codex/skills/` (outside `skills/`, so Claude Code does not
  load the Codex adapter as a skill). The command names do not change.
- **Declaration.** `configs/umbrella.json` lists the plugins the hub root ships in `plugins` (`manifest` or `source`
  entries, no catalog); `aicore.content.marketplace` reads them like the `provides.plugins` of a module, with
  `package: root`. A name repeated by a module is `MARKETPLACE_DUPLICATE`; a malformed list is
  `MARKETPLACE_HUB_PLUGINS_INVALID`.
- **skiller.** skiller no longer renders the `skm` unit, its catalog entry or its Codex adapter. The host config
  `configs/skiller-host.json` names `plugins/*` in `plugin_dirs`, so skiller's validation knows the hub plugins as
  siblings (the same as module plugins).
- **Version.** `skm` goes to 0.5.0 (its source moved, so the release tuple changes): `configs/release-units.json`
  owns it as `explicit`, and the two manifests must say the same (`RELEASE_EXPECTED_VERSION_MISMATCH` otherwise).
- **Doctor.** `/skm:doctor` runs `swissknifeman doctor` (every module); `skiller doctor` stays for the registry alone.

## Alternatives considered

- Keep `skm` in skiller: rejected, the umbrella face would leave with skiller's repository.
- Split: the front door at the root, skill commands in skiller under a `skiller` plugin: rejected for now, it renames
  `/skm:skills` and `/skm:status` that projects use; the commands only call the installed CLIs, so they can stay together.

## Consequences

- A plugin of the hub root is data in `configs/umbrella.json`; a new one needs no code.
- Projects keep `skm@swissknifeman`; the version bump re-fetches the plugin once.

## Supersedes

Amends ADR 0075 (the `skm` entry of the skiller catalog, and `plugin_dirs` now also names hub plugin folders).
