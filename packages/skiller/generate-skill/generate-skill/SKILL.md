---
name: generate-skill
bucket: meta
version: 0.1.0
description: "Meta-skill for creating new skills from SKILL_TEMPLATE"
risk: write
persona: architect
tags: [meta, scaffolding]
requires: []
produces_for: []
outputs: ["skills/{bucket}/{name}/SKILL.md"]
adapters: [claude, cursor, fable]
sha256: ""
---

## Context

Use when you need to create a new skill in the registry academici/swissknifeman.

## Algorithm

1. Define bucket and name
2. Copy SKILL_TEMPLATE.md
3. Fill in frontmatter and sections
4. Add snippets/ with index.json
5. **Start it evals/** (eval-first): `skiller eval <bucket>/<name> --scaffold` →
   fill in `evals.json` (cases + software assertions), `pressure.json`
   (temptation scenarios «skip skill») and `triggers.json` (response accuracy
   descriptions). Run - `skiller eval <bucket>/<name>` (requires CLI `claude`).
6. Run `skiller registry`

> **Eval-first.** Skill without evals — unverifiable assertion. Create cases
> along with the skill: what it should do (evals) and what to keep under
> pressure (pressure). `validate.sh` shows coverage evals in one line.
