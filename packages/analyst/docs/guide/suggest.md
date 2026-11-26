# suggest — cross-project pattern → skill draft

`analyst suggest` closes the gap between «found a cross-project pattern» ([scan](./lifecycle#cross-project-scan-p2))
and «is reusable [skill](/skiller/guide/)». This is a deterministic bridge: pattern →
**staged-DRAFT** `SKILL.ru.md`, which a person finalizes and promotes. Further directions - [roadmap](/roadmap).

```
analyst suggest <pattern_id> | --all [--bucket B] [--min-weight N] [--dry-run] [--json] [--force]
```

## What it does

Reading **only** abstracted index `<state>/analyst/index/by_pattern/<id>.json` and
generates staged-directory:

```
<state>/analyst/drafts/<pattern_id>/
  SKILL.ru.md      # RU-source-BLANK (frontmatter-skeleton + provenance stamp + body) — ruled by man
  draft.meta.json  # draft passport: provenance + seed_sha256 (detection of manual edits)
```

Catalog **mirrors the skill form** (`skills/<bucket>/<name>/`) — person puts next to `snippets/` and
transfers with one command.

## Invariant - what suggest DOES NOT

| Doesn't | How to hold |
|:--|:--|
| Doesn't write to `skills/` | Only `<state>/analyst/drafts/`; promo - human hands |
| Does not generate EN `SKILL.md` | Only RU-workpiece; EN — man promtom skiller after modification |
| Does not auto-register | Doesn't call `skiller registry`/`integrate`; does not touch `skills.json` |
| Does not disclose raw/secrets | Reading **only** index `by_pattern/` (is already abstracted) — privacy is structural |
| Does not overwrite human edits | `seed_sha256`-detection: the corrected body is not touched without `--force` |
| Does not delete auto drafts | Orphaned - warning, not delete |

## Idempotency (edit-safety)

Re-suggest does not overwrite manual work. Mechanism - `seed_sha256` in `draft.meta.json`:

- no catalog → create (`created`);
- body matches the generated one → `unchanged`;
- body == past seed (did not correct) or `--force` → regenerate (`updated`/`forced`);
- body != past seed (ruled with their hands) → body **do not touch**, we refresh only the provenance meta
  (`skipped-edited`).

**Orphaned drafts** (pattern disappeared from the index) when `--all` — **warning, not deleting**
(unlike [scan-prune](./lifecycle#cross-project-scan-p2): human-editable draft,
auto-delete = loss of labor).

## Numeric gates

By default - for all patterns given `scan` (have already passed `min_projects≥3`). `--min-weight N`
raises the bar for the number of projects. `--min-tier` **deferred**: does not carry the pattern index confidence
(she per-lesson, P3) — would require reading the lessons backwards, which would break «read only the index».

## Promotion of a draft in skill (does a person)

`suggest` prints the exact sequence (repo-grounded, **not** `skiller integrate` — he sews
skills *to the project*, does not register a new one):

1. `mkdir -p skills/<bucket>/<name>/` and move it there `SKILL.ru.md` (`name` == directory name).
2. Generate EN-canon: promt `packages/skiller/prompts/generate/claude-canon-from-ru.md` → `SKILL.md`.
3. `bash packages/skiller/scripts/check-translations.sh --stamp`.
4. `bash packages/skiller/scripts/validate.sh`.
5. `skiller registry`.

`bucket` impossible to guess (namespace — insulation, bucket — topic): default `TODO`-placeholder +
tooltip with list of buckets; person chooses (`--bucket B`). Bilingual skill model -
see [skiller](/skiller/guide/creating-skills).
