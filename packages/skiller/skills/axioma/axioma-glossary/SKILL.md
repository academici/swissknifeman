---
name: axioma-glossary
bucket: axioma
version: 0.1.0
description: "Binds domain-modeling discipline to the live thin term-index of the Axioma ecosystem: canon path, its 4-column structure, delegation of the Rule-of-Two/steward model to domain-modeling (no embedded copy of content). Read when asking 'what does term X mean in another package' or suspecting a collision/homonym across packages — right after domain-modeling."
risk: read
persona: architect
tags: [axioma, ecosystem, glossary, term-index]
level: ""
requires: [domain-modeling]
produces_for: []
outputs: [chat]
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Axioma Glossary

## Context

`domain-modeling` is a universal discipline: it already mandates a package's
`CONTEXT.md` and defines the Rule of Two for entering the shared term-index,
but the mechanism itself does not store WHERE the term-index lives or how it
is structured. This skill is the Axioma-specific binding: it points to the
live canon's path, explains its 4-column structure, and runs the reading
algorithm against it. Read it right after `domain-modeling` — that skill
explains WHY and WHEN a term enters the term-index (Rule of Two, steward
model), this skill gives the CONCRETE path and canon format.

The single source of data is the live file
`02-Knowledge/00-Strategy/Ecosystem_Glossary.md` in the Brain vault. This
skill does NOT hold a copy of its contents — an embedded copy drifts from the
canon on the first term-index edit (same principle as `axioma-stack`→radar).

## Inputs

- The term that triggered the question/suspected collision (e.g. encountered
  a word in another package that means something different in your own
  `CONTEXT.md`).
- Candidate packages the term may have crossed between.
- Canon path: `02-Knowledge/00-Strategy/Ecosystem_Glossary.md` **relative to
  the Brain vault root** (not the current project's CWD). Working outside
  Brain — first resolve the Brain vault root (ecosystem maind hub / known
  path), then open the term-index there; a CWD-relative path silently
  collapses the check into a no-op.

## Canon structure (4 columns)

`| Term | Owning package | Collisions/homonyms | Deprecated synonyms |`

1. **Term** — the ubiquitous-language word/phrase that crossed the boundary
   of 2+ packages (Rule of Two — see `domain-modeling`).
2. **Owning package** — whose `CONTEXT.md` normalizes the definition
   (steward model: edit the meaning ONLY through the owner's `CONTEXT.md`,
   the term-index is a pointer, not a definition store).
3. **Collisions/homonyms** — the same word means something different in
   another package (e.g. `Entitlement` ≠ `Tariff` ≠ `Quota`).
4. **Deprecated synonyms** — old names for the same concept that may still
   show up in legacy code/docs.

## Algorithm

1. Read `domain-modeling` first if not already read in this session (gives
   the Rule of Two and steward model; this skill is its Axioma-specific
   execution).
2. Open `02-Knowledge/00-Strategy/Ecosystem_Glossary.md`.
3. Look up the term in the table (exact/close match on the "Term" column).
4. Term found → the "Owning package" column tells you whose `CONTEXT.md` is
   the source of truth for the definition; the "Collisions/homonyms" column
   warns of divergent meaning across packages — defer to it instead of
   memory/intuition.
5. Term NOT found → either it hasn't crossed the boundary of 2+ packages yet
   (Rule of Two not triggered, no entry needed), or it just did — handle via
   `domain-modeling` (edit the owner's `CONTEXT.md` + add a term-index row;
   the Rule-of-Two entry rule is not reimplemented here, only invoked — see
   `requires`).
6. Term-index and the owner's `CONTEXT.md` disagree → `CONTEXT.md` is the
   source of truth (`domain-modeling` rule), the term-index is stale and
   must be brought in line with it.

## Outputs

A short chat answer, one line per term:

`<term> → owner: <package> (collision: <yes/no — with what> | deprecated: <synonym|—>)`

Not a standalone file — the answer is embedded into the dialogue
(domain discussion/review), same as `axioma-stack`.

## Quality checklist

- [ ] Term-index read via the path
      `02-Knowledge/00-Strategy/Ecosystem_Glossary.md` as a live file, not an
      embedded copy.
- [ ] The full term-index table is NOT duplicated in the skill body — only
      column structure and a navigation algorithm.
- [ ] Rule of Two and the steward model are obtained via `domain-modeling`
      (`requires`), not rephrased in this skill's own words.
- [ ] On a term-index↔`CONTEXT.md` mismatch, `CONTEXT.md` is named as the
      source of truth, not the term-index.
- [ ] Cross-link to `domain-modeling` is present.

## Links

- `architect/domain-modeling` — ubiquitous-language discipline, Rule of Two
  for term-index entry, steward model (invoked by this skill, not
  duplicated).
- `02-Knowledge/00-Strategy/Ecosystem_Glossary.md` — the single source of
  data (canon, live file in the Brain vault).
- `axioma/axioma-stack` — analogous "mechanism in SKM, content in Brain"
  binding for the reuse registry (layout precedent).
