# Anatomy of a skill

Skill is a folder inside bucket-a. Minimum - one `SKILL.md`; usually nearby
there are snippets and adapters delta-files.

```
skills/laravel-testing/laravel-testing/
├── SKILL.md          # required: frontmatter + instructions for agent
├── snippets/         # code examples, templates, help files
│   ├── index.json    # snippets manifest
│   └── pest-example.md
├── adapters/         # optional: overrides for specific IDE
│   ├── claude.md
│   └── cursor.md
└── upstream.json     # only for external skills (see Upstream-sync)
```

## SKILL.md

The file consists of YAML-frontmatter and bodies with instructions:

```markdown
---
name: skill-name
bucket: <bucket-directory-name>   # must match skills/<bucket>/ and have an entry in buckets.json
version: 0.1.0
description: "Brief description of the skill"
risk: read|draft|write|external
persona: founder
tags: []
requires: []
produces_for: []
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

## Context
When to use this skill and why it is needed.

## Input data
What the agent must know before executing.

## Algorithm
Step-by-step instructions for the agent.

## Imprint
Specific files that will be created.

## Quality checklist
- [ ] Criterion 1

## Links
- snippets/example.md
```

## Key fields frontmatter

| Field | Purpose |
|---|---|
| `name` | unique name; with a flat layout, collisions are resolved by a prefix bucket-a |
| `description` | the agent decides when to use the skill - write specifically |
| `risk` | `read` — read only, `draft` — drafts, `write` — changes files, `external` — external calls |
| `requires` / `produces_for` | connections between skills (for example, `prd-from-brd` requires exit `brd`) |
| `snippets` | list of snippets that the skill uses |
| `adapters` | in which agents the skill is tested |
| `sha256` | is filled in automatically `skiller registry` |

## Snippets

`snippets/` — these are working materials of the skill: code examples, document templates,
reference books. Manifesto `index.json` lists files and checks
`validate.sh`. Snippets allow you to keep `SKILL.md` short: instructions
separately, voluminous examples separately.

## Delta-adapter files

Specific IDE does not mix with the main skill, but is placed in
`adapters/<agent>.md` inside the skill folder:

- `adapters/claude.md` — overrides for CLAUDE.md-specifics Claude Code;
- `adapters/cursor.md` — overrides for `.cursor/rules`.

So one skill remains provider-neutral, and the adapters impose a thin
setting during installation. Delta format (`Override:` / `Additional:`, pre-flight
hooks) — in [adapter delta specifications](./adapter-deltas).

## upstream.json

Present only for external skills and describes the source and strategy
updates - details in [Upstream-sync](./upstream-sync). Main rule:
**no `upstream.json` → self-written skill, sync-tuning does not touch him**.

## Body size `SKILL.md` — no platform cap (OQ-4)

The body of the selected skill is read by the provider **in full** — neither Claude Code, neither
Codex no file size limit `SKILL.md` (original source Codex straight
says: detection budget is applied «only to the initial skills list», a
the selected skill is loaded completely). The real limitation is **listing
detection** (name+description of each skill, resident in each request), not
file: see [Token budget](./budget.md). Body cap `SKILL.md` is not entered by this
(); the only limiter is soft warn
`validate.sh` by number of non-empty body lines (internal skill `skill-authoring`,
section «lean SKILL.md») — it's about readability, not about the platform limit.
