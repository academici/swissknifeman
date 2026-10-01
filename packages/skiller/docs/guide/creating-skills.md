# Creating skills

Two ways to replenish the registry: write your own skill or selectively import
external with update tracking.

## Your own skill

1. Copy `SKILL_TEMPLATE.md` → `skills/{bucket}/{name}/SKILL.md`
2. Fill in frontmatter and sections (see [Anatomy of a skill](./skill-anatomy))
3. Add `snippets/` with manifest `index.json`
4. Check: `./scripts/validate.sh`
5. Rebuild the registry: `skiller registry`
6. Open PR — CI will run the same validation

::: tip generate-skill
There is a meta-skill in the repository `generate-skill/` — agent can create new
skills based on the template yourself. It is installed only with a profile `standalone`
(`include_meta: true`).
:::

## Section `## Conformance`

Machine-squeezable checklist of skill rules: bulleted list of imperatives,
**≤10 lines**, grappable (`grep -A12 '^## Conformance' SKILL.md`). Consumer -
conformance-finder'review orchestrator's (`task:review`, Stage B): finder gets
section as a checklist and checks the diff against each line. New skill in the registry
⇒ new dimension review automatically.

Authoring rules:

- **Mandatory for new skill conventions** (naming / writing-style / stack / laravel
  etc.); existing ones are added incrementally as you touch them.
- Extract from the text of the skill itself, not new rules: each line can be reduced to
  sections/body rule SKILL.
- String = one verifiable imperative («do X» / «don't Y»), without explanation,
  examples and links - details live in the body.
- Written in singular EN-only `SKILL.md`; provider projections are regenerated
  `skiller registry`.
- No section - finder will take the rulebook from the body SKILL (quality checklist / hard
  bans), but it is more expensive and noisier; For conventions, the section is preferred.

Examples: `general/naming-conventions`, `general/writing-style`,
`general/git-commit-rules`, `quality/artifact-review`.

## External skill

External skills are taken **selectively** — only what really fits
production scripts, not entire repositories. Candidates and Source Analysis -
in the catalog `references/`.

1. Create a folder: `mkdir -p skills/{bucket}/{name}`
2. Create `upstream.json` (sha256 and fetched_at leave blank):

```json
{
  "schema_version": 1,
  "source": "github",
  "repo": "owner/repo",
  "strategy": "replace",
  "files": [
    {
      "path": "SKILL.md",
      "url": "https://raw.githubusercontent.com/owner/repo/main/SKILL.md",
      "sha256": "",
      "fetched_at": ""
    }
  ]
}
```

3. Download the file and commit sha:

```bash
./scripts/update-upstreams.sh --apply --skill {bucket}/{name}
```

4. Select strategy:
   - `replace` — file is mirrored as is; upstream must have a suitable one
     frontmatter (`name` + `description`), otherwise the validator will not pass;
   - `notify` — you adapt the local copy (yours frontmatter, edits);
     upstream updates are only reported;
   - `fork` — a large external skill that you wrap with a thin navigator.
     The content mirror is placed in `references/source.md` (`files[].path` indicates
     on him), edits live in the wrapper `SKILL.md`, on upstream drift
     distribution is blocked until manual transfer. More details in
     [upstream-sync.md](./upstream-sync.md#fork-fork-with-local-edits).

5. `skiller registry` → PR
6. Update source status in `references/{source}.md` on `imported`

## Life cycle references/

`references/` — directory of external sources: one md-file to source with URL,
description, solution «take selectively / do not take», target bucket-ami and
status:

```
planned → imported | rejected
```

When the skill is actually imported, the status is updated and appears in the skill folder
`upstream.json`.

## Validation

Before each PR:

```bash
./scripts/validate.sh
```

Checks frontmatter of all skills, correctness `upstream.json`, profiles,
registry and snippet-manifests. CI ([validate.yml](./ci)) runs the same thing.
