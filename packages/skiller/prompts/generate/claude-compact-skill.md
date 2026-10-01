# Claude: compaction SKILL.md

Rewrite the attached `SKILL.md` is more compact without losing its meaning. The goal is to reduce
tier-0 ⊕ always (description) and tier-1 ↻ on-trigger (body).

## Rules
1. Remove inlet water («This skill is intended for…»).
2. Instructional paragraphs → bullet-points.
3. Remove examples that duplicate an already formulated rule; large examples -
   take it out to `snippets/` (with link from body).
4. `description` — leave specifics (when to use), remove common words.
5. Code-do not touch the blocks for the purpose.
6. Frontmatter: remove `_comment`-strings; Save the schema fields.

## Output
1. Compact `SKILL.md`.
2. Statistics: was X lines / became Y / savings Z%.
3. What is included in `snippets/` and what was removed as a duplicate.

> Check before/after: `skiller budget --config <yours>.json` (or map
> `docs/guide/budget.md` after `skiller registry`).
