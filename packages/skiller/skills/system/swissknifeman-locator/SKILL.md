---
name: swissknifeman-locator
bucket: system
version: 0.1.0
description: Reach swissknifeman (skills node) from an external repo — non-hardcoded path resolution, root config.json as registry of linked projects, project↔hub link scheme
risk: read
persona: architect
tags: [swissknifeman, skills, registry, navigation, locator, ecosystem]
requires: [local-topology]
produces_for: []
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Skill: Swissknifeman Locator

Use when: an agent in an **external repo** wants to find the ecosystem's control monorepo (**swissknifeman**, node `skills-hub`), learn from its root `config.json` **which projects exist and how they link**, or recognize how the current project is wired to the hub. Drill-down into one node of the `local-topology` map, with path resolution that works without a topology config.

swissknifeman carries the AI-skill registry + distribution into projects + ecosystem binaries (`maind` — memory/graph/MCP, `skiller` — skills, `harness` — environment).

## swissknifeman path resolution (non-hardcoded)

Path is machine-specific — **resolve, don't hardcode**. Ladder:

```bash
# A. Explicit env override
SKM="$SWISSKNIFEMAN_ROOT"

# B. Via an installed ecosystem binary (anchor): readlink to the real file in the repo,
#    climb bin → package → packages → root (3 levels)
if [ -z "$SKM" ]; then
  BIN="$(command -v maind || command -v skiller)"
  [ -n "$BIN" ] && SKM="$(cd "$(dirname "$(readlink -f "$BIN")")/../../.." && pwd)"
fi

# C. Candidates from $HOME (first existing); canonical — projects/packages/swissknifeman
if [ -z "$SKM" ] || [ ! -f "$SKM/config.json" ]; then
  for c in "$HOME/projects/packages/swissknifeman" "$HOME/projects/swissknifeman" "$HOME/swissknifeman"; do
    [ -f "$c/config.json" ] && SKM="$c" && break
  done
fi

# Proof of root: config.json + packages/skiller + packages/maind
[ -n "$SKM" ] && [ -f "$SKM/config.json" ] && [ -d "$SKM/packages/skiller" ] \
  && cd "$SKM" || echo "swissknifeman not found: set \$SWISSKNIFEMAN_ROOT"
```

If nothing matched — **tell the user**, ask for `$SWISSKNIFEMAN_ROOT`; don't guess.

## Root `config.json` = registry of linked projects (two-way link)

Root `config.json` holds `projects[]` for the whole ecosystem: `{id, name, local_path, vault_path, type, namespaces, docs_folders, dependencies, mcp, roles}`. A tooling registry (imports the Brain catalog, adds namespaces/type/graph/mcp).

```bash
# ecosystem projects: id, type, path, namespaces
jq -r '.projects[]|"\(.id)\t\(.type)\t\(.local_path)\tns=\(.namespaces//[]|join(","))"' "$SKM/config.json"

# namespaces (memory/graph isolation groups)
jq -r '.namespaces|to_entries[]|"\(.key): \(.value.name) — \(.value.description)"' "$SKM/config.json"

# package dependency graph
jq -r '.projects[]|select((.dependencies//[])|length>0)|"\(.id) → \(.dependencies|join(","))"' "$SKM/config.json"

# bridge to the Brain docs-hub
jq -r '.integrations.brain.path' "$SKM/config.json"   # path to vault .projects.json (see brain-locator)
```

**Two-way:** the project references swissknifeman (via its artifacts — below), and `config.json.projects[]` lists the project. Two sides of one link.

## Project↔swissknifeman link scheme (how to recognize)

In an external project's root the link shows via artifacts:

- **`.swissknifeman/config.json`** (`mode:"vendor"`, `buckets`/`exclude`) — **vendor** channel: physical skill copies in `.claude/skills/`.
- **`skills-lock.json`** (`skills:{<name>:{source, managed, bucket, installed_path}}`) — installed-skill map; `source:"swissknifeman"` + `managed:true` = vendored from the hub.
- **`.claude/settings.local.json` → `enabledPlugins` + `extraKnownMarketplaces`** — **connect** channel: bucket plugins, marketplace points to the local swissknifeman path (skill files NOT copied).
- **`.mcp.json` → server `maind`** — project wired to the memory/graph hub.

Deeper (installing/changing/syncing skills via two channels, doc-sync) — runbook `project-tooling-runbook`; onboarding to the hub — `ecosystem-integration`; environment (permissions/MCP/hooks/agent-packs) — `harness-operations`. The locator only helps **recognize** the link and reach the node, not duplicate their procedures.

## Principles

- **Read-only guide.** Finds the node and reads `config.json`; ecosystem edits go through `skiller`/`maind`/`harness`, not by hand.
- **Resolve, don't hardcode.** Root from binary/env/`$HOME` candidates.
- **Don't duplicate runbooks.** Install/sync commands live in the dedicated skills, don't copy them here.

## Checklist

- [ ] Root resolved via binary/env/`$HOME`, not hardcoded
- [ ] Ecosystem overview read from `config.json.projects[]`/`namespaces`
- [ ] Project link recognized by `.swissknifeman/config.json`/`skills-lock.json`/`enabledPlugins`
- [ ] Depth delegated to `project-tooling-runbook`/`ecosystem-integration`

## Links

- `local-topology` (system bucket) — root map of three nodes; swissknifeman = node `skills-hub`.
- `brain-locator` (system bucket) — paired locator for node `docs-hub`; bridge via `integrations.brain.path`.
- `project-tooling-runbook`, `ecosystem-integration`, `harness-operations` — operational depth (if available).
