# Claude: translation SKILL.md → SKILL.&lt;lang&gt;.md

Translate the attached `SKILL.md` into a human-readable version in another language.
File translation (`SKILL.<lang>.md`, e.g. `SKILL.en.md`) **gitignored and won't load
agent** — this is a reference for the person next to the canon `SKILL.md`.

## Rules
1. Add a marker line at the beginning:
   `> 🌐 Translation for humans. Agent uses SKILL.md, not this file.`
2. Translate freely with explanations, not literally.
3. Technical terms, paths, commands, field names - leave as is.
4. Comments inside code-blocks - translate; Don't touch the code itself.
5. Frontmatter — copy without changes (source of truth - `SKILL.md`).
6. Add a section at the end «Human context»: 3–5 suggestions - why skill,
   when it is actually used, what it is connected with.

Output only the content `SKILL.<lang>.md` + line with the file path.

> These files are the basis: the skill bodies are now in Russian, the translation is useful for
> migration of canon to compact English. Transfer coverage:
> Do not write the result as a parallel registry canon: local registry skills are EN-only.
