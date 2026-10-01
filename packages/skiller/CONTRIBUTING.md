# Contributing

## Adding a Local Skill

1. Copy `SKILL_TEMPLATE.md` → `skills/{bucket}/{name}/SKILL.md`
2. Add `snippets/` with `index.json` manifest
3. Run `./scripts/validate.sh`
4. Run `skiller registry` — updates skills.json **and generates
   plugin manifests** (`.claude-plugin/marketplace.json`,
   `skills/*/.claude-plugin/plugin.json`) and graph; definitely after
   additions/movements/skill removal
5. Open PR — CI runs the same validation

**Anti-bloat (required).** Create a new skill only if there is no intersection with
existing - otherwise **expand existing** (Step 0 in internal
`skill-authoring`). The skill must be **universal**: without project-specific
business logic and **without specific project names/packages** in the body/snippets
(in general: «consumer project», «dependent package»). Acceptance standard and
methodology - `docs/guide/methodology.md`.

**Section `## Conformance`.** For skill conventions (naming / writing-style / stack)
is required: ≤10 strings of imperatives - a machine-squeezable checklist for
conformance-finder'ov `task:review`. Authoring Standard -
`docs/guide/creating-skills.md`, § «Section `## Conformance`».

## Adding an External (Upstream-Tracked) Skill

We take external skills **selectively** — only what really fits. Candidates
and source analysis - in [references/](references/README.md).

1. `mkdir -p skills/{bucket}/{name}`
2. Create `upstream.json` (sha256/fetched_at leave blank):
   ```json
   {
     "schema_version": 1,
     "source": "github",
     "repo": "owner/repo",
     "strategy": "replace",
     "files": [
       { "path": "SKILL.md",
         "url": "https://raw.githubusercontent.com/owner/repo/main/SKILL.md",
         "sha256": "", "fetched_at": "" }
     ]
   }
   ```
3. `./scripts/update-upstreams.sh --apply --skill {bucket}/{name}` — will download the file and write sha
4. Select strategy:
   - `replace` — file is mirrored as is; upstream must have a suitable one
     frontmatter (`name` + `description`), otherwise the validator will not pass
   - `notify` — you adapt the local copy (yours frontmatter, edits);
     upstream updates are only reported
5. `skiller registry` → PR
6. Update source status in `references/{source}.md` on `imported`

## references/ Lifecycle

One md-file to source: URL, what is this, «take selectively» / «do not take», targets
bucket-s, status `planned` → `imported` / `rejected`. During actual import
skill - update status and add `upstream.json` to the skill folder.

## Buckets

| Bucket | Purpose |
|--------|---------|
| founder, pm, architect | Business & architecture |
| oss-dev, quality, operator | Engineering practices |
| devops, php | Infrastructure & Laravel |
| roles | Persona-based skills |
| imported | External super-skills (upstream-tracked) |

## Validation

```bash
./scripts/validate.sh    # before each PR; CI runs the same thing
```

Checks: frontmatter all SKILL.md (for external upstream.json — only
`name` + `description`), diagram upstream.json, profiles/*.json, skills.json,
snippet-manifests, buckets.json (1:1 with catalogs bucket-ov), freshness
plugin-manifests (`.claude-plugin/`), uniqueness of skill names (double inside
bucket-a - error, between bucket-ami - warning) and running tests CLI (see below).

## Tests

Logic CLI lives in the package `lib/skiller/` (`bin/skiller` —
slim launcher). Tests - stdlib `unittest`, without dependencies:

```bash
./scripts/test.sh        # unit + integration; -v — verbose output
```

Unit tests cover pure functions (frontmatter, flag parsing, selection
skills, resolve `requires`); integration drives `connect`/`vendor` vs
synthetic registry in tmpdir (`tests/fixtures.py`) — real registry and network
are not needed. `validate.sh` starts `test.sh`, so call him separately before PR
optional.

## Releases & Tagging

- Annotated semver-tags: `git tag -a vX.Y.Z -m "..."` (push tags - manually).
- **minor** — new wireframe feature (CLI, installer, registry, marketplace);
  **patch** — filling/skill edits.
- When tag, move section `[Unreleased]` CHANGELOG in `[X.Y.Z]`.
- Plugin versions Claude Code are resolved in git SHA (fields `version` in
  manifests intentionally not) — tags serve as human-readable release markers,
  do not affect plugin updates.

## Snippet Guidelines

- Anonymize project namespaces: `namespace App\...`
- Add source comment: `// Source: {project}/{file} (anonymized)`
- Quality threshold for scanner: ≥ 60 (see `.skills-scanner.json`)

## Adapters

Provider-specific deltas go in `skills/{bucket}/{name}/adapters/` — never duplicate full SKILL.md.

Global adapter docs: `adapters/{cursor,claude-code,perplexity}/`.

Separate sync-script for Obsidian no: vault (brain) — normal consuming
project (`cd <vault> && skiller vendor`, next `skiller update`).

## Scanner

```bash
./scripts/scan-skills.sh              # SCAN + ANALYZE
./scripts/scan-skills.sh --extract    # + EXTRACT to .scanner-output/
./scripts/scan-and-pr.sh              # + COMMIT + PR
```

## Internal Project Skills

The methodology for developing the registry itself is fixed in internal skills
`.claude/skills/` (package-architecture, skill-authoring, release-discipline,
docs-maintenance). They are automatically picked up Claude Code in this repo,
**are not exported** (validator and registry scan only `skills/**`) and
are linted softly: frontmatter `name` + `description`, name == directory name.

## Backlog

- [ ] Filament resource generator skill
- [ ] Deeper AzGuard snippet extraction via scanner
- [ ] Per-skill adapter deltas where providers diverge
- [ ] Selectively import candidates from references/ (laravel-specialist, laravel-tips, MADR)
