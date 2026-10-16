---
name: brain-locator
bucket: system
version: 0.2.0
description: Reach the Brain vault (ecosystem Obsidian docs) from a project — non-hardcoded path resolution (maind/$HOME), own and linked-project docs, sync
risk: read
persona: architect
tags: [brain, vault, docs, navigation, locator, obsidian]
requires: [local-topology]
produces_for: []
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Skill: Brain Locator

Use when: an agent in **any project** wants to find the ecosystem docs store (**Brain vault**, node `docs-hub`), reach **own** docs or a **linked** project's docs, or check whether the project is synced with Brain. Drill-down into one node of the `local-topology` map, with path resolution that works even without a topology config.

**Marker.** If this skill is attached to a project → the project **participates in doc-sync with Brain**: its `docs/`/`docs-public` are mirrored to the vault via two-way `brain sync`. Skill present = project is "on Brain".

## Brain path resolution (non-hardcoded)

Vault path is machine-specific — **resolve, don't hardcode**. Priority ladder (mirrors `brain vault`: configuration `brain.vault_path` → `$MAIND_BRAIN_VAULT` → `~/Vaults/Brain`):

```bash
# A. The brain module resolver (if installed): configuration -> env -> default
if command -v brain >/dev/null 2>&1; then
  BRAIN="$(brain vault --json 2>/dev/null | jq -r '.path // empty')"
fi

# B. Explicit env override (if the ecosystem sets it)
if [ -z "$BRAIN" ]; then BRAIN="$MAIND_BRAIN_VAULT"; fi

# B2. maind resolver (if installed): brain record in the project registry
if [ -z "$BRAIN" ] && command -v maind >/dev/null 2>&1; then
  BRAIN="$(maind projects list --json 2>/dev/null \
            | jq -r '.projects[]|select(.id=="brain").vault_path // empty')"
fi

# C. Candidates from $HOME (first existing); canonical — ~/Vaults/Brain
if [ -z "$BRAIN" ]; then
  for c in "$HOME/Vaults/Brain" "$HOME/Brain" "$HOME/Documents/Brain"; do
    [ -d "$c" ] && BRAIN="$c" && break
  done
fi

# Proof it's really the Brain vault: root has .projects.json and CLAUDE.md
[ -n "$BRAIN" ] && [ -f "$BRAIN/.projects.json" ] && [ -f "$BRAIN/CLAUDE.md" ] \
  && cd "$BRAIN" || echo "Brain vault not found: set \$MAIND_BRAIN_VAULT or check ~/Vaults/Brain"
```

If nothing matched and `maind` is absent — **tell the user** the vault wasn't found and ask for `$MAIND_BRAIN_VAULT`; don't guess or hardcode.

## How Brain links to projects

- **`.projects.json`** at vault root — project catalog (generated cache): `{name, repo, vault_path, folders}`. Here `repo` = **absolute path to the code repo**, `vault_path` = project folder in the vault, `folders` (`["docs","docs-public"]`) = synced folders.
- **Control note** `05-Projects/<category>/<Name>/<Name>.md` with frontmatter `repo:` (code path) — project "control tower": status, cross-project links (`uses:`/`used_by:`), references. Catalog source of truth = this frontmatter (`.projects.json` is generated from it).
- **`CLAUDE.md`** of the vault — human-readable map of all projects (products/packages/business) + personas + vault-local skill triggers.
- **Obsidian `[[wikilinks]]`** — links between projects by audience/data/shared components.

## Navigation: own and linked-project docs

```bash
# 1) own record in the catalog — by repo == absolute path of the current project
jq -r --arg r "$(pwd)" '.projects[]|select(.repo==$r)|.vault_path' "$BRAIN/.projects.json"

# 2) own docs in the vault: <vault_path>/docs (+ docs-public); folder list — field folders
# 3) linked projects: control note <vault_path>/<Name>.md → frontmatter uses:/used_by:
# 4) overview of all projects and their repo links
brain list
```

Docs live **both** in the repo (`<repo>/docs`, `<repo>/docs-public`) **and** mirrored in the vault; `brain` keeps them in sync (two-way git-merge):

```bash
brain status <project>   # docs ↔ repo divergence?
brain sync <project>     # sync
```

## Principles

- **Read-only guide.** Explains the scheme and reads the catalog; does **not** write to the vault. Doc changes go only through `brain sync` (like `local-topology`).
- **Resolve, don't hardcode.** Vault path from `maind`/env/`$HOME` candidates, never a hardcoded string.
- **Don't confuse nodes.** Brain (`docs-hub`, Obsidian docs) is **not** the maind memory node (agent-memory daemon). Docs ≠ memory; for memory see `shared-memory`.
- **Don't commit machine-specific paths** into the project (`.projects.json`, absolute paths).

## Checklist

- [ ] Brain path resolved via `maind`/env/`$HOME`, not hardcoded
- [ ] Own record found by `repo == $(pwd)` in `.projects.json`
- [ ] Sync went through `brain status/sync`, didn't edit mirrors by hand
- [ ] Didn't confuse the Brain docs-hub with the maind memory node

## Links

- `local-topology` (system bucket) — root map of three nodes; Brain = node `docs-hub`.
- `swissknifeman-locator` (system bucket) — paired locator for node `skills-hub`.
- `shared-memory` (system bucket) — a DIFFERENT node: shared memory (maind agent-memory daemon), not Obsidian docs.
