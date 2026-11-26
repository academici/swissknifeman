---
description: Show plugins/marketplace ecosystems academici and enable the necessary ones - maind how the hub manages plugins (maind · swissknifeman · brain).
argument-hint: "[enable <plugin>@<marketplace>]"
allowed-tools: Bash(jq:*), Read, Edit
---
Managing ecosystem plugins academici from the hub **mAInd**. Input: «$ARGUMENTS».

## Current status (read-only)
!`jq '{enabledPlugins, marketplaces: (.extraKnownMarketplaces // {} | keys)}' ~/.claude/settings.json 2>/dev/null`

## What to do
1. Show the user: which marketplace registered and which plugins are enabled (`enabledPlugins`).
2. Compare with the ecosystem - both monorepo packages live in ONE marketplace `swissknifeman`:
   - `maind@swissknifeman` (hub: onboarding/sync/status/health),
   - `skm@swissknifeman` (project skills: buckets/connect/vendor/integrate),
   - `brain@brain` (docs-sync valta, separate repository).
   Mark what's missing (no marketplace or the plugin is disabled) and isn't it **takes**: the same
   plugin included from two marketplace (e.g. `maind@academici` + `maind@swissknifeman`) — leave
   only `@swissknifeman`.
3. If the user asks to enable it, edit it `~/.claude/settings.json` (Edit, keeping the rest):
   - enter `"<plugin>@<marketplace>": true` in `enabledPlugins`;
   - if marketplace not registered - add to `extraKnownMarketplaces` entry `{ "source": { "source": "directory", "path": "<repo path>" } }` (paths: maind+skm→monorepo root `swissknifeman`, brain — its directory).
4. Remind: changes are activated **after reboot** Claude Code.

> This is it «hub manages plugins»: maind writes `enabledPlugins`/marketplaces, like `connect.py` y swissknifeman. The operations themselves in projects are performed by teams `/maind:*`, `/skm:*`, `/brain:*`.
