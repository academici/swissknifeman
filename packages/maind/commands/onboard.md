---
description: Project onboarding into the ecosystem mAInd — skills + memory + graph + MCP. Specifies the dialing with dialogue, then calls `maind onboard`.
argument-hint: "[path-or-id] [recommended|full|minimal]"
allowed-tools: Bash(maind:*)
---
Connecting the project to the hub **mAInd**. User input: «$ARGUMENTS».
Launcher - `maind` (if not in PATH — `${CLAUDE_PLUGIN_ROOT}/bin/maind`).

## Steps
1. **Target.** If in «$ARGUMENTS» no path/id — ask the user for the path to the repository or id project. New way maind will register itself.
2. **Set** (CLI is non-interactive - YOU ask, through AskUserQuestion):
   - **bundle**: `recommended` (default) · `full` (memory federation + brain core) · `minimal` · `custom`;
   - **skill channel** (applies to skills ONLY; memory/graph/MCP — as usual): `connect` (plugins,
     not in repo, need registry swissknifeman) vs `vendor` (physical. copies in `.claude/skills/`, in the repo -
     work for external developers without swissknifeman) → flag `--skills-channel connect|vendor`;
   - **code graph** (Serena, project symbol graph) — yes/no → flag `--with-code`;
   - **brain doc-sync** — yes/no → flag `--with-brain`.
3. **Preview** (first MANDATORY dry-run):
   `maind onboard <project> --bundle <B> [--skills-channel <C>] [--with-code] [--with-brain] --dry-run --json`
   Show the user the outline of steps from the output.
4. **Application** upon confirmation (without `--dry-run`, with `--yes`):
   `maind onboard <project> --bundle <B> [--skills-channel <C>] [--with-code] [--with-brain] --yes --json`
5. **Report.** Go through the output steps (register / skills / deploy / graph / memory / skill). Steps `skipped` due to lack of swissknifeman/brain — this is normal (every step standalone-safe).

onboard transitively raises skills (swissknifeman `integrate`) and MCP-hub servers - no need to install them separately.
