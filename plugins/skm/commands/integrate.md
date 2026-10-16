---
description: Full project integration wizard via skiller (skills + hooks + permissions + memory + hub).
argument-hint: "[minimal|recommended|full|custom]"
allowed-tools: Bash(skiller:*)
---
Project integration via **skiller integrate**. Input: «$ARGUMENTS».
Launcher - `skiller` (after `./install.sh`). In non-interactive mode, you specify the choice.

## Steps
1. **Bundle**: `recommended` (default) · `full` · `minimal` · `custom`. If in «$ARGUMENTS» no - ask.
2. **Skill channel** (ASK via AskUserQuestion — applies ONLY to skills):
   - **connect** — plugins marketplace; files are not in the repo, you need access to the registry swissknifeman;
   - **vendor** — physical. copies in `.claude/skills/` (via `sync`), are committed to the repo → work for
     external developers without swissknifeman. → flag `--skills-channel connect|vendor`.
   Recommend **vendor**, if the project is given to third-party developers.
3. **Preview**: `skiller integrate --dry-run [--skills-channel <C>]` — show checklist (skills / permissions / auto-approve / memory / hub / docs-sync).
4. **Application** by confirmation: `skiller integrate --yes --bundle <B> [--skills-channel <C>]`.
5. **Report**: what is included for each block.
