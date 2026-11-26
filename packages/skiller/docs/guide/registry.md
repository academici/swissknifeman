# Registry skills.json

`skills.json` at the root of the repository is a machine-readable catalog of all skills.
File **is generated**, his hands do not rule.

## What does it store?

For each skill:

- path and version;
- `sha256` of each file - integrity and change detection;
- **provenance**: `source: local | github | http`, URL upstream, `fetched_at`;
- **graph and routing** (registry v5): `tags`, `requires`, `produces_for`
  from frontmatter — fields are optional and omitted if empty.

The registry always shows what is written in the library, where it came from and
how old.

Graph fields are used [dependency graph page](./graph) (is generated
`registry.render_graph` every time `skiller registry`);
`skiller vendor` reads `requires` directly from frontmatter and transitively
does not meet the dependencies in a custom installation.

## Reassembly

```bash
# Rebuild the registry (skills.json, plugin manifests, graph)
skiller registry
```

`skiller registry` parses frontmatter each `SKILL.md` (only
frontmatter, not the entire file body), counts hashes and collects the final JSON.

## Automation

- The author runs `skiller registry` and commits the result; `sha256-update.yml` and the skiller unit of
  `modules.yml` run `skiller registry --check` on push and PR (read-only: no workflow commits to `main`).

Separate mirroring in Obsidian vault no longer exists: vault — normal
consumer project that connects via `skiller vendor`
and updated with the command `skiller update` (see [CLI](./cli)).

## When to rebuild manually

After any change in skills: added a new one, updated the version in frontmatter,
imported external. Validator and CI will notice that the registry is out of sync with the contents
`skills/`.
