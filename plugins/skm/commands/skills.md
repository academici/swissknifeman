---
description: Select and apply skill buckets skiller to project - channel connect (Claude marketplace) or vendor (physical copies for Cursor/others).
argument-hint: "[connect|vendor] [bucket1,bucket2 | --profile P]"
allowed-tools: Bash(skiller:*)
---
Selection of skills for the project through **skiller**. Input: «$ARGUMENTS».
Launcher - `skiller` (after `./install.sh`).

## Steps
1. **Channel** (ALWAYS specify if not specified in «$ARGUMENTS»):
   - `connect` — for **Claude Code**: plugin activationmarketplace, skills are not copied (live in the registry, auto-updated);
   - `vendor` — for **Cursor / other agents**: physical transfer SKILL.md to the project (`.cursor/skills` / `.ai/skills`).
2. **What's available** — list registry buckets (from `buckets.json` / `skills.json` repository skiller): architect, php, frontend, devops, quality, operator, pm, founder, python, oss-dev, roles, system, general, blender, imported, generate-skill.
3. **Select** — check with the user for the required buckets (or profile). This is it «checkboxes»: you ask, you collect a list.
4. **Application**:
   - connect: `skiller connect --plugins <bucket1,bucket2>` (or `--profile <P>`);
   - vendor: `skiller vendor --agent <claude|cursor|generic>` (set - from `.swissknifeman/config.json`; for a one-time sample, specify the composition).
5. **Report**: what's connected/copied. For vendor update the map: `skiller lock`.
