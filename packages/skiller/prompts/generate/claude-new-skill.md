# Claude: generation of a new skill

Create a new skill for swissknifeman. **First** check that it is not a duplicate
existing (otherwise expand the existing one - anti-bloat).

## Parameters (fill out before sending)
- Bucket: [existing bucket from `skills/`]
- Name: [kebab-case, == directory name]
- Task: [1–2 suggestions - what it does and when to use it]
- Risk: [read / draft / write / external]
- Dependencies: [`requires` — list or «no»]

## Requirements
1. Frontmatter strictly according to the scheme: `name`, `bucket`, `version: 0.1.0`, `description`,
   `risk`, `persona`, `tags`, `requires`, `produces_for`, `outputs`, `snippets`,
   `adapters: [claude, cursor, fable]`, `sha256: ""` (will fill in `skiller registry`).
2. `description` — specific and compact: it is resident in every request (tier-0).
3. Body sections: «Context» (when/why), «Algorithm», «Imprint», «Checklist».
4. The body is laconic (landmark ≤150 lines); voluminous examples - in `snippets/`.
5. Without specific project names/packages and without hardcoded model names in the body.
6. Language - Russian (registry convention).

Output: contents `SKILL.md` + string with path `skills/<bucket>/<name>/SKILL.md`.
After insertion - `skiller registry` and `scripts/validate.sh`.
